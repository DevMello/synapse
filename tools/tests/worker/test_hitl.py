"""HITL Gatekeeper tests (§4.7).

Self-contained, no network. Exercises the suspend/resume primitive end-to-end against
the in-memory ``uplink`` and the real SQLite ``store``:

  * approve path — request blocks, emits a ``hitl.request`` frame, persists a pending
    row, then a ``hitl.resolve`` (approve) unblocks it approved=True and updates the row.
  * deny path — resolve with "deny" → approved=False.
  * timeout path — no resolve within the timeout → approved=False, reason mentions
    timeout, row status "timeout".
  * orphan resolve — resolving a run with no live gate is an idempotent no-op (no crash)
    and still stamps the audit row.

Drives the blocked request with ``asyncio.create_task`` + short waits. Relies on
conftest's ``store``/``uplink`` fixtures; resets the gatekeeper singleton per test so
gates never leak between cases.
"""
from __future__ import annotations

import asyncio
import importlib

import pytest

import synapse_worker.commands.hitl as hitl_cmd
from synapse_worker.commands.hitl import handle_hitl_resolve
from synapse_worker.hitl import HitlOutcome, get_gatekeeper, reset_gatekeeper
from synapse_worker.router import CommandContext, known_commands


@pytest.fixture(autouse=True)
def _fresh_gatekeeper():
    """Each test starts with an empty pending-gate registry, and the ``hitl.resolve``
    handler re-registered (conftest's autouse fixture clears the router each test)."""
    reset_gatekeeper()
    importlib.reload(hitl_cmd)
    yield
    reset_gatekeeper()


def _ctx() -> CommandContext:
    return CommandContext(command_type="hitl.resolve")


async def _wait_pending(run_id: str, timeout: float = 1.0) -> None:
    """Spin until the gate is open AND its upstream ``hitl.request`` frame has been sent.

    The gate is registered in the map *before* the request_approval coroutine awaits its
    persist + uplink send, so waiting only on ``pending_run_ids()`` races those side
    effects. Waiting for the frame (the last side effect before the block) guarantees the
    pending row and the upstream send have already happened.
    """
    from synapse_worker.uplink import get_uplink

    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        gate_open = run_id in get_gatekeeper().pending_run_ids()
        frame_sent = any(
            f.payload.get("run_id") == run_id
            for f in get_uplink().of_type("hitl.request")
        )
        if gate_open and frame_sent:
            return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"gate for {run_id} never opened")
        await asyncio.sleep(0.01)


# ── approve path ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_approve_unblocks_and_updates_row(store, uplink):
    gk = get_gatekeeper()
    task = asyncio.create_task(
        gk.request_approval(
            run_id="rn_1", action={"tool": "git.push"}, context={"diff": "+1 -0"}
        )
    )
    await _wait_pending("rn_1")

    # A hitl.request frame went upstream on the control channel...
    frames = uplink.of_type("hitl.request")
    assert len(frames) == 1
    assert frames[0].channel == "control"
    assert frames[0].payload["run_id"] == "rn_1"
    assert frames[0].payload["action"] == {"tool": "git.push"}

    # ...and a pending row exists.
    row = await store.fetchone("SELECT * FROM hitl_state WHERE run_id=?", ("rn_1",))
    assert row is not None and row["status"] == "pending"

    await handle_hitl_resolve(
        _ctx(), {"run_id": "rn_1", "decision": "approve", "reason": "ok", "actor": "ada"}
    )

    outcome: HitlOutcome = await asyncio.wait_for(task, timeout=1.0)
    assert outcome.approved is True
    assert outcome.actor == "ada"
    assert outcome.reason == "ok"

    row = await store.fetchone("SELECT * FROM hitl_state WHERE run_id=?", ("rn_1",))
    assert row["status"] == "approved"
    assert row["decision"] == "approve"
    assert row["actor"] == "ada"
    assert row["resolved_at"] is not None


