"""Built-in agent memory API — the provider-agnostic surface every agent gets (§4.13).

The same five calls work regardless of the backing store (sqlite key/value or a vector DB):

    memory.store(agent_id, key, value, *, tags=[], namespace="default")
    memory.query(agent_id, search_term, *, k=10, namespace="default")
    memory.get(agent_id, key, *, namespace="default")
    memory.list(agent_id, *, namespace="default", limit=100)
    memory.delete(agent_id, key, *, namespace="default")

Two ways it's surfaced:
  * to **API agents** — programmatically, as :func:`get_memory` / a :class:`MemoryAPI` object;
  * to **CLI / tool agents** — via the built-in ``memory`` MCP server
    (:mod:`synapse_worker.memory.mcp_server`), one of the default capabilities.

**Redaction guarantee (§4.5 / §4.13 trust boundary):** memory is NOT E2E-encrypted — the
cloud stores redacted plaintext. So every value is run through the §4.5 Layer-A filter chain
(``get_filter_chain().screen_outbound``) BEFORE it is persisted or journalled. On-device
redaction is the guarantee that no raw secret leaves the machine, on write or later on sync.

**Local-first + sync-on-demand:** ``store``/``delete`` mutate the local provider immediately
and append a journal row. :func:`flush_deltas` batches the journal into a ``memory.delta``
upstream frame on the telemetry channel and marks the rows synced — a periodic, non-blocking
background flush (the ``memory_sync`` service), never a per-access cloud round-trip.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..filtering.base import get_filter_chain
from ..logging import get_logger
from ..uplink import CHANNEL_TELEMETRY, get_uplink
from .providers import MemoryProvider, StoredEntry, get_provider

log = get_logger(__name__)


@dataclass
class MemoryEntry:
    """A memory entry as returned to an agent (value is the redacted, persisted form)."""

    key: str
    value: str
    tags: list[str]
    namespace: str
    version: int
    updated_at: float

    @classmethod
    def from_stored(cls, e: StoredEntry) -> "MemoryEntry":
        return cls(
            key=e.key,
            value=e.value,
            tags=list(e.tags),
            namespace=e.namespace,
            version=e.version,
            updated_at=e.updated_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "tags": list(self.tags),
            "namespace": self.namespace,
            "version": self.version,
            "updated_at": self.updated_at,
        }


def _redact(text: str) -> str:
    """Run a value through §4.5 Layer A so secrets/PII are stripped before persist/sync.

    A blocked field (block-mode redaction) yields empty text — the secret is dropped, which
    is the safe outcome for a not-E2E-encrypted store. Always returns a plain string.
    """
    if not text:
        return text
    result = get_filter_chain().screen_outbound(text)
    return result.text


class MemoryAPI:
    """The agent-facing memory object. Bound to a provider (default: factory-selected)."""

    def __init__(self, provider: Optional[MemoryProvider] = None) -> None:
        # Default provider is resolved lazily per-call when none is injected, so the
        # configured backend (and the test singleton) is honoured at call time.
        self._provider = provider

    def _resolve(self, agent_id: Optional[str] = None) -> MemoryProvider:
        return self._provider or get_provider(agent_id)

    async def store(
        self,
        agent_id: str,
        key: str,
        value: str,
        *,
        tags: Optional[list[str]] = None,
        namespace: str = "default",
    ) -> MemoryEntry:
        """Redact + persist locally + journal for sync. Returns the stored entry."""
        redacted = _redact(str(value))
        provider = self._resolve(agent_id)
        entry = await provider.store(
            agent_id, key, redacted, tags=tags or [], namespace=namespace
        )
        return MemoryEntry.from_stored(entry)

    async def query(
        self,
        agent_id: str,
        search_term: str,
        *,
        k: int = 10,
        namespace: str = "default",
    ) -> list[MemoryEntry]:
        provider = self._resolve(agent_id)
        rows = await provider.query(
            agent_id, search_term, k=k, namespace=namespace
        )
        return [MemoryEntry.from_stored(r) for r in rows]

    async def get(
        self, agent_id: str, key: str, *, namespace: str = "default"
    ) -> Optional[MemoryEntry]:
        provider = self._resolve(agent_id)
        entry = await provider.get(agent_id, key, namespace=namespace)
        return MemoryEntry.from_stored(entry) if entry else None

    async def list(
        self, agent_id: str, *, namespace: str = "default", limit: int = 100
    ) -> list[MemoryEntry]:
        provider = self._resolve(agent_id)
        rows = await provider.list(agent_id, namespace=namespace, limit=limit)
        return [MemoryEntry.from_stored(r) for r in rows]

    async def delete(
        self, agent_id: str, key: str, *, namespace: str = "default"
    ) -> bool:
        provider = self._resolve(agent_id)
        return await provider.delete(agent_id, key, namespace=namespace)


_memory: Optional[MemoryAPI] = None


def get_memory() -> MemoryAPI:
    """The shared memory API object surfaced to agents and the ``memory`` MCP server."""
    global _memory
    if _memory is None:
        _memory = MemoryAPI()
    return _memory


def reset_memory() -> None:  # test helper
    global _memory
    _memory = None


async def flush_deltas(agent_id: Optional[str] = None, *, limit: int = 500) -> int:
    """Ship journalled local changes upstream as a ``memory.delta`` frame.

    Batches un-synced journal rows into entries + deletes, sends ONE telemetry frame, and
    marks those rows synced. Values are already redacted at write time (§4.5), so the delta
    carries only sanitized text. Returns the number of journal rows flushed (0 = nothing new,
    so no frame is sent — a second flush after the first is a no-op).

    Kept non-blocking and idempotent so the ``memory_sync`` periodic service can call it
    without holding up the hot path; a cloud-originated edit does not journal, so it is
    never re-emitted here (no sync loop).
    """
    provider = get_provider(agent_id)
    delta = await provider.export_delta(agent_id, limit=limit)
    if delta.is_empty():
        return 0

    payload: dict[str, Any] = {
        "agent_id": delta.agent_id,
        "entries": delta.entries,
        "deletes": delta.deletes,
    }
    await get_uplink().send("memory.delta", payload, channel=CHANNEL_TELEMETRY)
    await provider.mark_synced(delta.seqs)
    log.debug(
        "memory.delta flushed: %d entries, %d deletes",
        len(delta.entries),
        len(delta.deletes),
    )
    return len(delta.seqs)
