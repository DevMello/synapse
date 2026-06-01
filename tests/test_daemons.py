"""Tests for the daemons REST + uptime unit.

Run against the real Supabase project; orgs are minted per-test via
`make_test_org` for RLS isolation. Presence rows are inserted directly through
the service-role client to exercise the online/offline derivation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from synapse_cloud.db import service_db


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def _insert_presence(
    daemon_id: str, org_id: str, *, expires_at: datetime, last_heartbeat: datetime | None = None
) -> None:
    db = await service_db()
    row = {
        "daemon_id": daemon_id,
        "org_id": org_id,
        "hub_node": "hub-test",
        "expires_at": _iso(expires_at),
    }
    if last_heartbeat is not None:
        row["last_heartbeat"] = _iso(last_heartbeat)
    await db.table("daemon_presence").upsert(row).execute()


async def test_list_requires_auth(client):
    resp = await client.get("/daemons")
    assert resp.status_code == 401


async def test_list_empty_org(client, test_org):
    resp = await client.get("/daemons", headers=test_org.auth_headers())
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_offline_when_no_presence(client, test_org):
    daemon_id, _ = await test_org.make_daemon(name="d1")
    resp = await client.get("/daemons", headers=test_org.auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == daemon_id
    assert body[0]["status"] == "offline"
    assert body[0]["name"] == "d1"
    assert body[0]["tags"] == []
    assert body[0]["uptime_seconds"] is None


async def test_online_when_presence_in_future(client, test_org):
    daemon_id, _ = await test_org.make_daemon(name="online-d")
    now = datetime.now(timezone.utc)
    await _insert_presence(
        daemon_id,
        test_org.org_id,
        expires_at=now + timedelta(minutes=5),
        last_heartbeat=now - timedelta(seconds=30),
    )
    resp = await client.get(f"/daemons/{daemon_id}", headers=test_org.auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "online"
    assert body["hub_node"] == "hub-test"
    assert body["last_heartbeat"] is not None
    assert body["uptime_seconds"] is not None
    assert body["uptime_seconds"] >= 0


async def test_offline_when_presence_expired(client, test_org):
    daemon_id, _ = await test_org.make_daemon(name="stale-d")
    now = datetime.now(timezone.utc)
    await _insert_presence(
        daemon_id, test_org.org_id, expires_at=now - timedelta(minutes=1)
    )
    resp = await client.get(f"/daemons/{daemon_id}", headers=test_org.auth_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "offline"


async def test_revoked_overrides_presence(client, test_org):
    daemon_id, _ = await test_org.make_daemon(name="revoked-d")
    db = await service_db()
    await db.table("daemons").update(
        {"revoked_at": _iso(datetime.now(timezone.utc))}
    ).eq("id", daemon_id).execute()
    # Even with a live presence row, status must be 'revoked'.
    await _insert_presence(
        daemon_id,
        test_org.org_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    resp = await client.get(f"/daemons/{daemon_id}", headers=test_org.auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "revoked"
    assert body["revoked_at"] is not None


async def test_get_unknown_is_404(client, test_org):
    import uuid

    resp = await client.get(
        f"/daemons/{uuid.uuid4()}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


async def test_get_other_org_is_404(client, make_test_org):
    org_a = await make_test_org()
    org_b = await make_test_org()
    daemon_id, _ = await org_a.make_daemon(name="a-daemon")
    # org_b must not see org_a's daemon.
    resp = await client.get(f"/daemons/{daemon_id}", headers=org_b.auth_headers())
    assert resp.status_code == 404


async def test_list_is_org_scoped(client, make_test_org):
    org_a = await make_test_org()
    org_b = await make_test_org()
    await org_a.make_daemon(name="a-daemon")
    resp = await client.get("/daemons", headers=org_b.auth_headers())
    assert resp.status_code == 200
    assert resp.json() == []


async def test_patch_updates_name_and_tags(client, test_org):
    daemon_id, _ = await test_org.make_daemon(name="before")
    resp = await client.patch(
        f"/daemons/{daemon_id}",
        headers=test_org.auth_headers(),
        json={"name": "after", "tags": ["prod", "edge"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "after"
    assert body["tags"] == ["prod", "edge"]


async def test_patch_ignores_protected_fields(client, test_org):
    daemon_id, _ = await test_org.make_daemon(name="keep")
    resp = await client.patch(
        f"/daemons/{daemon_id}",
        headers=test_org.auth_headers(),
        json={
            "name": "keep",
            "status": "online",
            "revoked_at": _iso(datetime.now(timezone.utc)),
            "refresh_token_hash": "evil",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["revoked_at"] is None
    # stored status should remain the seeded 'offline', not the injected value.
    assert body["stored_status"] == "offline"


async def test_patch_empty_body_is_400(client, test_org):
    daemon_id, _ = await test_org.make_daemon(name="nochange")
    resp = await client.patch(
        f"/daemons/{daemon_id}", headers=test_org.auth_headers(), json={}
    )
    assert resp.status_code == 400


async def test_patch_unknown_is_404(client, test_org):
    import uuid

    resp = await client.patch(
        f"/daemons/{uuid.uuid4()}",
        headers=test_org.auth_headers(),
        json={"name": "x"},
    )
    assert resp.status_code == 404


async def test_patch_requires_write_role(client, make_test_org):
    viewer_org = await make_test_org(role="viewer")
    # Need a daemon in that org to target; make_daemon inserts directly.
    daemon_id, _ = await viewer_org.make_daemon(name="v")
    resp = await client.patch(
        f"/daemons/{daemon_id}",
        headers=viewer_org.auth_headers(),
        json={"name": "nope"},
    )
    assert resp.status_code == 403
