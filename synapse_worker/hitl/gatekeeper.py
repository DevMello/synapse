"""HITL Gatekeeper: the suspend/resume primitive + pending-gate registry (§4.7).

When the Ruleset Engine marks an action sensitive (or an agent explicitly requests
approval), the runtime calls :meth:`Gatekeeper.request_approval`. That:

1. INSERTs a ``hitl_state`` row (status ``pending``) so the local TUI's Approvals pane
   can render the gate (it reads that table), and publishes a local ``hitl`` event.
2. Emits a ``hitl.request`` upstream frame on the control channel so the cloud can fan
   an approval prompt out to Slack/Discord/Email/Web UI.
3. **Really blocks** on an ``asyncio.Future`` — not a poll — until a ``hitl.resolve``
   command resolves the matching gate or a timeout fires. On timeout the gate resolves
   as **deny** (fail-safe default) and the row is marked ``timeout``.

Correlation: the daemon does not know the cloud's ``hitl_id`` when it sends the request,
so gates are keyed by ``run_id`` (a run has at most one pending gate at a time). The
``hitl.resolve`` handler looks the gate up by ``run_id`` and resolves its Future. If no
gate matches (already resolved or timed out) the handler is idempotent: it just updates
the row and returns without crashing.

The module-level singleton (:func:`get_gatekeeper`) lets the command handler resolve
gates created by the runtime even though they live in different call stacks.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from ..events import Event, get_event_bus
from ..logging import get_logger
from ..uplink import CHANNEL_CONTROL, get_uplink

log = get_logger(__name__)

# Default HITL wait before falling back to deny. Kept conservative (5 min) so a sensitive
# action never blocks a run forever, yet a human has a realistic window to respond.
DEFAULT_HITL_TIMEOUT_SECONDS = 300.0

__all__ = [
    "Gatekeeper",
    "HitlOutcome",
    "get_gatekeeper",
    "reset_gatekeeper",
    "DEFAULT_HITL_TIMEOUT_SECONDS",
]


@dataclass
class HitlOutcome:
    """The resolution of a HITL gate handed back to the awaiting runtime."""

    approved: bool
    actor: Optional[str] = None
    reason: str = ""
    hitl_id: Optional[str] = None


@dataclass
class _Gate:
    """One pending gate: its DB row id, the run it belongs to, and the Future the
    runtime is blocked on."""

    hitl_id: str
    run_id: str
    future: "asyncio.Future[HitlOutcome]"


class Gatekeeper:
    """Suspend/resume primitive + a registry of pending gates keyed by ``run_id``."""

    def __init__(self) -> None:
        # run_id -> pending gate. A run has at most one open gate at a time, so run_id is
        # a safe correlation key for the cloud's resolve (which carries run_id, not our id).
        self._gates: dict[str, _Gate] = {}

    # ── runtime side: open a gate and block ────────────────────────────────
    async def request_approval(
        self,
        *,
        run_id: str,
        action: Any,
        context: Optional[dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> HitlOutcome:
        """Pause the run until the cloud/TUI resolves the gate (or timeout → deny)."""
        if timeout is None:
            timeout = DEFAULT_HITL_TIMEOUT_SECONDS

        hitl_id = f"hitl_{uuid.uuid4().hex[:16]}"
        loop = asyncio.get_running_loop()
        future: "asyncio.Future[HitlOutcome]" = loop.create_future()
        gate = _Gate(hitl_id=hitl_id, run_id=run_id, future=future)

        # If a stale gate already exists for this run (e.g. a prior request never
        # resolved), deny it before replacing — the run only blocks on the newest gate,
        # so a never-resolved older Future would otherwise leak.
        old = self._gates.get(run_id)
        if old is not None and not old.future.done():
            old.future.set_result(
                HitlOutcome(approved=False, reason="superseded", hitl_id=old.hitl_id)
            )
        self._gates[run_id] = gate

        await self._persist_pending(hitl_id, run_id, action)
        await self._publish_event(
            run_id=run_id, agent_id=agent_id, status="pending", hitl_id=hitl_id
        )

        # Emit the upstream request AFTER persisting so the TUI/row exists even if the
        # send fails; never let an uplink hiccup crash the run — the timeout still applies.
        try:
            await get_uplink().send(
                "hitl.request",
                {
                    "hitl_id": hitl_id,
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "action": action,
                    "context": context or {},
                },
                channel=CHANNEL_CONTROL,
            )
        except Exception:  # noqa: BLE001 - request is best-effort; gate still times out
            log.exception("hitl.request send failed for run %s", run_id)

        try:
            outcome = await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            # Fail-safe: no decision in the window → default DENY.
            outcome = HitlOutcome(
                approved=False, reason="timeout (default deny)", hitl_id=hitl_id
            )
            await self._finalize_row(hitl_id, "timeout", outcome)
            await self._publish_event(
                run_id=run_id, agent_id=agent_id, status="timeout", hitl_id=hitl_id
            )
            log.info("hitl gate for run %s timed out → deny", run_id)
            return outcome
        finally:
            # Drop the gate only if it's still ours (a superseding request may have
            # already replaced it in the map).
            if self._gates.get(run_id) is gate:
                del self._gates[run_id]

        # Resolved by the command handler, which already wrote the final row + event.
        return outcome

    # ── resolve side: called by the hitl.resolve command handler ───────────
    async def resolve(
        self,
        *,
        run_id: str,
        approved: bool,
        actor: Optional[str] = None,
        reason: str = "",
    ) -> bool:
        """Deliver a decision to the pending gate for ``run_id``.

        Returns True if a gate was found and resolved, False if none matched (already
        resolved/timed out) — in which case the caller still updates the row for audit.
        Idempotent and crash-free either way.
        """
        gate = self._gates.get(run_id)
        if gate is None or gate.future.done():
            return False

        outcome = HitlOutcome(
            approved=approved, actor=actor, reason=reason, hitl_id=gate.hitl_id
        )
        status = "approved" if approved else "denied"

        # Claim the gate FIRST, synchronously, so a concurrently-firing ``wait_for``
        # timeout can't cancel the Future between our checks and the I/O below — that
        # would race a "timeout" row against our "approved/denied" one. If the timeout
        # already won (Future done/cancelled), defer to it as an orphan resolve.
        try:
            gate.future.set_result(outcome)
        except asyncio.InvalidStateError:
            return False

        # Future is set; now record the decision. The awaiting runtime won't observe the
        # result until this coroutine next yields, so the row is written first in practice.
        await self._finalize_row(gate.hitl_id, status, outcome)
        await self._publish_event(run_id=run_id, status=status, hitl_id=gate.hitl_id)
        log.info("hitl gate for run %s resolved → %s", run_id, status)
        return True

    def pending_run_ids(self) -> list[str]:
        """run_ids with an open gate (for tests/diagnostics)."""
        return [rid for rid, g in self._gates.items() if not g.future.done()]

    # ── persistence helpers (best-effort; never sink the runtime) ──────────
    async def _persist_pending(self, hitl_id: str, run_id: str, action: Any) -> None:
        try:
            from ..store import get_store

            await get_store().execute(
                "INSERT INTO hitl_state (id, run_id, status, action, created_at)"
                " VALUES (?,?,?,?,?)",
                (hitl_id, run_id, "pending", _as_text(action), time.time()),
            )
        except Exception:  # noqa: BLE001 - store may be absent in lightweight contexts
            log.exception("hitl: failed to persist pending row for run %s", run_id)

    async def _finalize_row(
        self, hitl_id: str, status: str, outcome: HitlOutcome
    ) -> None:
        try:
            from ..store import get_store

            await get_store().execute(
                "UPDATE hitl_state SET status=?, resolved_at=?, decision=?, actor=?,"
                " reason=? WHERE id=?",
                (
                    status,
                    time.time(),
                    "approve" if outcome.approved else "deny",
                    outcome.actor,
                    outcome.reason,
                    hitl_id,
                ),
            )
        except Exception:  # noqa: BLE001
            log.exception("hitl: failed to finalize row %s", hitl_id)

    async def _publish_event(
        self,
        *,
        run_id: str,
        status: str,
        hitl_id: str,
        agent_id: Optional[str] = None,
    ) -> None:
        # Local-only nudge so the TUI Approvals pane can react live (optional per spec).
        try:
            await get_event_bus().publish(
                Event(
                    kind="hitl",
                    data={"hitl_id": hitl_id, "status": status},
                    run_id=run_id,
                    agent_id=agent_id,
                )
            )
        except Exception:  # noqa: BLE001 - event bus is a convenience, not a dependency
            log.debug("hitl: event publish failed for run %s", run_id, exc_info=True)


def _as_text(action: Any) -> str:
    """Coerce an action of any shape to a stable text form for the ``action`` column."""
    if action is None or isinstance(action, str):
        return action or ""
    try:
        import json

        return json.dumps(action, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(action)


# ── module-level singleton seam ────────────────────────────────────────────
_gatekeeper: Gatekeeper = Gatekeeper()


def get_gatekeeper() -> Gatekeeper:
    return _gatekeeper


def reset_gatekeeper() -> None:  # test helper
    global _gatekeeper
    _gatekeeper = Gatekeeper()
