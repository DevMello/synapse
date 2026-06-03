"""Tests for the identity & tenancy router.

Runs against the REAL Supabase project via the shared conftest fixtures. Each
test mints isolated orgs through `make_test_org` so concurrent workers don't
collide.
"""
from __future__ import annotations

import uuid


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
async def test_me_requires_auth(client):
    resp = await client.get("/me")
    assert resp.status_code == 401


async def test_me_returns_principal_and_profile(client, test_org):
    resp = await client.get("/me", headers=test_org.auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == test_org.user_id
    assert body["org_id"] == test_org.org_id
    assert body["role"] == "owner"
    assert body["email"] == test_org.email
    assert body["display_name"]


# --------------------------------------------------------------------------- #
# Orgs
# --------------------------------------------------------------------------- #
async def test_get_current_org(client, test_org):
    resp = await client.get("/orgs/current", headers=test_org.auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == test_org.org_id
    assert "name" in body
    assert isinstance(body["settings"], dict)


async def test_patch_current_org_admin(client, test_org):
    new_name = f"renamed-{uuid.uuid4().hex[:8]}"
    resp = await client.patch(
        "/orgs/current",
        headers=test_org.auth_headers(),
        json={"name": new_name, "settings": {"theme": "dark"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == new_name
    assert body["settings"] == {"theme": "dark"}


async def test_patch_current_org_rejects_non_admin(client, make_test_org):
    operator = await make_test_org(role="operator")
    resp = await client.patch(
        "/orgs/current",
        headers=operator.auth_headers(),
        json={"name": "nope"},
    )
    assert resp.status_code == 403


async def test_patch_current_org_empty_body(client, test_org):
    resp = await client.patch(
        "/orgs/current", headers=test_org.auth_headers(), json={}
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Members
# --------------------------------------------------------------------------- #
async def test_list_members_includes_owner(client, test_org):
    resp = await client.get("/members", headers=test_org.auth_headers())
    assert resp.status_code == 200
    members = resp.json()
    by_id = {m["user_id"]: m for m in members}
    assert test_org.user_id in by_id
    owner = by_id[test_org.user_id]
    assert owner["role"] == "owner"
    assert owner["email"] == test_org.email


async def test_add_member_creates_auth_user(client, test_org):
    email = f"invitee-{uuid.uuid4().hex[:10]}@synapse.test"
    resp = await client.post(
        "/members",
        headers=test_org.auth_headers(),
        json={"email": email, "role": "operator"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == email
    assert body["role"] == "operator"
    assert body["org_id"] == test_org.org_id
    new_user_id = body["user_id"]

    # Member now appears in the list.
    listed = await client.get("/members", headers=test_org.auth_headers())
    assert new_user_id in {m["user_id"] for m in listed.json()}

    # Clean up the auth user we created out-of-band (not tracked by fixture).
    from synapse_cloud.db import service_db

    db = await service_db()
    try:
        await db.auth.admin.delete_user(new_user_id)
    except Exception:  # noqa: BLE001
        pass


async def test_add_member_rejects_duplicate(client, test_org):
    # Owner is already a member; adding the same email again should conflict.
    resp = await client.post(
        "/members",
        headers=test_org.auth_headers(),
        json={"email": test_org.email, "role": "viewer"},
    )
    assert resp.status_code == 409


async def test_add_member_rejects_invalid_role(client, test_org):
    email = f"invitee-{uuid.uuid4().hex[:10]}@synapse.test"
    resp = await client.post(
        "/members",
        headers=test_org.auth_headers(),
        json={"email": email, "role": "superuser"},
    )
    assert resp.status_code == 422


async def test_add_member_requires_admin(client, make_test_org):
    operator = await make_test_org(role="operator")
    email = f"invitee-{uuid.uuid4().hex[:10]}@synapse.test"
    resp = await client.post(
        "/members",
        headers=operator.auth_headers(),
        json={"email": email, "role": "viewer"},
    )
    assert resp.status_code == 403


async def test_update_member_role(client, test_org):
    email = f"invitee-{uuid.uuid4().hex[:10]}@synapse.test"
    add = await client.post(
        "/members",
        headers=test_org.auth_headers(),
        json={"email": email, "role": "viewer"},
    )
    assert add.status_code == 201
    uid = add.json()["user_id"]

    resp = await client.patch(
        f"/members/{uid}",
        headers=test_org.auth_headers(),
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    from synapse_cloud.db import service_db

    db = await service_db()
    try:
        await db.auth.admin.delete_user(uid)
    except Exception:  # noqa: BLE001
        pass


async def test_update_member_not_found(client, test_org):
    resp = await client.patch(
        f"/members/{uuid.uuid4()}",
        headers=test_org.auth_headers(),
        json={"role": "admin"},
    )
    assert resp.status_code == 404


async def test_cannot_demote_last_owner(client, test_org):
    resp = await client.patch(
        f"/members/{test_org.user_id}",
        headers=test_org.auth_headers(),
        json={"role": "admin"},
    )
    assert resp.status_code == 409


async def test_remove_member(client, test_org):
    email = f"invitee-{uuid.uuid4().hex[:10]}@synapse.test"
    add = await client.post(
        "/members",
        headers=test_org.auth_headers(),
        json={"email": email, "role": "viewer"},
    )
    assert add.status_code == 201
    uid = add.json()["user_id"]

    resp = await client.delete(
        f"/members/{uid}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 204

    listed = await client.get("/members", headers=test_org.auth_headers())
    assert uid not in {m["user_id"] for m in listed.json()}

    from synapse_cloud.db import service_db

    db = await service_db()
    try:
        await db.auth.admin.delete_user(uid)
    except Exception:  # noqa: BLE001
        pass


async def test_cannot_remove_last_owner(client, test_org):
    resp = await client.delete(
        f"/members/{test_org.user_id}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 409


async def test_remove_member_not_found(client, test_org):
    resp = await client.delete(
        f"/members/{uuid.uuid4()}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404
