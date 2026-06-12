"""Handoff command handlers: cache chain grant / revoke (§11.10).

``app.build_daemon`` auto-imports this module, registering the handlers. The cloud pushes
a signed chain grant (``chain.grant``) which the daemon caches and verifies offline before
each handoff; ``chain.revoke`` drops it. Cancelling running hops reuses §2's
``orchestration.halt`` (handoff hops share the ``orchestration_lineage`` WAL), so no new
halt handler is needed here.
"""
from __future__ import annotations

from typing import Any

from ..handoff.broker import cache_chain_grant, drop_chain_grant
from ..logging import get_logger
from ..router import CommandContext, on_command

log = get_logger(__name__)


@on_command("chain.grant")
async def handle_chain_grant(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Cache a cloud-signed chain grant for offline enforcement."""
    grant_id = payload.get("grant_id")
    core = payload.get("core") if isinstance(payload.get("core"), dict) else None
    if not grant_id or not core:
        log.warning("chain.grant: missing grant_id/core; ignoring")
        return
    await cache_chain_grant(
        grant_id,
        core.get("daemon_id"),
        core.get("flow_id"),
        core,
        payload.get("signature") or "",
        payload.get("public_key"),
    )
    log.info("chain.grant: cached chain grant %s (flow %s)", grant_id, core.get("flow_id"))


@on_command("chain.revoke")
async def handle_chain_revoke(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Drop a cached chain grant (no further handoffs can be authorized by it)."""
    grant_id = payload.get("grant_id")
    if not grant_id:
        return
    await drop_chain_grant(grant_id)
    log.info("chain.revoke: dropped chain grant %s", grant_id)
