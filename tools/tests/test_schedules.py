"""Tests for the schedules unit: CRUD, kind validation, schedule.set dispatch."""
from __future__ import annotations

import pytest_asyncio

from synapse_cloud.command_bus import (
    InMemoryCommandBus,
    get_command_bus,
    set_command_bus,
)
from synapse_cloud.db import service_db


@pytest_asyncio.fixture
def fresh_bus():
    """Install a fresh in-memory command bus and restore the previous one."""
    prev = get_command_bus()
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    yield bus
    set_command_bus(prev)


async def _make_agent(org_id: str, daemon_id: str | None = None) -> str:
    db = await service_db()
    row: dict = {"org_id": org_id, "name": "test-agent", "type": "cli"}
    if daemon_id is not None:
        row["daemon_id"] = daemon_id
    inserted = (await db.table("agents").insert(row).execute()).data[0]
    return inserted["id"]


# ── create + kind validation ──────────────────────────────────────────────────
async def test_create_cron_schedule_dispatches(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)

    resp = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "cron", "cron_expr": "*/5 * * * *"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    sched = resp.json()
    assert sched["kind"] == "cron"
    assert sched["cron_expr"] == "*/5 * * * *"
    assert sched["enabled"] is True
    assert sched["agent_id"] == agent_id

    sent = fresh_bus.sent
    assert len(sent) == 1
    assert sent[0].command_type == "schedule.set"
    assert sent[0].daemon_id == daemon_id
    assert sent[0].payload["schedule_id"] == sched["id"]
    assert sent[0].payload["enabled"] is True
    assert sent[0].payload["deleted"] is False


async def test_create_interval_schedule(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    resp = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "interval", "interval_seconds": 60},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["interval_seconds"] == 60


async def test_create_one_shot_schedule(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    resp = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "one_shot", "run_at": "2030-01-01T00:00:00Z"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["run_at"] is not None


async def test_no_daemon_skips_send_but_persists(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)  # no daemon_id
    resp = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "interval", "interval_seconds": 30},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    assert len(fresh_bus.sent) == 0


async def test_create_kind_mismatch_rejected(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    headers = test_org.auth_headers()

    # cron without cron_expr
    r = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "cron"},
        headers=headers,
    )
    assert r.status_code == 400, r.text

    # interval without interval_seconds
    r = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "interval"},
        headers=headers,
    )
    assert r.status_code == 400, r.text

    # one_shot without run_at
    r = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "one_shot"},
        headers=headers,
    )
    assert r.status_code == 400, r.text

    # unknown kind
    r = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "weekly", "cron_expr": "x"},
        headers=headers,
    )
    assert r.status_code == 400, r.text


async def test_create_agent_not_found(test_org, client, fresh_bus):
    resp = await client.post(
        "/agents/00000000-0000-0000-0000-000000000000/schedules",
        json={"kind": "interval", "interval_seconds": 60},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


# ── read ────────────────────────────────────────────────────────────────────
async def test_list_and_get_schedule(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(
            f"/agents/{agent_id}/schedules",
            json={"kind": "interval", "interval_seconds": 60},
            headers=headers,
        )
    ).json()

    lst = await client.get(f"/agents/{agent_id}/schedules", headers=headers)
    assert lst.status_code == 200
    assert [s["id"] for s in lst.json()] == [created["id"]]

    one = await client.get(f"/schedules/{created['id']}", headers=headers)
    assert one.status_code == 200
    assert one.json()["id"] == created["id"]


# ── update ──────────────────────────────────────────────────────────────────
async def test_update_schedule_dispatches(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(
            f"/agents/{agent_id}/schedules",
            json={"kind": "interval", "interval_seconds": 60},
            headers=headers,
        )
    ).json()
    fresh_bus.sent.clear()

    resp = await client.patch(
        f"/schedules/{created['id']}",
        json={"interval_seconds": 120},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["interval_seconds"] == 120

    assert len(fresh_bus.sent) == 1
    assert fresh_bus.sent[0].command_type == "schedule.set"
    assert fresh_bus.sent[0].payload["interval_seconds"] == 120


async def test_disable_toggle_dispatches(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(
            f"/agents/{agent_id}/schedules",
            json={"kind": "cron", "cron_expr": "* * * * *"},
            headers=headers,
        )
    ).json()
    fresh_bus.sent.clear()

    resp = await client.patch(
        f"/schedules/{created['id']}",
        json={"enabled": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False

    assert len(fresh_bus.sent) == 1
    assert fresh_bus.sent[0].payload["enabled"] is False


async def test_update_no_fields_rejected(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(
            f"/agents/{agent_id}/schedules",
            json={"kind": "interval", "interval_seconds": 60},
            headers=headers,
        )
    ).json()

    resp = await client.patch(f"/schedules/{created['id']}", json={}, headers=headers)
    assert resp.status_code == 400


async def test_update_clearing_required_field_rejected(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(
            f"/agents/{agent_id}/schedules",
            json={"kind": "cron", "cron_expr": "* * * * *"},
            headers=headers,
        )
    ).json()

    # Nulling cron_expr on a cron schedule must be rejected.
    resp = await client.patch(
        f"/schedules/{created['id']}",
        json={"cron_expr": None},
        headers=headers,
    )
    assert resp.status_code == 400


# ── delete ──────────────────────────────────────────────────────────────────
async def test_delete_schedule_dispatches_teardown(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    headers = test_org.auth_headers()
    created = (
        await client.post(
            f"/agents/{agent_id}/schedules",
            json={"kind": "interval", "interval_seconds": 60},
            headers=headers,
        )
    ).json()
    fresh_bus.sent.clear()

    resp = await client.delete(f"/schedules/{created['id']}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True

    assert len(fresh_bus.sent) == 1
    assert fresh_bus.sent[0].command_type == "schedule.set"
    assert fresh_bus.sent[0].payload["deleted"] is True
    assert fresh_bus.sent[0].payload["enabled"] is False

    # Gone.
    gone = await client.get(f"/schedules/{created['id']}", headers=headers)
    assert gone.status_code == 404


# ── org isolation ─────────────────────────────────────────────────────────────
async def test_org_isolation_get_schedule(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent_id = await _make_agent(org_a.org_id)
    created = (
        await client.post(
            f"/agents/{agent_id}/schedules",
            json={"kind": "interval", "interval_seconds": 60},
            headers=org_a.auth_headers(),
        )
    ).json()

    resp = await client.get(
        f"/schedules/{created['id']}", headers=org_b.auth_headers()
    )
    assert resp.status_code == 404


async def test_org_isolation_delete_schedule(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent_id = await _make_agent(org_a.org_id)
    created = (
        await client.post(
            f"/agents/{agent_id}/schedules",
            json={"kind": "interval", "interval_seconds": 60},
            headers=org_a.auth_headers(),
        )
    ).json()

    resp = await client.delete(
        f"/schedules/{created['id']}", headers=org_b.auth_headers()
    )
    assert resp.status_code == 404


# ── rbac ──────────────────────────────────────────────────────────────────────
async def test_viewer_cannot_create(make_test_org, client, fresh_bus):
    org = await make_test_org(role="viewer")
    agent_id = await _make_agent(org.org_id)
    resp = await client.post(
        f"/agents/{agent_id}/schedules",
        json={"kind": "interval", "interval_seconds": 60},
        headers=org.auth_headers(),
    )
    assert resp.status_code == 403
