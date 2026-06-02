"""``memory.sync`` command (cloud -> daemon, §4.13) + the ``memory_sync`` flush service.

``app.build_daemon`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one (a) registers the ``memory.sync`` ``@on_command`` handler AND (b) registers the
low-priority ``memory_sync`` background service that periodically flushes the local memory
change-journal upstream as ``memory.delta`` frames.

**``memory.sync`` — UI edits/deletes/pre-loads applied to the LOCAL provider** (the source of
truth for the agent), ONE entry op per command::

    {"op": "upsert" | "delete", "agent_id"?, "namespace", "key", "value"?, "text"?, "tags"?}

The ``agent_id`` may be in the payload, on ``ctx.agent_id`` … wait — :class:`CommandContext`
exposes ``daemon_id``/``org_id`` but the per-entry agent is carried in the payload or parsed
from the idempotency key ``memory.sync:{op}:{agent_id}:{namespace}:{key}``.

WHY apply via ``provider.apply_remote`` (not the journalling ``store``/``delete``): a
cloud-originated edit must NOT append a journal row, or :func:`flush_deltas` would re-emit it
as a ``memory.delta`` straight back to the cloud that just sent it (a sync loop). Pre-loading
a dataset before first run uses this same path.

Values still pass through §4.5 redaction on apply — the cloud snapshot is already redacted,
but redact-on-write is an invariant (defence in depth) and ``text`` for vector pre-loads is
sanitized too.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from ..filtering.base import get_filter_chain
from ..logging import get_logger
from ..memory.api import flush_deltas
from ..memory.providers import get_provider
from ..router import CommandContext, on_command
from ..services import register_service

log = get_logger(__name__)

# Default flush cadence for the background sync loop (seconds). Low priority: a simple
# periodic batch flush, never on the agent's hot path.
_FLUSH_INTERVAL_SECONDS = 30.0


def _agent_id_from(ctx: CommandContext, payload: dict[str, Any]) -> Optional[str]:
    """Recover agent_id: payload field, then the idempotency key, then ``ctx``.

    Key shape is ``memory.sync:{op}:{agent_id}:{namespace}:{key}``. The command type itself
    contains a '.', never a ':', and op is a fixed word, so agent_id is parts[2]. Read
    defensively — a garbled/short key just falls through to the next source.
    """
    explicit = payload.get("agent_id")
    if explicit:
        return str(explicit)
    key = ctx.idempotency_key or ""
    parts = key.split(":")
    # ["memory.sync", op, agent_id, namespace, key...]
    if len(parts) >= 5 and parts[0] == "memory.sync" and parts[2]:
        return parts[2]
    return getattr(ctx, "agent_id", None)


def _redact(text: Optional[str]) -> str:
    if not text:
        return ""
    return get_filter_chain().screen_outbound(text).text


@on_command("memory.sync")
async def handle_memory_sync(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Apply one cloud-originated memory edit to the local provider (no re-emit)."""
    op = str(payload.get("op", "upsert")).lower()
    agent_id = _agent_id_from(ctx, payload)
    if not agent_id:
        log.warning("memory.sync: no agent_id (payload/key/ctx); ignoring")
        return

    namespace = str(payload.get("namespace", "default"))
    key = payload.get("key")
    if not key:
        log.warning("memory.sync for %s: missing key; ignoring", agent_id)
        return
    key = str(key)

    provider = get_provider(agent_id)

    if op == "delete":
        await provider.apply_remote(agent_id, "delete", namespace=namespace, key=key)
        log.info("memory.sync: deleted %s/%s for agent %s", namespace, key, agent_id)
        return

    # upsert (covers pre-load). Redact value/text defensively before persisting locally.
    raw_value = payload.get("value")
    if raw_value is None:
        raw_value = payload.get("text")  # vector pre-load datasets use "text"
    value = _redact(str(raw_value)) if raw_value is not None else ""
    tags = payload.get("tags") or []
    await provider.apply_remote(
        agent_id,
        "upsert",
        namespace=namespace,
        key=key,
        value=value,
        tags=list(tags),
    )
    log.info("memory.sync: upserted %s/%s for agent %s", namespace, key, agent_id)


class MemorySyncService:
    """Low-priority loop that periodically flushes the memory journal upstream.

    Non-blocking: a flush batches journalled changes into one ``memory.delta`` telemetry
    frame and marks rows synced. Sleeps between flushes so it never competes with the hot
    path. Stops cleanly on cancellation / ``stop()``.
    """

    def __init__(self, daemon: Any, interval: float = _FLUSH_INTERVAL_SECONDS) -> None:
        self._daemon = daemon
        self._interval = interval
        self._stop = asyncio.Event()

    async def run(self) -> None:
        log.debug("memory_sync service started (interval=%ss)", self._interval)
        while not self._stop.is_set():
            try:
                await flush_deltas()
            except Exception:  # noqa: BLE001 - a flush failure must not kill the loop
                log.exception("memory.delta flush failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue

    async def stop(self) -> None:
        self._stop.set()


@register_service("memory_sync")
def make_memory_sync(daemon) -> MemorySyncService:  # (Daemon) -> service with async run()/stop()
    return MemorySyncService(daemon)
