"""Tests for the daemon device-code auth flow (unit 1)."""
from __future__ import annotations

import pytest

from supabase import acreate_client
from supabase.lib.client_options import AsyncClientOptions

from synapse_cloud.command_bus import get_command_bus
from synapse_cloud.config import get_settings
from synapse_cloud.db import reset_db_cache, service_db
from synapse_cloud.security import (
    decode_daemon_access_token,
    hash_token,
    new_opaque_token,
)

pytestmark = pytest.mark.asyncio

_PASSWORD = "Test-Passw0rd!"


@pytest.fixture(autouse=True)
def _fresh_db_client():
    """Each test runs on its own event loop; the cached service client binds its
    connection to the loop that created it. Drop the cache after every test so a
    test never reuses a client bound to a closed loop (Windows proactor)."""
    yield
    reset_db_cache()


async def _fresh_headers(org) -> dict[str, str]:
    """Mint fresh, *valid* auth headers for an org's user.

    The conftest `make_test_org` fixture signs out after sign-in, which revokes
    that session globally — so `org.access_token` is no longer accepted by
    `auth.get_user`. We re-sign-in on a throwaway anon client (and don't sign
    out) to get a live token for authenticated requests.
    """
    s = get_settings()
    anon = await acreate_client(
        s.supabase_url,
        s.supabase_anon_key,
        options=AsyncClientOptions(auto_refresh_token=False, persist_session=False),
    )
    signin = await anon.auth.sign_in_with_password(
        {"email": org.email, "password": _PASSWORD}
    )
    return {
        "Authorization": f"Bearer {signin.session.access_token}",
        "X-Org-Id": org.org_id,
    }

_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


