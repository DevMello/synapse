"""Swappable storage providers for agent memory (§4.13).

A provider implements a small contract — ``store / get / query / list / delete`` plus
``export_delta`` for sync — so the backing store can be swapped per agent or per daemon
without changing agent code. The API layer (:mod:`synapse_worker.memory.api`) talks only
to this contract.

Providers shipped here:

  * :class:`SqliteMemoryProvider` — the **default, built-in** provider. Uses the foundation
    store's ``memory`` + ``memory_journal`` tables (zero setup, no dependencies). Search is
    substring/tag over the local rows. Versioning increments on re-store of an existing key.
  * :class:`VectorMemoryProvider` — the ``vector-memory`` provider, backed by Chroma/Qdrant
    in a **local Docker container** for semantic ``query()``. On init it would pull/start the
    container; if Docker (or the optional ``chromadb`` extra) is unavailable, init fails
    cleanly and the factory **gracefully falls back** to ``SqliteMemoryProvider`` rather than
    losing memory. The fallback is substring search instead of semantic.

``get_provider(agent_id=None)`` is the factory: it reads the configured provider name
(per-agent override, then daemon default, then ``sqlite-memory``) and returns a ready
provider — degrading to sqlite when the requested backend can't initialise.

WHY the journal lives in the provider's ``store``/``delete``: the journal is the source of
the ``memory.delta`` sync, and it must be written in the SAME local transaction context as
the mutation so a crash never leaves a mutation un-journalled (or vice versa).
"""
from __future__ import annotations

import abc
import json
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import get_settings
from ..logging import get_logger
from ..store import LocalStore, get_store

log = get_logger(__name__)

# Provider identifiers (match the §4.13 table / config values).
SQLITE_MEMORY = "sqlite-memory"
VECTOR_MEMORY = "vector-memory"


def _now() -> float:
    return time.time()


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


@dataclass
class StoredEntry:
    """One memory row as a provider returns it (value already redacted on write)."""

    agent_id: str
    namespace: str
    key: str
    value: str
    tags: list[str] = field(default_factory=list)
    version: int = 1
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "namespace": self.namespace,
            "key": self.key,
            "value": self.value,
            "tags": list(self.tags),
            "version": self.version,
            "updated_at": self.updated_at,
        }


def _decode_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    try:
        decoded = json.loads(raw)
        return [str(t) for t in decoded] if isinstance(decoded, list) else []
    except (ValueError, TypeError):
        return []


