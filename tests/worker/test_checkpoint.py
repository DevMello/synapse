"""Checkpointing, resume & recovery tests (§4.12) — self-contained, no network.

Exercises the unit end-to-end against the real SQLite ``store`` and in-memory ``uplink``/
``keystore`` fixtures from conftest:

  * journal append/latest/history + monotonic per-run seq.
  * plan_resume: committed step skipped; idempotent in-flight re-run; non-idempotent
    in-flight gated for HITL; resume policies (restart/abort/approval).
  * cloud sync: a sealed ``run.checkpoint`` frame round-trips via seal_open to the
    original session state, carries correct plaintext metadata, and is incremental.
  * run.recover handler: an inline sealed blob decrypts + restores the journal + yields a
    plan; an unset org recovery key degrades to a no-crash no-op.
  * auto_resume_all: an interrupted run with a committed checkpoint resumes at the right
    cursor.
"""
from __future__ import annotations

import json

import pytest

from synapse_worker import crypto
from synapse_worker.checkpoint import (
    STATUS_COMMITTED,
    STATUS_IN_FLIGHT,
    CheckpointJournal,
    auto_resume_all,
    plan_resume,
    sync_checkpoint,
)
from synapse_worker.checkpoint.recovery import (
    DECISION_GATE,
    DECISION_RERUN,
    DECISION_SKIP,
    KEYSTORE_SERVICE,
    ORG_PRIVATE_KEY,
    ORG_PUBLIC_KEY,
    POLICY_ABORT,
    POLICY_RESTART,
    RESUME,
    reset_warnings,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_warn():
    reset_warnings()
    yield
    reset_warnings()


def _seed_org_keys(keystore) -> crypto.KeyPair:
    kp = crypto.generate_keypair()
    keystore.set(KEYSTORE_SERVICE, ORG_PUBLIC_KEY, kp.public_key)
    keystore.set(KEYSTORE_SERVICE, ORG_PRIVATE_KEY, kp.private_key)
    return kp


async def _seed_run(store, run_id: str, agent_id: str = "agt_1", *, manifest: str | None = None):
    await store.execute(
        "INSERT INTO run_history (run_id, agent_id, status, started_at) VALUES (?,?,?,?)",
        (run_id, agent_id, "running", 0.0),
    )
    if manifest is not None:
        await store.execute(
            "INSERT INTO agents (id, name, type, version, manifest, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (agent_id, agent_id, "api", 1, manifest, 0.0),
        )


# ── journal ──────────────────────────────────────────────────────────────────
async def test_journal_monotonic_seq_and_history(store):
    j = CheckpointJournal(store)
    s1 = await j.append("run_a", 0, STATUS_IN_FLIGHT, {"tool_call": {"intent": "push"}})
    s2 = await j.append("run_a", 1, STATUS_COMMITTED, {"result": "ok"})
    # A different run starts its own seq series at 1.
    o1 = await j.append("run_b", 0, STATUS_IN_FLIGHT, {"tool_call": {"intent": "x"}})

    assert (s1, s2, o1) == (1, 2, 1)
    latest = await j.latest("run_a")
    assert latest["seq"] == 2 and latest["payload"] == {"result": "ok"}
    hist = await j.history("run_a")
    assert [r["seq"] for r in hist] == [1, 2]
    assert await j.latest_seq("run_a") == 2
    assert await j.latest("missing") is None


# ── resume planning ──────────────────────────────────────────────────────────
async def test_plan_resume_skip_rerun_gate(store):
    await _seed_run(store, "run_p")
    j = CheckpointJournal(store)
    # seq1: completed step (intent + result) -> SKIP, advances cursor to 1.
    await j.append("run_p", 1, STATUS_COMMITTED, {"tool_call": {"intent": "a"}, "result": "done"})
    # seq2: idempotent in-flight (intent, no result) -> RERUN.
    await j.append("run_p", 2, STATUS_IN_FLIGHT, {"tool_call": {"intent": "read", "idempotent": True}})

    plan = await plan_resume("run_p", store=store)
    decisions = {s.seq: s.decision for s in plan.steps}
    assert decisions == {1: DECISION_SKIP, 2: DECISION_RERUN}
    assert plan.disposition == RESUME
    assert plan.resume_cursor == 1
    assert plan.requires_approval is False

    # Now a non-idempotent in-flight step -> GATE + requires_approval.
    await j.append("run_p", 3, STATUS_IN_FLIGHT, {"tool_call": {"intent": "push", "idempotent": False}})
    plan2 = await plan_resume("run_p", store=store)
    assert {s.seq: s.decision for s in plan2.steps}[3] == DECISION_GATE
    assert plan2.requires_approval is True
    assert len(plan2.gated) == 1


async def test_plan_resume_two_write_protocol_completed_step_skipped(store):
    """§4.12 writes TWO rows per tool call (intent in_flight, then result committed),
    sharing a step_cursor. A completed non-idempotent step must SKIP, not gate on the
    intent row."""
    await _seed_run(store, "run_2w")
    j = CheckpointJournal(store)
    # step_cursor=1: intent row (in_flight, NO result, non-idempotent push)...
    await j.append("run_2w", 1, STATUS_IN_FLIGHT, {"tool_call": {"intent": "push", "idempotent": False}})
    # ...then the result row after it returns (committed).
    await j.append("run_2w", 1, STATUS_COMMITTED, {"tool_call": {"intent": "push"}, "result": "pushed"})
    # step_cursor=2: only an intent row -> genuinely interrupted -> GATE.
    await j.append("run_2w", 2, STATUS_IN_FLIGHT, {"tool_call": {"intent": "delete"}})

    plan = await plan_resume("run_2w", store=store)
    by_cursor = {s.step_cursor: s.decision for s in plan.steps}
    assert by_cursor == {1: DECISION_SKIP, 2: DECISION_GATE}
    assert plan.resume_cursor == 1
    assert plan.requires_approval is True  # the step-2 gate


async def test_plan_resume_default_non_idempotent_is_gated(store):
    """An in-flight step with no idempotency declaration is gated (safe default)."""
    await _seed_run(store, "run_d")
    j = CheckpointJournal(store)
    await j.append("run_d", 1, STATUS_IN_FLIGHT, {"tool_call": {"intent": "delete"}})
    plan = await plan_resume("run_d", store=store)
    assert plan.steps[0].decision == DECISION_GATE


async def test_plan_resume_policy_restart_and_abort(store):
    restart_toml = "[agent]\nid='a'\n[resume]\npolicy='restart'\n"
    await _seed_run(store, "run_r", agent_id="a", manifest=restart_toml)
    j = CheckpointJournal(store)
    await j.append("run_r", 1, STATUS_COMMITTED, {"result": "x"})
    plan = await plan_resume("run_r", store=store)
    assert plan.disposition == "restart" and plan.resume_cursor == 0

    abort_toml = "[agent]\nid='b'\n[resume]\npolicy='abort'\n"
    await _seed_run(store, "run_ab", agent_id="b", manifest=abort_toml)
    plan2 = await plan_resume("run_ab", store=store)
    assert plan2.disposition == "abort"


# ── cloud sync (E2E) ─────────────────────────────────────────────────────────
async def test_sync_checkpoint_seals_roundtrips_and_is_incremental(store, uplink, keystore):
    kp = _seed_org_keys(keystore)
    j = CheckpointJournal(store)
    session = {"step_cursor": 3, "messages": ["hi"], "cost_so_far_usd": 0.42, "status": "committed"}
    await j.append("run_s", 3, STATUS_COMMITTED, session)

    n = await sync_checkpoint("run_s", "agt_x", store=store)
    assert n == 1
    frames = uplink.of_type("run.checkpoint")
    assert len(frames) == 1
    fr = frames[0].payload
    # Plaintext metadata is correct and non-sensitive.
    assert fr["run_id"] == "run_s" and fr["agent_id"] == "agt_x"
    # seq is journal-assigned (first row -> 1); step_cursor is the run's own cursor (3).
    assert fr["seq"] == 1 and fr["step_cursor"] == 3
    assert fr["status"] == "committed" and fr["cost_so_far_usd"] == 0.42
    # The sealed blob round-trips back to the exact session state.
    plaintext = crypto.seal_open(kp.private_key, fr["payload_b64"])
    assert json.loads(plaintext) == session

    # Incremental: a second sync with no new rows emits nothing.
    assert await sync_checkpoint("run_s", "agt_x", store=store) == 0
    assert len(uplink.of_type("run.checkpoint")) == 1
    # A new checkpoint ships only the new seq (journal-assigned 2).
    await j.append("run_s", 4, STATUS_IN_FLIGHT, {"step_cursor": 4})
    assert await sync_checkpoint("run_s", "agt_x", store=store) == 1
    assert [f.payload["seq"] for f in uplink.of_type("run.checkpoint")] == [1, 2]


async def test_sync_checkpoint_no_org_key_is_graceful(store, uplink, keystore):
    j = CheckpointJournal(store)
    await j.append("run_n", 1, STATUS_COMMITTED, {"x": 1})
    # No org recovery public key set -> skip without crashing, emit nothing.
    assert await sync_checkpoint("run_n", "agt", store=store) == 0
    assert uplink.of_type("run.checkpoint") == []


# ── run.recover handler ──────────────────────────────────────────────────────
async def test_run_recover_inline_blob_restores_and_plans(store, uplink, keystore):
    import importlib

    import synapse_worker.commands.recovery as rec
    importlib.reload(rec)  # re-register handler (conftest clears the router each test)
    from synapse_worker.router import CommandContext, known_commands

    assert "run.recover" in known_commands()

    kp = _seed_org_keys(keystore)
    session = {"step_cursor": 7, "messages": ["restored"], "tool_call": {"intent": "a"}, "result": "ok"}
    blob = crypto.seal(kp.public_key, json.dumps(session, separators=(",", ":"), sort_keys=True).encode())

    ctx = CommandContext(command_type="run.recover")
    await rec.handle_run_recover(
        ctx,
        {"run_id": "run_rec", "agent_id": "agt_z", "seq": 5, "payload_b64": blob},
    )

    # The decrypted checkpoint was restored at its original seq.
    j = CheckpointJournal(store)
    latest = await j.latest("run_rec")
    assert latest is not None and latest["seq"] == 5
    assert latest["payload"]["messages"] == ["restored"]
    # A resume plan was emitted; the completed step is a SKIP.
    acks = uplink.of_type("run.recover.ack")
    assert len(acks) == 1
    plan = acks[0].payload["plan"]
    assert plan["run_id"] == "run_rec"
    assert plan["steps"][0]["decision"] == DECISION_SKIP


async def test_run_recover_unset_key_no_crash(store, uplink):
    import importlib

    import synapse_worker.commands.recovery as rec
    importlib.reload(rec)

    from synapse_worker.router import CommandContext

    # Provide a syntactically-valid-looking blob but NO org private key in the keystore.
    ctx = CommandContext(command_type="run.recover")
    await rec.handle_run_recover(
        ctx, {"run_id": "run_nokey", "agent_id": "a", "payload_b64": "Zm9v"}
    )
    # No checkpoint restored; handler did not raise.
    j = CheckpointJournal(store)
    assert await j.latest("run_nokey") is None


async def test_run_recover_missing_run_id_is_noop(store):
    import importlib

    import synapse_worker.commands.recovery as rec
    importlib.reload(rec)
    from synapse_worker.router import CommandContext

    # Must not raise.
    await rec.handle_run_recover(CommandContext(command_type="run.recover"), {})


# ── auto_resume_all ──────────────────────────────────────────────────────────
async def test_auto_resume_all_resumes_from_cursor(store):
    # An interrupted (status=running) run with a committed checkpoint at cursor 2.
    await _seed_run(store, "run_auto")
    # A finished run that must NOT be a resume candidate.
    await store.execute(
        "INSERT INTO run_history (run_id, agent_id, status, started_at) VALUES (?,?,?,?)",
        ("run_done", "agt_1", "finished", 0.0),
    )
    j = CheckpointJournal(store)
    await j.append("run_auto", 2, STATUS_COMMITTED, {"tool_call": {"intent": "a"}, "result": "ok"})

    plans = await auto_resume_all(store=store)
    by_run = {p.run_id: p for p in plans}
    assert "run_auto" in by_run and "run_done" not in by_run
    assert by_run["run_auto"].resume_cursor == 2
    assert by_run["run_auto"].disposition == RESUME