# ── deny path ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_deny_path(store, uplink):
    gk = get_gatekeeper()
    task = asyncio.create_task(gk.request_approval(run_id="rn_2", action="delete-prod"))
    await _wait_pending("rn_2")

    await handle_hitl_resolve(
        _ctx(), {"run_id": "rn_2", "decision": "deny", "reason": "too risky"}
    )

    outcome = await asyncio.wait_for(task, timeout=1.0)
    assert outcome.approved is False
    assert outcome.reason == "too risky"

    row = await store.fetchone("SELECT * FROM hitl_state WHERE run_id=?", ("rn_2",))
    assert row["status"] == "denied"
    assert row["decision"] == "deny"


# ── timeout path ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_timeout_defaults_to_deny(store, uplink):
    gk = get_gatekeeper()
    outcome = await gk.request_approval(run_id="rn_3", action="x", timeout=0.05)

    assert outcome.approved is False
    assert "timeout" in outcome.reason.lower()

    row = await store.fetchone("SELECT * FROM hitl_state WHERE run_id=?", ("rn_3",))
    assert row["status"] == "timeout"
    # The gate is cleaned up after it resolves.
    assert "rn_3" not in gk.pending_run_ids()


# ── orphan resolve (no matching gate) ────────────────────────────────────────
@pytest.mark.asyncio
async def test_resolve_with_no_gate_is_idempotent(store, uplink):
    # No request was ever made for rn_404 → no live gate. Must not crash.
    await handle_hitl_resolve(
        _ctx(), {"run_id": "rn_404", "decision": "approve", "reason": "late"}
    )
    # Nothing to assert beyond "did not raise"; no row was pre-created either.
    row = await store.fetchone("SELECT * FROM hitl_state WHERE run_id=?", ("rn_404",))
    assert row is None


@pytest.mark.asyncio
async def test_resolve_after_timeout_stamps_orphan_row(store, uplink):
    gk = get_gatekeeper()
    # Open and let it time out, leaving a 'timeout' row but no live gate.
    outcome = await gk.request_approval(run_id="rn_5", action="x", timeout=0.05)
    assert outcome.approved is False

    # A late approve arrives: no gate to resolve, but the row stays consistent. Because
    # the row is already 'timeout' (not 'pending'), the orphan update leaves it alone.
    await handle_hitl_resolve(
        _ctx(), {"run_id": "rn_5", "decision": "approve", "reason": "late"}
    )
    row = await store.fetchone("SELECT * FROM hitl_state WHERE run_id=?", ("rn_5",))
    assert row["status"] == "timeout"  # not clobbered by the late resolve


@pytest.mark.asyncio
async def test_resolve_missing_run_id_is_noop(store, uplink):
    # Defensive: a garbled payload must not crash dispatch.
    await handle_hitl_resolve(_ctx(), {"decision": "approve"})


# ── unknown decision defaults to deny ────────────────────────────────────────
@pytest.mark.asyncio
async def test_unknown_decision_denies(store, uplink):
    gk = get_gatekeeper()
    task = asyncio.create_task(gk.request_approval(run_id="rn_6", action="x"))
    await _wait_pending("rn_6")

    await handle_hitl_resolve(_ctx(), {"run_id": "rn_6", "decision": "maybe"})

    outcome = await asyncio.wait_for(task, timeout=1.0)
    assert outcome.approved is False


# ── concurrent timeout vs. late resolve must not crash or split-brain ─────────
@pytest.mark.asyncio
async def test_resolve_racing_timeout_does_not_crash(store, uplink):
    gk = get_gatekeeper()
    task = asyncio.create_task(gk.request_approval(run_id="rn_7", action="x", timeout=0.02))
    await _wait_pending("rn_7")
    # Let the gate time out first, then resolve into the now-dead gate. The resolve must
    # be a no-op (returns False) rather than raising InvalidStateError on a cancelled Future.
    outcome = await asyncio.wait_for(task, timeout=1.0)
    assert outcome.approved is False
    assert "timeout" in outcome.reason.lower()

    resolved = await gk.resolve(run_id="rn_7", approved=True, reason="late")
    assert resolved is False
    row = await store.fetchone("SELECT * FROM hitl_state WHERE run_id=?", ("rn_7",))
    assert row["status"] == "timeout"  # not flipped to approved by the late resolve


# ── handler is registered for the e2e seam ───────────────────────────────────
def test_hitl_resolve_command_registered():
    assert "hitl.resolve" in known_commands()
