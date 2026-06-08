"""Local SQLite (WAL) store — the durability boundary.

Everything that must survive a crash or an offline window lives here: agent defs,
schedules, the outbound telemetry/command queue (replayed in order on reconnect),
run history, HITL state, the run checkpoint journal, agent memory + its change journal,
env-var names, capability state, and the command idempotency ledger.

Design notes:
  * One ``aiosqlite`` connection in WAL mode. WAL lets readers and a writer coexist and
    survives ``kill -9`` between commits.
  * The store is a *seam*: ``get_store()/set_store()`` mirror the cloud's bus/audit
    singletons so feature units depend on the interface, not construction order.
  * Schema is created with ``CREATE TABLE IF NOT EXISTS`` so opening an existing store
    is idempotent. Units that need extra tables create them additively in their own
    ``init`` — they must NOT rewrite this schema.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    type         TEXT,
    platform     TEXT,
    version      INTEGER,
    manifest     TEXT,
    updated_at   REAL
);

CREATE TABLE IF NOT EXISTS schedules (
    id           TEXT PRIMARY KEY,
    agent_id     TEXT,
    kind         TEXT,          -- cron | interval | date
    expr         TEXT,
    policy       TEXT,          -- skip | run_once | coalesce
    payload      TEXT,
    updated_at   REAL
);

-- Outbound daemon->cloud queue. Durable so telemetry/results survive an offline
-- window and replay IN ORDER on reconnect (at-least-once + idempotency).
CREATE TABLE IF NOT EXISTS outbound_queue (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT NOT NULL,         -- control | telemetry
    msg_type        TEXT NOT NULL,
    payload         TEXT NOT NULL,
    idempotency_key TEXT,
    created_at      REAL NOT NULL,
    acked           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_outbound_unacked
    ON outbound_queue (acked, seq);

CREATE TABLE IF NOT EXISTS run_history (
    run_id        TEXT PRIMARY KEY,
    agent_id      TEXT,
    status        TEXT,
    cost_usd      REAL DEFAULT 0,
    tokens_input  INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,
    started_at    REAL,
    finished_at   REAL,
    detail        TEXT
);

CREATE TABLE IF NOT EXISTS hitl_state (
    id          TEXT PRIMARY KEY,
    run_id      TEXT,
    status      TEXT,            -- pending | approved | denied | timeout
    action      TEXT,
    created_at  REAL,
    resolved_at REAL,
    decision    TEXT,
    actor       TEXT,
    reason      TEXT
);

-- Write-ahead checkpoint journal: one monotonic row per run step (§4.12).
CREATE TABLE IF NOT EXISTS checkpoints (
    run_id       TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    step_cursor  INTEGER,
    status       TEXT,           -- pending | in_flight | committed
    payload      TEXT,
    created_at   REAL,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS memory (
    agent_id   TEXT NOT NULL,
    namespace  TEXT NOT NULL DEFAULT 'default',
    key        TEXT NOT NULL,
    value      TEXT,
    tags       TEXT,
    version    INTEGER DEFAULT 1,
    updated_at REAL,
    PRIMARY KEY (agent_id, namespace, key)
);

CREATE TABLE IF NOT EXISTS memory_journal (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT,
    namespace  TEXT,
    key        TEXT,
    op         TEXT,            -- store | delete
    value      TEXT,            -- redacted value (never raw secrets)
    version    INTEGER,
    created_at REAL,
    synced     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS env_names (
    scope      TEXT NOT NULL,   -- shared | agent
    agent_id   TEXT NOT NULL DEFAULT '',
    name       TEXT NOT NULL,
    origin     TEXT,            -- ui | local
    updated_at REAL,
    PRIMARY KEY (scope, agent_id, name)
);

-- Daemon-tier provisioned capabilities (§4.11).
CREATE TABLE IF NOT EXISTS capabilities (
    id         TEXT PRIMARY KEY,
    kind       TEXT,            -- mcp | script | workspace | composite
    name       TEXT,
    status     TEXT,            -- installing | ready | failed
    manifest   TEXT,
    updated_at REAL
);

-- Agent-tier attachments (§4.11 tier 2).
CREATE TABLE IF NOT EXISTS agent_capabilities (
    agent_id   TEXT NOT NULL,
    capability TEXT NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 1,
    updated_at REAL,
    PRIMARY KEY (agent_id, capability)
);

-- Command idempotency ledger: a command_type+key seen once is never re-run.
CREATE TABLE IF NOT EXISTS idempotency_seen (
    key          TEXT PRIMARY KEY,
    command_type TEXT,
    seen_at      REAL
);

CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY,
    v TEXT
);

-- Cached, cloud-signed orchestration grants (verified offline before each call, §2.4).
CREATE TABLE IF NOT EXISTS orchestration_grants (
    grant_id    TEXT PRIMARY KEY,
    agent_id    TEXT,            -- the orchestrator agent this grant authorizes
    core        TEXT,            -- canonical signed-fields JSON (delivered verbatim)
    signature   TEXT,            -- base64 ed25519 signature over core
    public_key  TEXT,            -- delivered key (informational; daemon verifies w/ trusted key)
    cached_at   REAL
);

-- Orchestration lineage WAL: one row per agent-initiated child (§2.4 step 4).
CREATE TABLE IF NOT EXISTS orchestration_lineage (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_run_id TEXT,
    child_run_id  TEXT,
    root_run_id   TEXT,
    grant_id      TEXT,
    verb          TEXT,
    depth         INTEGER,
    budget_used   REAL DEFAULT 0,
    status        TEXT,          -- pending | running | completed | failed | halted
    created_at    REAL,
    completed_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_lineage_root ON orchestration_lineage (root_run_id);
"""