async def _request_code(client) -> dict:
    resp = await client.post(
        "/auth/device/code",
        json={
            "hostname": "vps-01",
            "os_version": "ubuntu 24.04",
            "daemon_version": "0.1.0",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_device_code_returns_codes(client):
    body = await _request_code(client)
    assert body["device_code"]
    assert "-" in body["user_code"]
    assert body["interval"] == 5
    assert body["expires_in"] > 0
    assert body["verification_uri"]
    assert body["user_code"] in body["verification_uri_complete"]

    # device_code is stored hashed, never in plaintext.
    db = await service_db()
    rows = (
        await db.table("device_authorizations")
        .select("device_code_hash, user_code, status")
        .eq("user_code", body["user_code"])
        .execute()
    ).data
    assert rows
    assert rows[0]["device_code_hash"] == hash_token(body["device_code"])
    assert rows[0]["status"] == "pending"
    # cleanup
    await db.table("device_authorizations").delete().eq(
        "user_code", body["user_code"]
    ).execute()


async def test_token_pending_before_approval(client):
    body = await _request_code(client)
    resp = await client.post(
        "/auth/device/token",
        json={"grant_type": _DEVICE_GRANT, "device_code": body["device_code"]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "authorization_pending"

    db = await service_db()
    await db.table("device_authorizations").delete().eq(
        "user_code", body["user_code"]
    ).execute()


async def test_full_flow_approve_then_token_then_refresh(client, test_org):
    body = await _request_code(client)

    # Web UI approves with the user_code.
    approve = await client.post(
        "/auth/device/approve",
        json={"user_code": body["user_code"]},
        headers=await _fresh_headers(test_org),
    )
    assert approve.status_code == 200, approve.text
    daemon_id = approve.json()["daemon_id"]
    assert approve.json()["status"] == "authorized"
    test_org.daemon_ids.append(daemon_id)

    # Daemon polls for tokens.
    tok = await client.post(
        "/auth/device/token",
        json={"grant_type": _DEVICE_GRANT, "device_code": body["device_code"]},
    )
    assert tok.status_code == 200, tok.text
    data = tok.json()
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] > 0
    access1 = data["access_token"]
    refresh1 = data["refresh_token"]

    # Access token decodes to the right daemon + org.
    principal = decode_daemon_access_token(access1)
    assert principal.daemon_id == daemon_id
    assert principal.org_id == test_org.org_id

    # Daemon row carries the daemon metadata + a refresh-token hash.
    db = await service_db()
    daemon = (
        await db.table("daemons").select("*").eq("id", daemon_id).execute()
    ).data[0]
    assert daemon["hostname"] == "vps-01"
    assert daemon["os_version"] == "ubuntu 24.04"
    assert daemon["refresh_token_hash"] == hash_token(refresh1)

    # Refresh rotation: old refresh produces NEW access + refresh tokens.
    refreshed = await client.post(
        "/auth/token",
        json={"grant_type": "refresh_token", "refresh_token": refresh1},
    )
    assert refreshed.status_code == 200, refreshed.text
    rdata = refreshed.json()
    assert rdata["access_token"] != access1 or rdata["refresh_token"] != refresh1
    assert rdata["refresh_token"] != refresh1  # rotated

    # The old refresh token no longer works (rotated out).
    stale = await client.post(
        "/auth/token",
        json={"grant_type": "refresh_token", "refresh_token": refresh1},
    )
    assert stale.status_code == 400
    assert stale.json()["detail"]["error"] == "invalid_grant"

    # The new refresh token does work.
    again = await client.post(
        "/auth/token",
        json={"grant_type": "refresh_token", "refresh_token": rdata["refresh_token"]},
    )
    assert again.status_code == 200, again.text


async def test_approve_unknown_user_code(client, test_org):
    resp = await client.post(
        "/auth/device/approve",
        json={"user_code": "ZZZZ-9999"},
        headers=await _fresh_headers(test_org),
    )
    assert resp.status_code == 404


async def test_approve_requires_auth(client):
    body = await _request_code(client)
    resp = await client.post(
        "/auth/device/approve",
        json={"user_code": body["user_code"]},
    )
    assert resp.status_code == 401

    db = await service_db()
    await db.table("device_authorizations").delete().eq(
        "user_code", body["user_code"]
    ).execute()


async def test_token_invalid_device_code(client):
    resp = await client.post(
        "/auth/device/token",
        json={"grant_type": _DEVICE_GRANT, "device_code": new_opaque_token()},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_grant"


async def test_token_bad_grant_type(client):
    resp = await client.post(
        "/auth/device/token",
        json={"grant_type": "password", "device_code": "x"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "unsupported_grant_type"


async def test_refresh_invalid_token(client):
    resp = await client.post(
        "/auth/token",
        json={"grant_type": "refresh_token", "refresh_token": new_opaque_token()},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_grant"


async def test_revoke_kills_socket_and_blocks_refresh(client, test_org):
    body = await _request_code(client)
    approve = await client.post(
        "/auth/device/approve",
        json={"user_code": body["user_code"]},
        headers=await _fresh_headers(test_org),
    )
    daemon_id = approve.json()["daemon_id"]
    test_org.daemon_ids.append(daemon_id)

    tok = await client.post(
        "/auth/device/token",
        json={"grant_type": _DEVICE_GRANT, "device_code": body["device_code"]},
    )
    refresh1 = tok.json()["refresh_token"]

    # Revoke (admin/owner) — should close the daemon WS and clear the refresh hash.
    bus = get_command_bus()
    before = len(getattr(bus, "closed", []))
    revoke = await client.post(
        f"/daemons/{daemon_id}/revoke",
        headers=await _fresh_headers(test_org),
    )
    assert revoke.status_code == 204, revoke.text
    assert (daemon_id, "revoked") in bus.closed[before:]

    db = await service_db()
    daemon = (
        await db.table("daemons").select("*").eq("id", daemon_id).execute()
    ).data[0]
    assert daemon["revoked_at"] is not None
    assert daemon["status"] == "revoked"
    assert daemon["refresh_token_hash"] is None

    # Refresh after revoke is rejected.
    resp = await client.post(
        "/auth/token",
        json={"grant_type": "refresh_token", "refresh_token": refresh1},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_grant"


async def test_revoke_requires_admin(client, make_test_org):
    org = await make_test_org(role="viewer")
    daemon_id, _ = await org.make_daemon()
    resp = await client.post(
        f"/daemons/{daemon_id}/revoke",
        headers=await _fresh_headers(org),
    )
    assert resp.status_code == 403


async def test_revoke_other_org_daemon_404(client, make_test_org):
    org_a = await make_test_org()
    org_b = await make_test_org()
    daemon_id, _ = await org_a.make_daemon()
    resp = await client.post(
        f"/daemons/{daemon_id}/revoke",
        headers=await _fresh_headers(org_b),
    )
    assert resp.status_code == 404