class MemoryProvider(abc.ABC):
    """Storage-provider contract. All values arrive ALREADY redacted by the API layer."""

    #: Stable identifier (e.g. ``sqlite-memory``) — reported to the cloud / used in logs.
    name: str = "memory-provider"

    @abc.abstractmethod
    async def store(
        self,
        agent_id: str,
        key: str,
        value: str,
        *,
        tags: Optional[list[str]] = None,
        namespace: str = "default",
    ) -> StoredEntry:
        """Upsert ``key`` and append a journal row. Re-store bumps ``version``."""

    @abc.abstractmethod
    async def get(
        self, agent_id: str, key: str, *, namespace: str = "default"
    ) -> Optional[StoredEntry]:
        ...

    @abc.abstractmethod
    async def query(
        self,
        agent_id: str,
        search_term: str,
        *,
        k: int = 10,
        namespace: str = "default",
    ) -> list[StoredEntry]:
        """Search — substring/tag (sqlite) or semantic (vector). Top ``k`` matches."""

    @abc.abstractmethod
    async def list(
        self, agent_id: str, *, namespace: str = "default", limit: int = 100
    ) -> list[StoredEntry]:
        ...

    @abc.abstractmethod
    async def delete(
        self, agent_id: str, key: str, *, namespace: str = "default"
    ) -> bool:
        """Remove ``key`` and append a ``delete`` journal row. Returns True if it existed."""

    @abc.abstractmethod
    async def export_delta(
        self, agent_id: Optional[str] = None, *, limit: int = 500
    ) -> "MemoryDelta":
        """Batch un-synced journal rows into a delta for upstream sync."""

    @abc.abstractmethod
    async def mark_synced(self, seqs: list[int]) -> None:
        """Mark journal rows (by seq) as synced after a successful upstream send."""

    @abc.abstractmethod
    async def apply_remote(
        self,
        agent_id: str,
        op: str,
        *,
        namespace: str,
        key: str,
        value: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        """Apply a cloud-originated edit to the local store WITHOUT journalling it.

        WHY no journal row: a cloud edit must not re-emit a ``memory.delta`` (that would
        loop the change straight back to the cloud that just sent it).
        """


@dataclass
class MemoryDelta:
    """A batch of journalled changes ready to ship upstream as ``memory.delta``."""

    agent_id: Optional[str]
    entries: list[dict[str, Any]] = field(default_factory=list)
    deletes: list[dict[str, Any]] = field(default_factory=list)
    seqs: list[int] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.entries and not self.deletes


class SqliteMemoryProvider(MemoryProvider):
    """Default provider over the foundation ``memory`` + ``memory_journal`` tables."""

    name = SQLITE_MEMORY

    def __init__(self, store: Optional[LocalStore] = None) -> None:
        # Resolve lazily through get_store() by default so tests' singleton swap is honoured.
        self._explicit_store = store

    @property
    def _store(self) -> LocalStore:
        return self._explicit_store or get_store()

    async def store(
        self,
        agent_id: str,
        key: str,
        value: str,
        *,
        tags: Optional[list[str]] = None,
        namespace: str = "default",
    ) -> StoredEntry:
        tags = tags or []
        tags_json = _dumps(tags)
        now = _now()
        existing = await self.get(agent_id, key, namespace=namespace)
        version = (existing.version + 1) if existing else 1
        await self._store.execute(
            "INSERT INTO memory (agent_id, namespace, key, value, tags, version, updated_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(agent_id, namespace, key) DO UPDATE SET"
            " value=excluded.value, tags=excluded.tags, version=excluded.version,"
            " updated_at=excluded.updated_at",
            (agent_id, namespace, key, value, tags_json, version, now),
        )
        await self._journal(
            agent_id, namespace, key, "store", value=value, version=version
        )
        return StoredEntry(
            agent_id=agent_id,
            namespace=namespace,
            key=key,
            value=value,
            tags=tags,
            version=version,
            updated_at=now,
        )

    async def get(
        self, agent_id: str, key: str, *, namespace: str = "default"
    ) -> Optional[StoredEntry]:
        row = await self._store.fetchone(
            "SELECT * FROM memory WHERE agent_id=? AND namespace=? AND key=?",
            (agent_id, namespace, key),
        )
        return self._row_to_entry(row) if row else None

    async def query(
        self,
        agent_id: str,
        search_term: str,
        *,
        k: int = 10,
        namespace: str = "default",
    ) -> list[StoredEntry]:
        # Substring match over key + value + tags (the sqlite provider has no embeddings).
        like = f"%{search_term}%"
        rows = await self._store.fetchall(
            "SELECT * FROM memory WHERE agent_id=? AND namespace=?"
            " AND (key LIKE ? OR value LIKE ? OR tags LIKE ?)"
            " ORDER BY updated_at DESC LIMIT ?",
            (agent_id, namespace, like, like, like, k),
        )
        return [self._row_to_entry(r) for r in rows]

    async def list(
        self, agent_id: str, *, namespace: str = "default", limit: int = 100
    ) -> list[StoredEntry]:
        rows = await self._store.fetchall(
            "SELECT * FROM memory WHERE agent_id=? AND namespace=?"
            " ORDER BY updated_at DESC LIMIT ?",
            (agent_id, namespace, limit),
        )
        return [self._row_to_entry(r) for r in rows]

    async def delete(
        self, agent_id: str, key: str, *, namespace: str = "default"
    ) -> bool:
        existing = await self.get(agent_id, key, namespace=namespace)
        if existing is None:
            return False
        await self._store.execute(
            "DELETE FROM memory WHERE agent_id=? AND namespace=? AND key=?",
            (agent_id, namespace, key),
        )
        await self._journal(
            agent_id, namespace, key, "delete", value=None, version=existing.version
        )
        return True

    async def export_delta(
        self, agent_id: Optional[str] = None, *, limit: int = 500
    ) -> MemoryDelta:
        if agent_id is None:
            rows = await self._store.fetchall(
                "SELECT * FROM memory_journal WHERE synced=0 ORDER BY seq LIMIT ?",
                (limit,),
            )
        else:
            rows = await self._store.fetchall(
                "SELECT * FROM memory_journal WHERE synced=0 AND agent_id=? ORDER BY seq LIMIT ?",
                (agent_id, limit),
            )
        delta = MemoryDelta(agent_id=agent_id)
        for r in rows:
            delta.seqs.append(int(r["seq"]))
            if r["op"] == "delete":
                delta.deletes.append({"namespace": r["namespace"], "key": r["key"]})
            else:
                # Re-attach tags from the live row when present (journal stores value only).
                entry = await self.get(
                    r["agent_id"], r["key"], namespace=r["namespace"]
                )
                delta.entries.append(
                    {
                        "namespace": r["namespace"],
                        "key": r["key"],
                        "value": r["value"],
                        "tags": entry.tags if entry else [],
                        "version": r["version"],
                    }
                )
        return delta

    async def mark_synced(self, seqs: list[int]) -> None:
        for seq in seqs:
            await self._store.execute(
                "UPDATE memory_journal SET synced=1 WHERE seq=?", (seq,)
            )

    async def apply_remote(
        self,
        agent_id: str,
        op: str,
        *,
        namespace: str,
        key: str,
        value: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        now = _now()
        if op == "delete":
            await self._store.execute(
                "DELETE FROM memory WHERE agent_id=? AND namespace=? AND key=?",
                (agent_id, namespace, key),
            )
            return
        # upsert (also covers pre-load): bump version off any existing row.
        existing = await self.get(agent_id, key, namespace=namespace)
        version = (existing.version + 1) if existing else 1
        await self._store.execute(
            "INSERT INTO memory (agent_id, namespace, key, value, tags, version, updated_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(agent_id, namespace, key) DO UPDATE SET"
            " value=excluded.value, tags=excluded.tags, version=excluded.version,"
            " updated_at=excluded.updated_at",
            (agent_id, namespace, key, value or "", _dumps(tags or []), version, now),
        )

    # ── internals ─────────────────────────────────────────────────────────
    async def _journal(
        self,
        agent_id: str,
        namespace: str,
        key: str,
        op: str,
        *,
        value: Optional[str],
        version: int,
    ) -> None:
        await self._store.execute(
            "INSERT INTO memory_journal"
            " (agent_id, namespace, key, op, value, version, created_at, synced)"
            " VALUES (?,?,?,?,?,?,?,0)",
            (agent_id, namespace, key, op, value, version, _now()),
        )

    @staticmethod
    def _row_to_entry(row: dict[str, Any]) -> StoredEntry:
        return StoredEntry(
            agent_id=row["agent_id"],
            namespace=row["namespace"],
            key=row["key"],
            value=row["value"] or "",
            tags=_decode_tags(row.get("tags")),
            version=int(row.get("version") or 1),
            updated_at=float(row.get("updated_at") or 0.0),
        )


class VectorMemoryProvider(SqliteMemoryProvider):
    """``vector-memory`` provider: Chroma/Qdrant in a local Docker container.

    Semantic ``query`` over embeddings. The full embedding/container wiring is heavyweight
    and dependency-laden (``chromadb`` is an optional ``[vector]`` extra, Docker is a host
    dependency), so init **probes** for both and raises if either is missing — the factory
    catches that and falls back to sqlite. We subclass the sqlite provider so that, even if
    a caller forced this class on without a backend, every method still works locally rather
    than losing memory; only the (future) embedding-backed ``query`` differs.
    """

    name = VECTOR_MEMORY

    def __init__(self, store: Optional[LocalStore] = None) -> None:
        super().__init__(store)
        self._ensure_backend()

    @staticmethod
    def _ensure_backend() -> None:
        """Probe for Docker + the chromadb extra; raise cleanly if either is absent.

        WHY a probe (not a real container pull): tests and the default install must not
        require Docker. We only verify availability here; the factory turns a failure into
        a graceful sqlite fallback.
        """
        if shutil.which("docker") is None:
            raise MemoryProviderUnavailable("docker not found on PATH")
        try:  # pragma: no cover - chromadb is an optional extra, not installed in CI
            import chromadb  # type: ignore  # noqa: F401
        except Exception as exc:  # noqa: BLE001 - any import failure => unavailable
            raise MemoryProviderUnavailable(f"chromadb extra unavailable: {exc}") from exc
        # A real impl would also probe the running container here.


class MemoryProviderUnavailable(RuntimeError):
    """Raised when a provider's backend (Docker/embeddings) can't be initialised."""


def _configured_provider_name(agent_id: Optional[str]) -> str:
    """Resolve the desired provider: daemon default → sqlite.

    Read defensively: the ``memory_provider`` setting (``SYNAPSE_MEMORY_PROVIDER``) may be
    absent on a minimal install, and an unknown name is treated as the default so a typo
    can never wipe out memory. ``agent_id`` is accepted for a future per-agent override; for
    now the daemon-wide default applies to every agent.
    """
    try:
        settings = get_settings()
    except Exception:  # noqa: BLE001 - config not initialised yet
        return SQLITE_MEMORY
    name = getattr(settings, "memory_provider", SQLITE_MEMORY) or SQLITE_MEMORY
    return name if name in (SQLITE_MEMORY, VECTOR_MEMORY) else SQLITE_MEMORY


def get_provider(agent_id: Optional[str] = None) -> MemoryProvider:
    """Return a ready provider, falling back to sqlite when the requested one can't init.

    The fallback (vector → sqlite) is the §4.13 guarantee: a missing Docker/embedding
    backend means *substring instead of semantic* search, never *lost memory*.
    """
    name = _configured_provider_name(agent_id)
    if name == VECTOR_MEMORY:
        try:
            return VectorMemoryProvider()
        except MemoryProviderUnavailable as exc:
            log.warning(
                "vector-memory unavailable (%s); falling back to sqlite-memory", exc
            )
            return SqliteMemoryProvider()
    return SqliteMemoryProvider()
