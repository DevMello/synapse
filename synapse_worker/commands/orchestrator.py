"""Orchestration command handlers: cache grant / revoke / halt (§2.7).

``app.build_daemon`` auto-imports this module, registering the handlers. The cloud
pushes a signed grant (``orchestration.grant``) which the daemon caches and verifies
offline before each call; ``grant.revoke`` drops it and ``orchestration.halt`` cancels
the orchestration tree.
"""
from __future__ import annotations

from typing import Any

from ..logging import get_logger
from ..orchestrator.broker import cache_grant, drop_grant, lineage_update
from ..router import CommandContext, dispatch, on_command
from ..store import get_store

log = get_logger(__name__)


@on_command("orchestration.grant")
async def handle_grant(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Cache a cloud-signed orchestration grant for offline enforcement."""
    grant_id = payload.get("grant_id")
    core = payload.get("core") if isinstance(payload.get("core"), dict) else None
    if not grant_id or not core:
        log.warning("orchestration.grant: missing grant_id/core; ignoring")
        return
    await cache_grant(
        grant_id,
        core.get("agent_id"),
        core,
        payload.get("signature") or "",
        payload.get("public_key"),
    )
    log.info("orchestration.grant: cached grant %s for agent %s", grant_id, core.get("agent_id"))


@on_command("grant.revoke")
async def handle_revoke(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Drop a cached grant (the orchestrator can no longer authorize new calls)."""
    grant_id = payload.get("grant_id")
    if not grant_id:
        return
    await drop_grant(grant_id)
    log.info("grant.revoke: dropped grant %s", grant_id)


@on_command("orchestration.halt")
async def handle_halt(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Cancel a grant's (or a root's) running orchestration tree."""
    grant_id = payload.get("grant_id")
    root_run_id = payload.get("root_run_id")
    if not grant_id and not root_run_id:
        return

    if grant_id:
        rows = await get_store().fetchall(
            "SELECT child_run_id FROM orchestration_lineage WHERE grant_id=? AND status='running'",
            (grant_id,),
        )
    else:
        rows = await get_store().fetchall(
            "SELECT child_run_id FROM orchestration_lineage WHERE root_run_id=? AND status='running'",
            (root_run_id,),
        )

    for r in rows:
        child = r["child_run_id"]
        await dispatch(
            "agent.cancel",
            CommandContext(command_type="agent.cancel", daemon_id=ctx.daemon_id),
            {"run_id": child},
        )
        await lineage_update(child, "halted")
    log.info("orchestration.halt: halted %d run(s)", len(rows))
