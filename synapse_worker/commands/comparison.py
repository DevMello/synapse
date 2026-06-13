"""Comparison command handlers: launch / cancel a model-comparison group (§10.11).

``app.build_daemon`` auto-imports this module, registering the handlers. The cloud pushes a
plain ``agent.compare`` (NO signed grant — §10.4 is a human-driven evaluation tool, not a new
principal) which launches the group executor on a background task so the control loop acks
promptly. ``comparison.cancel`` stops all in-flight variants of a group.
"""
from __future__ import annotations

import asyncio
from typing import Any

from ..comparison.executor import cancel_group, run_group
from ..logging import get_logger
from ..router import CommandContext, on_command

log = get_logger(__name__)

# group_id -> the launcher task, so a late cancel can also stop the fan-out coroutine itself.
_launches: dict[str, asyncio.Task] = {}


@on_command("agent.compare")
async def handle_compare(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Launch a model-comparison run group (fire-and-forget on a background task)."""
    group_id = payload.get("group_id")
    agent_id = payload.get("agent_id")
    models = payload.get("models")
    if not group_id or not agent_id or not isinstance(models, list) or not models:
        log.warning("agent.compare: missing group_id/agent_id/models; ignoring")
        return

    async def _run() -> None:
        try:
            await run_group(
                group_id=group_id,
                agent_id=agent_id,
                daemon_id=ctx.daemon_id or "",
                models=models,
                input=payload.get("input") if isinstance(payload.get("input"), dict) else {},
                group_cost_cap=_as_float(payload.get("group_cost_cap")),
                max_parallel_variants=int(payload.get("max_parallel_variants") or 3),
            )
        finally:
            _launches.pop(group_id, None)

    _launches[group_id] = asyncio.create_task(_run())
    log.info("agent.compare: launched group %s (%d models)", group_id, len(models))


@on_command("comparison.cancel")
async def handle_compare_cancel(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Cancel all variants of a comparison group."""
    group_id = payload.get("group_id")
    if not group_id:
        log.warning("comparison.cancel: missing group_id; ignoring")
        return
    await cancel_group(group_id)
    task = _launches.pop(group_id, None)
    if task is not None and not task.done():
        task.cancel()


def _as_float(value: Any) -> Any:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
