"""``hitl.resolve`` command handler (§4.2 / §4.7).

The cloud delivers an approve/deny decision for a paused run here. ``app.build_daemon``
auto-imports this module, registering the ``@on_command("hitl.resolve")`` handler.

Payload shape (the cloud is the wire source of truth; read it defensively so a renamed
or missing field degrades gracefully instead of crashing the control loop)::

    {
      "hitl_id":  "<cloud id>",          # opaque cloud id; we correlate by run_id
      "run_id":   "<run id>",            # REQUIRED — the correlation key
      "decision": "approve" | "deny",
      "reason":   "<str>",
      "actor":    "<who decided>"        # optional
    }

Correlation: the daemon never learned the cloud's ``hitl_id`` when it sent the request,
so we look the pending gate up by ``run_id`` (a run has at most one open gate). If a gate
is found, its awaiting Future is resolved (the runtime unblocks). If none matches —
already resolved or timed out — we still update the ``hitl_state`` row for audit and
return; the handler is fully idempotent and never raises out.
"""
from __future__ import annotations

import time
from typing import Any

from ..hitl import get_gatekeeper
from ..logging import get_logger
from ..router import CommandContext, on_command
from ..store import get_store

log = get_logger(__name__)


@on_command("hitl.resolve")
async def handle_hitl_resolve(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Deliver the cloud's decision to the paused run, correlated by ``run_id``."""
    run_id = payload.get("run_id")
    if not run_id:
        log.warning("hitl.resolve: missing run_id; ignoring")
        return

    decision = str(payload.get("decision") or "").strip().lower()
    approved = decision == "approve"
    if decision not in ("approve", "deny"):
        # Unknown/garbled decision is treated as a deny (fail-safe), but logged.
        log.warning(
            "hitl.resolve for run %s: unknown decision %r → deny", run_id, decision
        )

    reason = payload.get("reason") or ""
    actor = payload.get("actor")

    resolved = await get_gatekeeper().resolve(
        run_id=run_id, approved=approved, actor=actor, reason=reason
    )
    if resolved:
        return

    # No live gate (already resolved / timed out / never opened on this daemon). Keep the
    # audit row consistent so the TUI/cloud reflect the late decision, then return.
    await _update_orphan_row(
        run_id=run_id, approved=approved, actor=actor, reason=reason
    )
    log.info("hitl.resolve for run %s: no pending gate (idempotent no-op)", run_id)


async def _update_orphan_row(
    *, run_id: str, approved: bool, actor: Any, reason: str
) -> None:
    """Best-effort: stamp the latest pending row for this run with the late decision.

    Only touches a row still in ``pending`` so we never clobber an already-recorded
    timeout/approval. Failures are swallowed — a missing store must not crash dispatch.
    """
    try:
        await get_store().execute(
            "UPDATE hitl_state SET status=?, resolved_at=?, decision=?, actor=?, reason=?"
            " WHERE run_id=? AND status='pending'",
            (
                "approved" if approved else "denied",
                time.time(),
                "approve" if approved else "deny",
                actor,
                reason,
                run_id,
            ),
        )
    except Exception:  # noqa: BLE001 - audit update is best-effort
        log.exception("hitl.resolve: failed to update orphan row for run %s", run_id)
