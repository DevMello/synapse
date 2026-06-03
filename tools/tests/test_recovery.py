"""Tests for the durable execution & recovery unit (#15).

Covers the inbound checkpoint ingest + reconcile handlers, the heartbeat sweep
(called directly, no Redis), and the recovery REST endpoints. Runs against the
real Supabase project; orgs are minted per-test via `make_test_org` for RLS
isolation. The opaque checkpoint blob lands in the in-memory FakeBlobStore.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pytest_asyncio

from synapse_cloud.command_bus import (
    InMemoryCommandBus,
    get_command_bus,
    set_command_bus,
)
from synapse_cloud.db import service_db
from synapse_cloud.message_registry import (
    CHECKPOINT,
    RUN_RECONCILE,
    MessageContext,
    dispatch,
)
from synapse_cloud.services.recovery import (
    checkpoint_blob_key,
    sweep_interrupted_runs,
)
from synapse_cloud.storage import CHECKPOINTS, get_storage
from synapse_cloud.workers.heartbeat_monitor import (
    sweep_interrupted_runs as worker_sweep,
)


@pytest_asyncio.fixture
def fresh_bus():
    """Install a fresh in-memory command bus and restore the previous one."""
    prev = get_command_bus()
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    yield bus
    set_command_bus(prev)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def _make_agent(org_id: str, daemon_id: str | None = None) -> str:
    db = await service_db()
    row: dict = {"org_id": org_id, "name": "rec-agent", "type": "cli"}
    if daemon_id is not None:
        row["daemon_id"] = daemon_id
    return (await db.table("agents").insert(row).execute()).data[0]["id"]


async def _make_run(
    org_id: str, agent_id: str, *, status: str = "running", daemon_id: str | None = None
) -> str:
    db = await service_db()
    row: dict = {
        "org_id": org_id,
        "agent_id": agent_id,
        "trigger": "manual",
        "status": status,
    }
    if daemon_id is not None:
        row["daemon_id"] = daemon_id
    return (await db.table("runs").insert(row).execute()).data[0]["id"]


async def _insert_presence(daemon_id: str, org_id: str, *, expires_at: datetime) -> None:
    db = await service_db()
    await db.table("daemon_presence").upsert(
        {
            "daemon_id": daemon_id,
            "org_id": org_id,
            "hub_node": "hub-test",
            "last_heartbeat": _iso(expires_at - timedelta(seconds=30)),
            "expires_at": _iso(expires_at),
        }
    ).execute()


def _ctx(daemon_id: str, org_id: str, run_id: str, seq: int | None = None) -> MessageContext:
    return MessageContext(
        daemon_id=daemon_id, org_id=org_id, run_id=run_id, agent_id=None, seq=seq
    )


# ── Inbound checkpoint ingest ────────────────────────────────────────────────
async def test_checkpoint_dispatch_inserts_row_and_stores_blob(test_org, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(test_org.org_id, agent_id, daemon_id=daemon_id)

    blob = b"opaque-ciphertext-\x00\x01\x02"
    n = await dispatch(
        CHECKPOINT,
        _ctx(daemon_id, test_org.org_id, run_id, seq=1),
        {
            "seq": 1,
            "step_cursor": 7,
            "status": "running",
            "cost_so_far_usd": 0.12,
            "payload_b64": base64.b64encode(blob).decode(),
        },
    )
    assert n >= 1

    db = await service_db()
    rows = (
        await db.table("run_checkpoints")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert len(rows) == 1
    cp = rows[0]
    assert cp["seq"] == 1
    assert cp["step_cursor"] == 7
    assert float(cp["cost_so_far_usd"]) == 0.12
    assert cp["daemon_id"] == daemon_id
    assert cp["payload_blob_ref"] is not None

    # Opaque blob stored verbatim in the CHECKPOINTS bucket.
    store = get_storage()
    expected_key = f"{CHECKPOINTS}/{checkpoint_blob_key(test_org.org_id, run_id, 1)}"
    assert expected_key in store.blobs
    assert store.blobs[expected_key] == blob
    assert cp["payload_blob_ref"] == expected_key


async def test_checkpoint_upsert_idempotent_on_run_seq(test_org, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(test_org.org_id, agent_id, daemon_id=daemon_id)

    base = {"seq": 3, "step_cursor": 1, "cost_so_far_usd": 0.5}
    await dispatch(CHECKPOINT, _ctx(daemon_id, test_org.org_id, run_id, seq=3), dict(base))
    # Re-deliver same seq with an updated cursor — should update, not duplicate.
    await dispatch(
        CHECKPOINT,
        _ctx(daemon_id, test_org.org_id, run_id, seq=3),
        {**base, "step_cursor": 9, "cost_so_far_usd": 0.9},
    )

    db = await service_db()
    rows = (
        await db.table("run_checkpoints")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .eq("seq", 3)
        .execute()
    ).data
    assert len(rows) == 1
    assert rows[0]["step_cursor"] == 9
    assert float(rows[0]["cost_so_far_usd"]) == 0.9


# ── Reconcile ────────────────────────────────────────────────────────────────
async def test_reconcile_moves_interrupted_run_back(test_org, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(
        test_org.org_id, agent_id, status="interrupted", daemon_id=daemon_id
    )

    await dispatch(
        RUN_RECONCILE,
        _ctx(daemon_id, test_org.org_id, run_id, seq=5),
        {
            "seq": 5,
            "step_cursor": 4,
            "cost_so_far_usd": 1.0,
            "payload_b64": base64.b64encode(b"cp5").decode(),
        },
    )

    db = await service_db()
    run = (
        await db.table("runs")
        .select("status")
        .eq("org_id", test_org.org_id)
        .eq("id", run_id)
        .execute()
    ).data[0]
    assert run["status"] in ("running", "resumed")

    # Carried checkpoint was ingested.
    cps = (
        await db.table("run_checkpoints")
        .select("seq")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert [c["seq"] for c in cps] == [5]


async def test_reconcile_completed_marks_resumed(test_org, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(
        test_org.org_id, agent_id, status="interrupted", daemon_id=daemon_id
    )

    await dispatch(
        RUN_RECONCILE,
        _ctx(daemon_id, test_org.org_id, run_id),
        {"completed": True},
    )

    db = await service_db()
    run = (
        await db.table("runs")
        .select("status")
        .eq("org_id", test_org.org_id)
        .eq("id", run_id)
        .execute()
    ).data[0]
    assert run["status"] == "resumed"


# ── Heartbeat sweep ──────────────────────────────────────────────────────────
async def test_sweep_marks_runs_interrupted_and_daemon_offline(test_org):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(
        test_org.org_id, agent_id, status="running", daemon_id=daemon_id
    )
    # Expired lease → daemon considered dead.
    await _insert_presence(
        daemon_id, test_org.org_id, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    db = await service_db()
    summary = await sweep_interrupted_runs(db)
    assert summary["interrupted_runs"] >= 1

    run = (
        await db.table("runs")
        .select("status")
        .eq("org_id", test_org.org_id)
        .eq("id", run_id)
        .execute()
    ).data[0]
    assert run["status"] == "interrupted"

    daemon = (
        await db.table("daemons")
        .select("status")
        .eq("org_id", test_org.org_id)
        .eq("id", daemon_id)
        .execute()
    ).data[0]
    assert daemon["status"] == "offline"


async def test_sweep_ignores_fresh_presence(test_org):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(
        test_org.org_id, agent_id, status="running", daemon_id=daemon_id
    )
    # Lease still valid → must not be swept.
    await _insert_presence(
        daemon_id, test_org.org_id, expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )

    db = await service_db()
    await sweep_interrupted_runs(db)

    run = (
        await db.table("runs")
        .select("status")
        .eq("org_id", test_org.org_id)
        .eq("id", run_id)
        .execute()
    ).data[0]
    assert run["status"] == "running"


async def test_worker_sweep_callable_without_redis(test_org):
    """The Arq task wrapper runs the same core directly (ctx=None, no Redis)."""
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(
        test_org.org_id, agent_id, status="running", daemon_id=daemon_id
    )
    await _insert_presence(
        daemon_id, test_org.org_id, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    summary = await worker_sweep(None)
    assert summary["stale_daemons"] >= 1

    db = await service_db()
    run = (
        await db.table("runs")
        .select("status")
        .eq("org_id", test_org.org_id)
        .eq("id", run_id)
        .execute()
    ).data[0]
    assert run["status"] == "interrupted"


# ── REST: list checkpoints ───────────────────────────────────────────────────
async def test_get_checkpoints(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(test_org.org_id, agent_id, daemon_id=daemon_id)
    headers = test_org.auth_headers()

    for seq in (2, 1, 3):
        await dispatch(
            CHECKPOINT,
            _ctx(daemon_id, test_org.org_id, run_id, seq=seq),
            {"seq": seq, "cost_so_far_usd": 0.1 * seq},
        )

    resp = await client.get(f"/runs/{run_id}/checkpoints", headers=headers)
    assert resp.status_code == 200, resp.text
    seqs = [c["seq"] for c in resp.json()]
    assert seqs == [1, 2, 3]  # ordered by seq ascending


async def test_get_checkpoints_run_not_found(test_org, client):
    resp = await client.get(
        "/runs/00000000-0000-0000-0000-000000000000/checkpoints",
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


# ── REST: recover ────────────────────────────────────────────────────────────
async def test_recover_reassigns_daemon_and_emits_command(test_org, client, fresh_bus):
    src_daemon, _ = await test_org.make_daemon(name="src")
    target_daemon, _ = await test_org.make_daemon(name="target")
    agent_id = await _make_agent(test_org.org_id, daemon_id=src_daemon)
    run_id = await _make_run(
        test_org.org_id, agent_id, status="interrupted", daemon_id=src_daemon
    )
    headers = test_org.auth_headers()

    # Seed a latest checkpoint to pass through to the target daemon.
    await dispatch(
        CHECKPOINT,
        _ctx(src_daemon, test_org.org_id, run_id, seq=8),
        {"seq": 8, "cost_so_far_usd": 2.0, "payload_b64": base64.b64encode(b"cp8").decode()},
    )

    resp = await client.post(
        f"/runs/{run_id}/recover",
        json={"target_daemon_id": target_daemon},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "recovering"
    assert body["daemon_id"] == target_daemon

    sent = [s for s in fresh_bus.sent if s.command_type == "run.recover"]
    assert len(sent) == 1
    assert sent[0].daemon_id == target_daemon
    assert sent[0].payload["run_id"] == run_id
    assert sent[0].payload["seq"] == 8
    assert sent[0].payload["payload_blob_ref"] is not None


async def test_recover_target_daemon_not_found(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(
        test_org.org_id, agent_id, status="interrupted", daemon_id=daemon_id
    )
    resp = await client.post(
        f"/runs/{run_id}/recover",
        json={"target_daemon_id": "00000000-0000-0000-0000-000000000000"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


# ── Org isolation ────────────────────────────────────────────────────────────
async def test_recover_org_isolation(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    daemon_a, _ = await org_a.make_daemon()
    target_b, _ = await org_b.make_daemon()
    agent_id = await _make_agent(org_a.org_id, daemon_id=daemon_a)
    run_id = await _make_run(
        org_a.org_id, agent_id, status="interrupted", daemon_id=daemon_a
    )

    # org_b cannot recover org_a's run (run is not in org_b).
    resp = await client.post(
        f"/runs/{run_id}/recover",
        json={"target_daemon_id": target_b},
        headers=org_b.auth_headers(),
    )
    assert resp.status_code == 404

    # org_a recovering onto a daemon that lives in org_b → target not found.
    resp2 = await client.post(
        f"/runs/{run_id}/recover",
        json={"target_daemon_id": target_b},
        headers=org_a.auth_headers(),
    )
    assert resp2.status_code == 404


async def test_checkpoint_handler_org_scoped(make_test_org, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    daemon_a, _ = await org_a.make_daemon()
    agent_id = await _make_agent(org_a.org_id, daemon_id=daemon_a)
    run_id = await _make_run(org_a.org_id, agent_id, daemon_id=daemon_a)

    # Wrong-org context must not land a checkpoint under org_a's run.
    await dispatch(
        RUN_RECONCILE,
        _ctx(daemon_a, org_b.org_id, run_id, seq=1),
        {"seq": 1, "cost_so_far_usd": 0.0},
    )

    db = await service_db()
    a_rows = (
        await db.table("run_checkpoints")
        .select("seq")
        .eq("org_id", org_a.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert a_rows == []  # nothing written under org_a


# ── Inbound run.recover.ack ──────────────────────────────────────────────────
async def test_recover_ack_writes_audit(test_org):
    from synapse_cloud.audit import FakeAuditWriter, get_audit, set_audit
    from synapse_cloud.routers.recovery import RUN_RECOVER_ACK

    daemon_id, _ = await test_org.make_daemon(name="adopter")
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(
        test_org.org_id, agent_id, status="recovering", daemon_id=daemon_id
    )

    prev = get_audit()
    fake = FakeAuditWriter()
    set_audit(fake)
    try:
        n = await dispatch(
            RUN_RECOVER_ACK,
            _ctx(daemon_id, test_org.org_id, run_id),
            {"agent_id": agent_id, "plan": {"disposition": "resume", "gated": []}},
        )
    finally:
        set_audit(prev)

    assert n >= 1
    acks = [e for e in fake.events if e["action"] == RUN_RECOVER_ACK]
    assert len(acks) == 1
    ev = acks[0]
    assert ev["org_id"] == test_org.org_id
    assert ev["resource_id"] == run_id
    assert ev["run_id"] == run_id
    assert ev["detail"]["daemon_id"] == daemon_id
    assert ev["detail"]["plan"] == {"disposition": "resume", "gated": []}


async def test_recover_ack_missing_run_id_is_noop(test_org):
    from synapse_cloud.audit import FakeAuditWriter, get_audit, set_audit
    from synapse_cloud.routers.recovery import RUN_RECOVER_ACK

    daemon_id, _ = await test_org.make_daemon(name="adopter2")
    prev = get_audit()
    fake = FakeAuditWriter()
    set_audit(fake)
    try:
        await dispatch(
            RUN_RECOVER_ACK,
            MessageContext(daemon_id=daemon_id, org_id=test_org.org_id),
            {"plan": {"disposition": "resume"}},
        )
    finally:
        set_audit(prev)
    # No run_id anywhere -> nothing recorded.
    assert [e for e in fake.events if e["action"] == RUN_RECOVER_ACK] == []


# ── RBAC ─────────────────────────────────────────────────────────────────────
async def test_recover_requires_write(make_test_org, client, fresh_bus):
    org = await make_test_org(role="viewer")
    daemon_id, _ = await org.make_daemon()
    agent_id = await _make_agent(org.org_id, daemon_id=daemon_id)
    run_id = await _make_run(
        org.org_id, agent_id, status="interrupted", daemon_id=daemon_id
    )
    resp = await client.post(
        f"/runs/{run_id}/recover",
        json={"target_daemon_id": daemon_id},
        headers=org.auth_headers(),
    )
    assert resp.status_code == 403
