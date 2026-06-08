"""run_agent flow: authorize → lineage WAL → async audit → dispatch child run (§2.4).

The orchestrator MCP tool calls :func:`run_agent`. Enforcement is local (the broker);
on ALLOW we append a lineage row, emit ``agent.orchestrate`` upstream (audit/lineage
only), and dispatch a normal local ``agent.run`` for the child carrying the lineage.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from ..logging import get_logger
from ..router import CommandContext, dispatch
from ..uplink import CHANNEL_CONTROL, get_uplink
from .broker import Decision, authorize, grant_for_agent, lineage_append

log = get_logger(__name__)


def _new_run_id() -> str:
    return f"rn_{uuid.uuid4().hex[:16]}"


async def run_agent(
    *,
    caller_run_id: Optional[str],
    caller_agent_id: str,
    daemon_id: str,
    target_agent_id: str,
    prompt_vars: Optional[dict[str, Any]] = None,
    caller_depth: int = 0,
    caller_perms: Optional[Iterable[str]] = None,
    target_perms: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """Spawn a child run of ``target_agent_id`` on this daemon, if the grant allows."""
    grant = await grant_for_agent(caller_agent_id)
    if not grant:
        return {"error": "no orchestration grant for this agent"}

    result = authorize(
        core=grant["core"],
        signature=grant["signature"],
        daemon_id=daemon_id,
        verb="run",
        target_agent_id=target_agent_id,
        caller_depth=caller_depth,
        caller_perms=caller_perms,
        target_perms=target_perms,
    )
    if result.decision is not Decision.ALLOW:
        log.warning("run_agent denied: %s", result.reason)
        return {"error": result.reason, "decision": result.decision.value}

    child_run_id = _new_run_id()
    root_run_id = caller_run_id or child_run_id
    depth = int(caller_depth) + 1
    grant_id = grant["grant_id"]

    await lineage_append(
        parent_run_id=caller_run_id,
        child_run_id=child_run_id,
        root_run_id=root_run_id,
        grant_id=grant_id,
        verb="run",
        depth=depth,
    )

    # Async audit upstream — enforcement already happened locally (§2.7).
    await get_uplink().send(
        "agent.orchestrate",
        {
            "verb": "run",
            "grant_id": grant_id,
            "initiator_agent_id": caller_agent_id,
            "target_agent_id": target_agent_id,
            "child_run_id": child_run_id,
            "parent_run_id": caller_run_id,
            "root_run_id": root_run_id,
            "depth": depth,
        },
        channel=CHANNEL_CONTROL,
    )

    # Start the child run locally via the normal agent.run path, lineage-tagged.
    await dispatch(
        "agent.run",
        CommandContext(command_type="agent.run", daemon_id=daemon_id),
        {
            "run_id": child_run_id,
            "agent_id": target_agent_id,
            "prompt_vars": prompt_vars or {},
            "initiator": "agent",
            "initiator_agent_id": caller_agent_id,
            "root_run_id": root_run_id,
            "parent_run_id": caller_run_id,
            "depth": depth,
        },
    )
    return {"child_run_id": child_run_id, "status": "spawned", "depth": depth}
