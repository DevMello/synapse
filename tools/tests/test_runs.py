"""Tests for the runs unit: lifecycle, cancel, tool_calls, run.finished handler."""
from __future__ import annotations

import pytest_asyncio

from synapse_cloud.command_bus import (
    InMemoryCommandBus,
    get_command_bus,
    set_command_bus,
)
from synapse_cloud.db import service_db
from synapse_cloud.message_registry import (
    RUN_FINISHED,
    MessageContext,
    dispatch,
)
from synapse_cloud.routers.runs import record_tool_calls


@pytest_asyncio.fixture
def fresh_bus():
    """Install a fresh in-memory command bus and restore the previous one."""
    prev = get_command_bus()
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    yield bus
    set_command_bus(prev)


async def _make_agent(org_id: str, daemon_id: str | None = None, version: int | None = None) -> str:
    db = await service_db()
    row: dict = {"org_id": org_id, "name": "test-agent", "type": "cli"}
    if daemon_id is not None:
        row["daemon_id"] = daemon_id
    if version is not None:
        row["version"] = version
    inserted = (await db.table("agents").insert(row).execute()).data[0]
    return inserted["id"]


async def test_create_run_dispatches_agent_run(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)

    resp = await client.post(
        f"/agents/{agent_id}/runs",
        json={"trigger": "manual"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["status"] == "pending"
    assert run["agent_id"] == agent_id
    assert run["daemon_id"] == daemon_id

    sent = fresh_bus.sent
    assert len(sent) == 1
    assert sent[0].command_type == "agent.run"
    assert sent[0].daemon_id == daemon_id
    assert sent[0].payload["run_id"] == run["id"]


async def test_create_run_idempotency(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)

    headers = test_org.auth_headers()
    r1 = await client.post(
        f"/agents/{agent_id}/runs",
        json={"idempotency_key": "key-123"},
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        f"/agents/{agent_id}/runs",
        json={"idempotency_key": "key-123"},
        headers=headers,
    )
    assert r2.status_code == 201, r2.text
    assert r1.json()["id"] == r2.json()["id"]
    # Only the first create dispatched a command.
    assert len(fresh_bus.sent) == 1


async def test_create_run_agent_not_found(test_org, client, fresh_bus):
    resp = await client.post(
        "/agents/00000000-0000-0000-0000-000000000000/runs",
        json={},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


async def test_list_and_get_run(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(f"/agents/{agent_id}/runs", json={}, headers=headers)
    ).json()

    lst = await client.get("/runs", headers=headers)
    assert lst.status_code == 200
    ids = [r["id"] for r in lst.json()]
    assert created["id"] in ids

    one = await client.get(f"/runs/{created['id']}", headers=headers)
    assert one.status_code == 200
    assert one.json()["id"] == created["id"]


async def test_list_runs_filter_by_status(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    headers = test_org.auth_headers()
    await client.post(f"/agents/{agent_id}/runs", json={}, headers=headers)

    pending = await client.get("/runs?status=pending", headers=headers)
    assert pending.status_code == 200
    assert all(r["status"] == "pending" for r in pending.json())

    succeeded = await client.get("/runs?status=succeeded", headers=headers)
    assert succeeded.status_code == 200
    assert all(r["status"] == "succeeded" for r in succeeded.json())


async def test_agent_run_history(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(f"/agents/{agent_id}/runs", json={}, headers=headers)
    ).json()

    hist = await client.get(f"/agents/{agent_id}/runs", headers=headers)
    assert hist.status_code == 200
    assert [r["id"] for r in hist.json()] == [created["id"]]


async def test_cancel_run(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(f"/agents/{agent_id}/runs", json={}, headers=headers)
    ).json()

    resp = await client.post(f"/runs/{created['id']}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"

    cancels = [s for s in fresh_bus.sent if s.command_type == "agent.cancel"]
    assert len(cancels) == 1
    assert cancels[0].payload["run_id"] == created["id"]


async def test_org_isolation_get_run(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent_id = await _make_agent(org_a.org_id)
    created = (
        await client.post(
            f"/agents/{agent_id}/runs", json={}, headers=org_a.auth_headers()
        )
    ).json()

    # org_b cannot see org_a's run.
    resp = await client.get(f"/runs/{created['id']}", headers=org_b.auth_headers())
    assert resp.status_code == 404


async def test_tool_calls_record_and_list(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(f"/agents/{agent_id}/runs", json={}, headers=headers)
    ).json()
    run_id = created["id"]

    await record_tool_calls(
        test_org.org_id,
        run_id,
        [
            {"name": "search", "args_redacted": {"q": "x"}, "latency_ms": 12, "cost_usd": 0.01},
            {"name": "write", "result_redacted": {"ok": True}},
        ],
    )

    resp = await client.get(f"/runs/{run_id}/tool_calls", headers=headers)
    assert resp.status_code == 200
    calls = resp.json()
    assert {c["name"] for c in calls} == {"search", "write"}


async def test_run_finished_handler_finalizes(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(f"/agents/{agent_id}/runs", json={}, headers=headers)
    ).json()
    run_id = created["id"]

    n = await dispatch(
        RUN_FINISHED,
        MessageContext(
            daemon_id=daemon_id,
            org_id=test_org.org_id,
            run_id=run_id,
            agent_id=agent_id,
            seq=1,
        ),
        {
            "status": "succeeded",
            "cost_usd": 0.42,
            "tokens_in": 100,
            "tokens_out": 200,
            "exit_code": 0,
            "tool_calls": [{"name": "do_it", "latency_ms": 5}],
        },
    )
    assert n >= 1

    run = (await client.get(f"/runs/{run_id}", headers=headers)).json()
    assert run["status"] == "succeeded"
    assert float(run["cost_usd"]) == 0.42
    assert run["tokens_in"] == 100
    assert run["tokens_out"] == 200
    assert run["exit_code"] == 0
    assert run["ended_at"] is not None

    calls = (await client.get(f"/runs/{run_id}/tool_calls", headers=headers)).json()
    assert [c["name"] for c in calls] == ["do_it"]


async def test_run_finished_handler_org_scoped(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent_id = await _make_agent(org_a.org_id)
    created = (
        await client.post(
            f"/agents/{agent_id}/runs", json={}, headers=org_a.auth_headers()
        )
    ).json()
    run_id = created["id"]

    # Dispatch with the WRONG org id — must not finalize org_a's run.
    await dispatch(
        RUN_FINISHED,
        MessageContext(
            daemon_id="x", org_id=org_b.org_id, run_id=run_id, agent_id=None, seq=1
        ),
        {"status": "failed"},
    )

    run = (
        await client.get(f"/runs/{run_id}", headers=org_a.auth_headers())
    ).json()
    assert run["status"] == "pending"
