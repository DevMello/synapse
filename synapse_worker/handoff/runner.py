"""handoff flow: authorize → redact envelope → lineage WAL → async audit → start
successor (§11.7). The ``handoff`` MCP tool calls :func:`handoff`. Enforcement is local
(the broker); on ALLOW we redact + bound the context envelope (H4), append a lineage row
(reusing §2's ``orchestration_lineage`` so ``orchestration.halt`` cancels chains too),
emit ``agent.handoff`` upstream (audit/lineage only), and start the successor run carrying
the same ``root_run_id`` — the unified Trace ID (H5).

Tail mode (default): the caller completes and the successor takes over. Return mode is
recorded the same way; the runtime resumes the caller on the successor's completion.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from ..filtering.base import Direction
from ..filtering.redaction import RedactionFilter
from ..logging import get_logger
from ..orchestrator.broker import lineage_append  # reuse the shared lineage WAL
from ..router import CommandContext, dispatch
from ..uplink import CHANNEL_CONTROL, get_uplink
from .broker import Decision, authorize_handoff, grant_for_edge

log = get_logger(__name__)

# Envelope fields carried A→B (§11.5), each redacted before leaving A.
_TEXT_FIELDS = ("task", "summary")


def _new_run_id() -> str:
    return f"rn_{uuid.uuid4().hex[:16]}"


def redact_envelope(context: dict[str, Any]) -> dict[str, Any]:
    """Screen the handoff envelope through Layer A (H4) before it leaves A.

    Raw secrets never ride a handoff; B resolves its own vault entries. Returns a new
    envelope with ``task``/``summary``/``artifacts`` redacted.
    """
    flt = RedactionFilter()
    out: dict[str, Any] = {}
    for k, v in context.items():
        if k in _TEXT_FIELDS and isinstance(v, str):
            out[k] = flt.screen(v, direction=Direction.OUTBOUND).text
        elif k == "artifacts":
            # Artifacts may be inline strings or refs; redact any inline string content.
            arts = v if isinstance(v, list) else [v]
            out[k] = [
                flt.screen(a, direction=Direction.OUTBOUND).text if isinstance(a, str) else a
                for a in arts
            ]
        else:
            out[k] = v
    return out


def envelope_bytes(envelope: dict[str, Any]) -> int:
    return len(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def payload_hash(envelope: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


async def handoff(
    *,
    caller_run_id: Optional[str],
    from_agent_id: str,
    daemon_id: str,
    to_agent_id: str,
    context: Optional[dict[str, Any]] = None,
    mode: str = "tail",
    caller_hop: int = 0,
    chain_cost_usd: float = 0.0,
) -> dict[str, Any]:
    """Pass the current task to ``to_agent_id`` along a pre-approved edge, if the grant allows."""
    grant = await grant_for_edge(from_agent_id, to_agent_id)
    if not grant:
        return {"error": "no chain grant authorizes this handoff edge"}

    core = grant["core"]
    result = authorize_handoff(
        core=core,
        signature=grant["signature"],
        daemon_id=daemon_id,
        from_agent_id=from_agent_id,
        to_agent_id=to_agent_id,
        mode=mode,
        hop=caller_hop,
        chain_cost_usd=chain_cost_usd,
    )
    if result.decision is not Decision.ALLOW:
        log.warning("handoff denied: %s", result.reason)
        return {"error": result.reason, "decision": result.decision.value}

    # Redact + bound the envelope (H4). Reject anything over the grant's cap.
    envelope = redact_envelope(context or {})
    max_bytes = int(core.get("max_payload_bytes", 0))
    if max_bytes and envelope_bytes(envelope) > max_bytes:
        return {"error": "handoff payload exceeds max_payload_bytes", "decision": "deny"}

    child_run_id = _new_run_id()
    root_run_id = caller_run_id or child_run_id
    hop = int(caller_hop) + 1
    grant_id = grant["grant_id"]
    flow_id = core.get("flow_id")
    phash = payload_hash(envelope)

    await lineage_append(
        parent_run_id=caller_run_id,
        child_run_id=child_run_id,
        root_run_id=root_run_id,
        grant_id=grant_id,
        verb="handoff",
        depth=hop,
    )

    # Async audit upstream — enforcement already happened locally (§11.10).
    await get_uplink().send(
        "agent.handoff",
        {
            "grant_id": grant_id,
            "flow_id": flow_id,
            "mode": mode,
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "child_run_id": child_run_id,
            "parent_run_id": caller_run_id,
            "root_run_id": root_run_id,
            "hop": hop,
            "payload_hash": phash,
        },
        channel=CHANNEL_CONTROL,
    )

    # Start the successor run locally via the normal agent.run path, lineage-tagged.
    # Tail: the caller run completes and B takes over the SAME root run. Return mode is
    # recorded identically; the runtime resumes the caller when B completes.
    await dispatch(
        "agent.run",
        CommandContext(command_type="agent.run", daemon_id=daemon_id),
        {
            "run_id": child_run_id,
            "agent_id": to_agent_id,
            "prompt_vars": {"handoff": envelope},
            "initiator": "agent",
            "initiator_agent_id": from_agent_id,
            "root_run_id": root_run_id,
            "parent_run_id": caller_run_id,
            "depth": hop,
            "hop": hop,
            "handoff_mode": mode,
            "flow_id": flow_id,
        },
    )
    return {
        "child_run_id": child_run_id,
        "status": "handed_off",
        "mode": mode,
        "hop": hop,
        "payload_hash": phash,
    }
