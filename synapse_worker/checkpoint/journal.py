"""Write-ahead checkpoint journal over the local ``checkpoints`` table (§4.12).

A checkpoint is a monotonically-numbered snapshot of one run's *session state*. The
journal is append-only: each ``append`` writes a new row with ``seq = max(seq)+1`` for
that run, so the table is an ordered, replayable history.

The write-ahead protocol the runtime drives around a tool call:

  1. **Before** executing a tool call, append the ``intent`` (+ idempotency key) with
     status ``in_flight`` and commit — so a crash mid-tool is detectable on resume.
  2. Execute the tool.
  3. **After** it returns, append the ``result`` with status ``committed`` and the
     advanced step cursor.

This file owns *only* the durable table mechanics. The resume *decisions* (skip / re-run
/ gate) and cloud sync live in :mod:`recovery` so the journal stays a thin, testable
storage layer.

The ``checkpoints`` table is defined in ``store.py`` (PK ``run_id, seq``); we never
re-create or alter it here — we only read/write rows.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from ..logging import get_logger
from ..store import LocalStore, get_store

log = get_logger(__name__)

# Tool-call lifecycle statuses (§4.12: pending -> in_flight -> committed).
STATUS_PENDING = "pending"
STATUS_IN_FLIGHT = "in_flight"
STATUS_COMMITTED = "committed"


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


class CheckpointJournal:
    """Append-only, per-run write-ahead journal over the ``checkpoints`` table.

    Stateless apart from the store handle: ``seq`` is derived from the table on every
    append (``MAX(seq)+1``) so two callers never have to coordinate a counter, and a
    crash between rows leaves a consistent, gap-free-from-the-table's-view history.
    """

    def __init__(self, store: Optional[LocalStore] = None) -> None:
        # Resolve lazily by default so a journal constructed before the store singleton
        # is installed (e.g. at import time) still works once the daemon boots.
        self._store = store

    @property
    def store(self) -> LocalStore:
        return self._store if self._store is not None else get_store()

    # ── write path ────────────────────────────────────────────────────────────
    async def append(
        self,
        run_id: str,
        step_cursor: int,
        status: str,
        payload: dict[str, Any],
    ) -> int:
        """Append one checkpoint row for ``run_id`` and return its assigned ``seq``.

        ``seq`` is monotonic per run (``MAX(seq)+1``). The whole insert is a single
        committed statement so the row is durable the moment ``append`` returns.
        """
        # Compute the next seq inside the same connection. We don't wrap this in an
        # explicit transaction because the daemon uses one serialized connection; the
        # SELECT-then-INSERT can't interleave with another append for the same run.
        row = await self.store.fetchone(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM checkpoints WHERE run_id=?",
            (run_id,),
        )
        seq = int(row["m"]) + 1 if row else 1
        await self.store.execute(
            "INSERT INTO checkpoints (run_id, seq, step_cursor, status, payload, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (run_id, seq, step_cursor, status, _dumps(payload), time.time()),
        )
        # Never log raw payload — session state can hold sensitive memory (§4.12 / §4.5).
        log.debug(
            "checkpoint append run=%s seq=%s cursor=%s status=%s",
            run_id,
            seq,
            step_cursor,
            status,
        )
        return seq

    async def append_at(
        self,
        run_id: str,
        seq: int,
        step_cursor: int,
        status: str,
        payload: dict[str, Any],
    ) -> int:
        """Insert a checkpoint at an *explicit* ``seq`` (used by cloud recovery restore).

        ``run.recover`` restores a last-known-good checkpoint that already carries its
        own seq from the originating daemon; we preserve it (idempotent upsert) instead of
        renumbering, so reconcile/dedupe stay aligned with the cloud's view.
        """
        await self.store.execute(
            "INSERT INTO checkpoints (run_id, seq, step_cursor, status, payload, created_at)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(run_id, seq) DO UPDATE SET"
            "   step_cursor=excluded.step_cursor, status=excluded.status,"
            "   payload=excluded.payload, created_at=excluded.created_at",
            (run_id, seq, step_cursor, status, _dumps(payload), time.time()),
        )
        return seq

    # ── read path ─────────────────────────────────────────────────────────────
    async def latest(self, run_id: str) -> Optional[dict[str, Any]]:
        """The highest-seq checkpoint row for ``run_id`` (payload decoded), or ``None``."""
        row = await self.store.fetchone(
            "SELECT * FROM checkpoints WHERE run_id=? ORDER BY seq DESC LIMIT 1",
            (run_id,),
        )
        return _decode(row)

    async def history(self, run_id: str) -> list[dict[str, Any]]:
        """All checkpoint rows for ``run_id`` in seq order (payloads decoded)."""
        rows = await self.store.fetchall(
            "SELECT * FROM checkpoints WHERE run_id=? ORDER BY seq ASC",
            (run_id,),
        )
        return [_decode(r) for r in rows if r is not None]  # type: ignore[misc]

    async def latest_seq(self, run_id: str) -> int:
        """Highest seq for ``run_id``, or 0 if the run has no checkpoints yet."""
        row = await self.store.fetchone(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM checkpoints WHERE run_id=?",
            (run_id,),
        )
        return int(row["m"]) if row else 0

    async def since(self, run_id: str, after_seq: int) -> list[dict[str, Any]]:
        """Checkpoints with ``seq > after_seq`` (the incremental cloud-sync delta)."""
        rows = await self.store.fetchall(
            "SELECT * FROM checkpoints WHERE run_id=? AND seq>? ORDER BY seq ASC",
            (run_id, after_seq),
        )
        return [_decode(r) for r in rows if r is not None]  # type: ignore[misc]


def _decode(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Decode the JSON ``payload`` column back to a dict; tolerate corrupt rows."""
    if row is None:
        return None
    raw = row.get("payload")
    try:
        row["payload"] = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        row["payload"] = {}
    return row