def _now() -> float:
    return time.time()


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


class LocalStore:
    """Async wrapper over the daemon's SQLite database."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = str(db_path)
        self._db: Optional[aiosqlite.Connection] = None

    # ── lifecycle ─────────────────────────────────────────────────────────
    async def connect(self) -> "LocalStore":
        if self._db is not None:
            return self
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA foreign_keys=ON;")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        return self

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("LocalStore not connected; call await store.connect()")
        return self._db

    # ── generic helpers ───────────────────────────────────────────────────
    async def execute(self, sql: str, params: tuple = ()) -> None:
        await self.db.execute(sql, params)
        await self.db.commit()

    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[dict[str, Any]]:
        cur = await self.db.execute(sql, params)
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row is not None else None

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        cur = await self.db.execute(sql, params)
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    # ── outbound queue (offline buffer; ordered at-least-once replay) ──────
    async def enqueue_outbound(
        self,
        channel: str,
        msg_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
    ) -> int:
        cur = await self.db.execute(
            "INSERT INTO outbound_queue (channel, msg_type, payload, idempotency_key, created_at, acked)"
            " VALUES (?,?,?,?,?,0)",
            (channel, msg_type, _dumps(payload), idempotency_key, _now()),
        )
        await self.db.commit()
        return int(cur.lastrowid)

    async def pending_outbound(
        self, channel: Optional[str] = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Unacked outbound rows in send order. Payload is decoded back to a dict."""
        if channel is None:
            rows = await self.fetchall(
                "SELECT * FROM outbound_queue WHERE acked=0 ORDER BY seq LIMIT ?",
                (limit,),
            )
        else:
            rows = await self.fetchall(
                "SELECT * FROM outbound_queue WHERE acked=0 AND channel=? ORDER BY seq LIMIT ?",
                (channel, limit),
            )
        for r in rows:
            try:
                r["payload"] = json.loads(r["payload"])
            except (ValueError, TypeError):
                r["payload"] = {}
        return rows

    async def ack_outbound(self, seq: int) -> None:
        await self.execute("UPDATE outbound_queue SET acked=1 WHERE seq=?", (seq,))

    async def purge_acked_outbound(self, older_than_seconds: float = 0.0) -> int:
        cutoff = _now() - older_than_seconds
        cur = await self.db.execute(
            "DELETE FROM outbound_queue WHERE acked=1 AND created_at < ?", (cutoff,)
        )
        await self.db.commit()
        return cur.rowcount

    # ── command idempotency ───────────────────────────────────────────────
    async def mark_seen(self, key: str, command_type: str) -> bool:
        """Record a command idempotency key. Returns True if NEW (process it),
        False if already seen (a duplicate to skip)."""
        if not key:
            return True
        try:
            await self.db.execute(
                "INSERT INTO idempotency_seen (key, command_type, seen_at) VALUES (?,?,?)",
                (key, command_type, _now()),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    # ── key/value scratch ─────────────────────────────────────────────────
    async def kv_get(self, k: str) -> Optional[Any]:
        row = await self.fetchone("SELECT v FROM kv WHERE k=?", (k,))
        if row is None:
            return None
        try:
            return json.loads(row["v"])
        except (ValueError, TypeError):
            return row["v"]

    async def kv_set(self, k: str, v: Any) -> None:
        await self.execute(
            "INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, _dumps(v)),
        )


# ── singleton seam ────────────────────────────────────────────────────────
_store: Optional[LocalStore] = None


def get_store() -> LocalStore:
    if _store is None:
        raise RuntimeError("store not initialised; call set_store(...) at startup")
    return _store


def set_store(store: LocalStore) -> None:
    global _store
    _store = store


def reset_store() -> None:  # test helper
    global _store
    _store = None
