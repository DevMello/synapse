"""Tests for agents CRUD + immutable versioning, deploy/rollback/diff/tags.

Runs against real Supabase with the in-memory command bus + audit seams. Each
test mints an isolated org via `make_test_org`.
"""
from __future__ import annotations

import pytest

from synapse_cloud.command_bus import get_command_bus
from synapse_cloud.services import versioning


async def _create_agent(client, org, **kwargs):
    body = {"name": "alpha", "type": "cli"}
    body.update(kwargs)
    resp = await client.post("/agents", json=body, headers=org.auth_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def test_create_agent_makes_v1(client, test_org):
    agent = await _create_agent(client, test_org, prompt="hello")
    assert agent["org_id"] == test_org.org_id
    assert agent["type"] == "cli"
    assert agent["status"] == "active"
    assert agent["current_version"] == 1

    versions = (
        await client.get(
            f"/agents/{agent['id']}/versions", headers=test_org.auth_headers()
        )
    ).json()
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["prompt"] == "hello"


async def test_create_agent_bad_type(client, test_org):
    resp = await client.post(
        "/agents", json={"name": "x", "type": "nope"}, headers=test_org.auth_headers()
    )
    assert resp.status_code == 422


async def test_list_and_get_agent(client, test_org):
    a = await _create_agent(client, test_org, name="one")
    b = await _create_agent(client, test_org, name="two")

    listed = (await client.get("/agents", headers=test_org.auth_headers())).json()
    ids = {x["id"] for x in listed}
    assert {a["id"], b["id"]} <= ids

    got = await client.get(f"/agents/{a['id']}", headers=test_org.auth_headers())
    assert got.status_code == 200
    assert got.json()["name"] == "one"


async def test_get_agent_404(client, test_org):
    import uuid

    resp = await client.get(
        f"/agents/{uuid.uuid4()}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


async def test_org_isolation(client, make_test_org):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent = await _create_agent(client, org_a)

    # org_b cannot see org_a's agent
    resp = await client.get(f"/agents/{agent['id']}", headers=org_b.auth_headers())
    assert resp.status_code == 404
    listed = (await client.get("/agents", headers=org_b.auth_headers())).json()
    assert all(x["id"] != agent["id"] for x in listed)


async def test_patch_agent_fields(client, test_org):
    agent = await _create_agent(client, test_org)
    resp = await client.patch(
        f"/agents/{agent['id']}",
        json={"name": "renamed", "limits": {"max_cost": 10}},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "renamed"
    assert body["limits"] == {"max_cost": 10}


async def test_archive_via_status(client, test_org):
    agent = await _create_agent(client, test_org)
    resp = await client.patch(
        f"/agents/{agent['id']}",
        json={"status": "archived"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


async def test_patch_bad_status(client, test_org):
    agent = await _create_agent(client, test_org)
    resp = await client.patch(
        f"/agents/{agent['id']}",
        json={"status": "bogus"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 422


async def test_patch_no_fields(client, test_org):
    agent = await _create_agent(client, test_org)
    resp = await client.patch(
        f"/agents/{agent['id']}", json={}, headers=test_org.auth_headers()
    )
    assert resp.status_code == 400


async def test_create_agent_unknown_daemon(client, test_org):
    import uuid

    resp = await client.post(
        "/agents",
        json={"name": "x", "type": "cli", "daemon_id": str(uuid.uuid4())},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


# ── versioning ──────────────────────────────────────────────────────────────
async def test_versions_monotonic_and_immutable(client, test_org):
    agent = await _create_agent(client, test_org, prompt="v1")
    aid = agent["id"]

    v2 = await client.post(
        f"/agents/{aid}/versions",
        json={"prompt": "v2", "message": "second"},
        headers=test_org.auth_headers(),
    )
    assert v2.status_code == 201
    assert v2.json()["version"] == 2

    v3 = await client.post(
        f"/agents/{aid}/versions",
        json={"prompt": "v3"},
        headers=test_org.auth_headers(),
    )
    assert v3.json()["version"] == 3

    # current_version bumped
    agent_now = (
        await client.get(f"/agents/{aid}", headers=test_org.auth_headers())
    ).json()
    assert agent_now["current_version"] == 3

    # v1 unchanged (immutable)
    v1 = (
        await client.get(f"/agents/{aid}/versions/1", headers=test_org.auth_headers())
    ).json()
    assert v1["prompt"] == "v1"


async def test_get_version_404(client, test_org):
    agent = await _create_agent(client, test_org)
    resp = await client.get(
        f"/agents/{agent['id']}/versions/99", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


# ── deploy / update_prompt commands ───────────────────────────────────────────
async def test_create_version_emits_update_prompt(client, test_org):
    daemon_id, _ = await test_org.make_daemon()
    agent = await _create_agent(client, test_org, daemon_id=daemon_id, prompt="v1")
    aid = agent["id"]

    bus = get_command_bus()
    before = len(bus.sent)
    resp = await client.post(
        f"/agents/{aid}/versions",
        json={"prompt": "v2"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201
    new = bus.sent[before:]
    assert any(
        c.command_type == "agent.update_prompt"
        and c.daemon_id == daemon_id
        and c.payload["version"] == 2
        and c.payload["prompt"] == "v2"
        for c in new
    )


async def test_create_version_deploy_flag(client, test_org):
    daemon_id, _ = await test_org.make_daemon()
    agent = await _create_agent(client, test_org, daemon_id=daemon_id)
    aid = agent["id"]

    bus = get_command_bus()
    before = len(bus.sent)
    await client.post(
        f"/agents/{aid}/versions",
        json={"prompt": "deployed", "deploy": True},
        headers=test_org.auth_headers(),
    )
    new = bus.sent[before:]
    assert any(c.command_type == "agent.deploy" and c.daemon_id == daemon_id for c in new)


async def test_no_daemon_skips_send(client, test_org):
    agent = await _create_agent(client, test_org)  # no daemon_id
    aid = agent["id"]

    bus = get_command_bus()
    before = len(bus.sent)
    resp = await client.post(
        f"/agents/{aid}/versions",
        json={"prompt": "v2"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201  # version still returned
    assert resp.json()["version"] == 2
    # nothing for this agent's (no) daemon
    new = bus.sent[before:]
    assert all(c.payload.get("agent_id") != aid for c in new)


async def test_create_agent_deploy_flag(client, test_org):
    daemon_id, _ = await test_org.make_daemon()
    bus = get_command_bus()
    before = len(bus.sent)
    agent = await _create_agent(
        client, test_org, daemon_id=daemon_id, prompt="p", deploy=True
    )
    new = bus.sent[before:]
    assert any(
        c.command_type == "agent.deploy"
        and c.daemon_id == daemon_id
        and c.payload["agent_id"] == agent["id"]
        for c in new
    )


# ── rollback ──────────────────────────────────────────────────────────────────
async def test_rollback_appends_new_version(client, test_org):
    daemon_id, _ = await test_org.make_daemon()
    agent = await _create_agent(client, test_org, daemon_id=daemon_id, prompt="v1")
    aid = agent["id"]
    await client.post(
        f"/agents/{aid}/versions",
        json={"prompt": "v2"},
        headers=test_org.auth_headers(),
    )

    bus = get_command_bus()
    before = len(bus.sent)
    resp = await client.post(
        f"/agents/{aid}/rollback",
        json={"version": 1},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    rolled = resp.json()
    assert rolled["version"] == 3  # appended, not mutated
    assert rolled["prompt"] == "v1"  # copies target content

    # history intact: 3 versions, v2 still present
    versions = (
        await client.get(f"/agents/{aid}/versions", headers=test_org.auth_headers())
    ).json()
    assert {v["version"] for v in versions} == {1, 2, 3}

    # emitted update_prompt for the rolled-back content
    new = bus.sent[before:]
    assert any(
        c.command_type == "agent.update_prompt"
        and c.payload["version"] == 3
        and c.payload["prompt"] == "v1"
        for c in new
    )


async def test_rollback_unknown_version(client, test_org):
    agent = await _create_agent(client, test_org)
    resp = await client.post(
        f"/agents/{agent['id']}/rollback",
        json={"version": 42},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


# ── diff ──────────────────────────────────────────────────────────────────────
async def test_diff_versions(client, test_org):
    agent = await _create_agent(client, test_org, prompt="line one\nline two\n")
    aid = agent["id"]
    await client.post(
        f"/agents/{aid}/versions",
        json={"prompt": "line one\nline changed\n", "config": {"k": 1}},
        headers=test_org.auth_headers(),
    )

    resp = await client.get(
        f"/agents/{aid}/versions/1/diff/2", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    diff = resp.json()
    assert diff["from_version"] == 1
    assert diff["to_version"] == 2
    assert diff["prompt"]["changed"] is True
    assert "line changed" in diff["prompt"]["diff"]
    assert diff["config"]["changed"] is True


async def test_diff_404(client, test_org):
    agent = await _create_agent(client, test_org)
    resp = await client.get(
        f"/agents/{agent['id']}/versions/1/diff/9", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


# ── tags ──────────────────────────────────────────────────────────────────────
async def test_set_and_clear_tags(client, test_org):
    agent = await _create_agent(client, test_org)
    aid = agent["id"]

    resp = await client.patch(
        f"/agents/{aid}/versions/1",
        json={"tags": ["known-good", "production"]},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 200
    assert set(resp.json()["tags"]) == {"known-good", "production"}

    # prompt/config remain immutable through a tag patch
    cleared = await client.patch(
        f"/agents/{aid}/versions/1",
        json={"tags": []},
        headers=test_org.auth_headers(),
    )
    assert cleared.json()["tags"] == []


async def test_patch_tags_404(client, test_org):
    agent = await _create_agent(client, test_org)
    resp = await client.patch(
        f"/agents/{agent['id']}/versions/77",
        json={"tags": ["x"]},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


# ── rbac ──────────────────────────────────────────────────────────────────────
async def test_viewer_cannot_create(client, make_test_org):
    viewer = await make_test_org(role="viewer")
    resp = await client.post(
        "/agents", json={"name": "x", "type": "cli"}, headers=viewer.auth_headers()
    )
    assert resp.status_code == 403


# ── service helper unit ───────────────────────────────────────────────────────
def test_diff_versions_no_change():
    a = {"version": 1, "prompt": "same", "config": {"x": 1}}
    b = {"version": 2, "prompt": "same", "config": {"x": 1}}
    d = versioning.diff_versions(a, b)
    assert d["prompt"]["changed"] is False
    assert d["config"]["changed"] is False
