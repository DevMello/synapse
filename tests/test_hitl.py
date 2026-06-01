"""Tests for the HITL + notifications unit.

Covers: notification_channels CRUD + RBAC, the inbound `hitl.request` flow
(pending row + notification), resolve (command + status update + 409 on
double-resolve + RBAC), and the timeout sweeper (default-deny).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest_asyncio

from synapse_cloud.command_bus import (
    InMemoryCommandBus,
    get_command_bus,
    set_command_bus,
)
from synapse_cloud.db import service_db
from synapse_cloud.message_registry import HITL_REQUEST, MessageContext, dispatch
from synapse_cloud.notifications.base import get_notifier
from synapse_cloud.workers.notify import sweep_expired_hitl


@pytest_asyncio.fixture
def fresh_bus():
    prev = get_command_bus()
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    yield bus
    set_command_bus(prev)


def _now_offset(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


# ── notification channels CRUD + RBAC ──────────────────────────────────────────
async def test_create_and_list_channel(test_org, client):
    resp = await client.post(
        "/notifications/channels",
        json={"kind": "slack", "config": {"webhook_url": "https://hooks/x"}},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    channel = resp.json()
    assert channel["kind"] == "slack"
    assert channel["enabled"] is True

    listed = await client.get("/notifications/channels", headers=test_org.auth_headers())
    assert listed.status_code == 200
    assert any(c["id"] == channel["id"] for c in listed.json())


async def test_invalid_kind_rejected(test_org, client):
    resp = await client.post(
        "/notifications/channels",
        json={"kind": "carrier-pigeon"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 422


async def test_update_and_delete_channel(test_org, client):
    created = (
        await client.post(
            "/notifications/channels",
            json={"kind": "discord", "config": {"webhook_url": "https://d/x"}},
            headers=test_org.auth_headers(),
        )
    ).json()
    cid = created["id"]

    patched = await client.patch(
        f"/notifications/channels/{cid}",
        json={"enabled": False},
        headers=test_org.auth_headers(),
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    deleted = await client.delete(
        f"/notifications/channels/{cid}", headers=test_org.auth_headers()
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    gone = await client.get(
        f"/notifications/channels/{cid}", headers=test_org.auth_headers()
    )
    assert gone.status_code == 404


async def test_channel_mutations_require_admin(make_test_org, client):
    viewer = await make_test_org(role="viewer")
    resp = await client.post(
        "/notifications/channels",
        json={"kind": "slack"},
        headers=viewer.auth_headers(),
    )
    assert resp.status_code == 403


async def test_channels_org_scoped(make_test_org, client):
    org_a = await make_test_org()
    org_b = await make_test_org()
    created = (
        await client.post(
            "/notifications/channels",
            json={"kind": "in_app"},
            headers=org_a.auth_headers(),
        )
    ).json()
    # Org B cannot see org A's channel.
    resp = await client.get(
        f"/notifications/channels/{created['id']}", headers=org_b.auth_headers()
    )
    assert resp.status_code == 404


# ── inbound hitl.request flow ──────────────────────────────────────────────────
async def test_hitl_request_creates_pending_and_notifies(test_org):
    daemon_id, _ = await test_org.make_daemon()
    notifier = get_notifier()
    before = len(notifier.sent)

    n = await dispatch(
        HITL_REQUEST,
        MessageContext(
            daemon_id=daemon_id,
            org_id=test_org.org_id,
            run_id=None,
            agent_id=None,
            seq=1,
        ),
        {"action": "delete-prod-db", "context": {"why": "cleanup"}},
    )
    assert n >= 1

    db = await service_db()
    rows = (
        await db.table("hitl_requests")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("daemon_id", daemon_id)
        .execute()
    ).data
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["action"] == "delete-prod-db"

    sent = notifier.sent[before:]
    assert any(s.event == "hitl.request" and s.org_id == test_org.org_id for s in sent)


# ── resolve ─────────────────────────────────────────────────────────────────
async def _make_pending(org_id: str, daemon_id: str, expires_in: int = 3600) -> str:
    db = await service_db()
    row = (
        await db.table("hitl_requests")
        .insert(
            {
                "org_id": org_id,
                "daemon_id": daemon_id,
                "action": "approve-spend",
                "context": {},
                "status": "pending",
                "expires_at": _now_offset(expires_in),
            }
        )
        .execute()
    ).data[0]
    return row["id"]


async def test_resolve_approved_sends_command(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    hitl_id = await _make_pending(test_org.org_id, daemon_id)

    resp = await client.post(
        f"/hitl/{hitl_id}/resolve",
        json={"decision": "approved", "reason": "looks good"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["resolved_by"] == test_org.user_id
    assert body["resolution_reason"] == "looks good"
    assert body["resolved_at"] is not None

    assert len(fresh_bus.sent) == 1
    cmd = fresh_bus.sent[0]
    assert cmd.command_type == "hitl.resolve"
    assert cmd.daemon_id == daemon_id
    assert cmd.payload["decision"] == "approved"
    assert cmd.payload["hitl_id"] == hitl_id


async def test_resolve_already_resolved_409(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    hitl_id = await _make_pending(test_org.org_id, daemon_id)

    first = await client.post(
        f"/hitl/{hitl_id}/resolve",
        json={"decision": "denied"},
        headers=test_org.auth_headers(),
    )
    assert first.status_code == 200
    second = await client.post(
        f"/hitl/{hitl_id}/resolve",
        json={"decision": "approved"},
        headers=test_org.auth_headers(),
    )
    assert second.status_code == 409


async def test_resolve_requires_write(make_test_org, client, fresh_bus):
    owner = await make_test_org()
    viewer = await make_test_org(role="viewer")
    # Put a daemon + request in the viewer's own org so RBAC (not 404) is tested.
    daemon_id, _ = await viewer.make_daemon()
    hitl_id = await _make_pending(viewer.org_id, daemon_id)

    resp = await client.post(
        f"/hitl/{hitl_id}/resolve",
        json={"decision": "approved"},
        headers=viewer.auth_headers(),
    )
    assert resp.status_code == 403


async def test_list_filter_by_status(test_org, client):
    daemon_id, _ = await test_org.make_daemon()
    await _make_pending(test_org.org_id, daemon_id)

    resp = await client.get("/hitl?status=pending", headers=test_org.auth_headers())
    assert resp.status_code == 200
    assert all(r["status"] == "pending" for r in resp.json())
    assert len(resp.json()) >= 1

    bad = await client.get("/hitl?status=bogus", headers=test_org.auth_headers())
    assert bad.status_code == 422


# ── timeout sweeper (default-deny) ─────────────────────────────────────────────
async def test_sweeper_expires_overdue_and_denies(test_org, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    hitl_id = await _make_pending(test_org.org_id, daemon_id, expires_in=-10)

    expired = await sweep_expired_hitl()
    assert expired >= 1

    db = await service_db()
    row = (
        await db.table("hitl_requests")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("id", hitl_id)
        .execute()
    ).data[0]
    assert row["status"] == "expired"

    denials = [
        c
        for c in fresh_bus.sent
        if c.command_type == "hitl.resolve" and c.payload.get("hitl_id") == hitl_id
    ]
    assert len(denials) == 1
    assert denials[0].payload["decision"] == "denied"


async def test_sweeper_skips_future_requests(test_org, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    hitl_id = await _make_pending(test_org.org_id, daemon_id, expires_in=3600)

    await sweep_expired_hitl()

    db = await service_db()
    row = (
        await db.table("hitl_requests")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("id", hitl_id)
        .execute()
    ).data[0]
    assert row["status"] == "pending"
