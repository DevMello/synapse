"""Tests for the marketplace + two-tier capabilities unit.

Covers:
  * marketplace: list/get global listings (kind + platform filters), install
    records an org-scoped row, installs list is org-scoped.
  * daemon tier: provisioning inserts a daemon_capabilities row (installing) AND
    emits plugin.install / mcp.configure; the capability.status inbound message
    flips install_status to ready; plugin.remove deletes the daemon capability
    AND its agent_capabilities AND emits the command.
  * agent tier: attach inserts an agent_capabilities row + emits capability.attach;
    detach removes it + emits capability.detach.
  * org-scoping isolation and RBAC (viewer cannot mutate).

No Redis: the inbound handler is exercised via `dispatch(...)` directly.
"""
from __future__ import annotations

import uuid

import pytest_asyncio

from synapse_cloud.command_bus import (
    InMemoryCommandBus,
    get_command_bus,
    set_command_bus,
)
from synapse_cloud.db import service_db
from synapse_cloud.message_registry import (
    CAPABILITY_STATUS,
    MessageContext,
    dispatch,
)


@pytest_asyncio.fixture
def fresh_bus():
    prev = get_command_bus()
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    yield bus
    set_command_bus(prev)


# ── seed helpers ────────────────────────────────────────────────────────────
async def _seed_listing(
    kind: str = "plugin",
    name: str = "test-listing",
    platforms: list[str] | None = None,
) -> str:
    """Insert a global marketplace listing and return its id."""
    db = await service_db()
    row = (
        await db.table("marketplace_listings")
        .insert(
            {
                "kind": kind,
                "name": f"{name}-{uuid.uuid4().hex[:8]}",
                "description": "seeded for tests",
                "platforms": platforms if platforms is not None else ["linux"],
                "version": "1.0.0",
            }
        )
        .execute()
    ).data[0]
    return row["id"]


async def _seed_agent(org, daemon_id: str | None) -> str:
    db = await service_db()
    payload = {
        "org_id": org.org_id,
        "name": f"cap-agent-{uuid.uuid4().hex[:6]}",
        "type": "api",
    }
    if daemon_id is not None:
        payload["daemon_id"] = daemon_id
    row = (await db.table("agents").insert(payload).execute()).data[0]
    return row["id"]


async def _cleanup_listing(listing_id: str) -> None:
    db = await service_db()
    try:
        await db.table("marketplace_listings").delete().eq("id", listing_id).execute()
    except Exception:  # noqa: BLE001
        pass


# ── marketplace: listings ─────────────────────────────────────────────────────
async def test_list_listings(test_org, client):
    listing_id = await _seed_listing()
    try:
        resp = await client.get("/marketplace/listings", headers=test_org.auth_headers())
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()]
        assert listing_id in ids
    finally:
        await _cleanup_listing(listing_id)


async def test_list_listings_kind_and_platform_filter(test_org, client):
    plugin_id = await _seed_listing(kind="plugin", platforms=["linux"])
    skill_id = await _seed_listing(kind="skill", platforms=["darwin"])
    try:
        resp = await client.get(
            "/marketplace/listings",
            params={"kind": "plugin"},
            headers=test_org.auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        kinds = {i["kind"] for i in resp.json()}
        assert kinds == {"plugin"} or "skill" not in kinds
        ids = {i["id"] for i in resp.json()}
        assert plugin_id in ids
        assert skill_id not in ids

        resp2 = await client.get(
            "/marketplace/listings",
            params={"platform": "darwin"},
            headers=test_org.auth_headers(),
        )
        assert resp2.status_code == 200, resp2.text
        ids2 = {i["id"] for i in resp2.json()}
        assert skill_id in ids2
        assert plugin_id not in ids2
    finally:
        await _cleanup_listing(plugin_id)
        await _cleanup_listing(skill_id)


async def test_get_listing(test_org, client):
    listing_id = await _seed_listing()
    try:
        resp = await client.get(
            f"/marketplace/listings/{listing_id}", headers=test_org.auth_headers()
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == listing_id
    finally:
        await _cleanup_listing(listing_id)


async def test_get_listing_404(test_org, client):
    resp = await client.get(
        f"/marketplace/listings/{uuid.uuid4()}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


# ── marketplace: install ──────────────────────────────────────────────────────
async def test_install_records_row(test_org, client):
    listing_id = await _seed_listing()
    daemon_id, _ = await test_org.make_daemon()
    try:
        resp = await client.post(
            f"/marketplace/listings/{listing_id}/install",
            json={"daemon_id": daemon_id},
            headers=test_org.auth_headers(),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["org_id"] == test_org.org_id
        assert body["listing_id"] == listing_id
        assert body["daemon_id"] == daemon_id
        assert body["installed_by"] == test_org.user_id

        # Shows up in this org's installs list.
        installs = await client.get(
            "/marketplace/installs", headers=test_org.auth_headers()
        )
        assert installs.status_code == 200
        assert any(i["id"] == body["id"] for i in installs.json())
    finally:
        await _cleanup_listing(listing_id)


async def test_install_404_for_missing_listing(test_org, client):
    resp = await client.post(
        f"/marketplace/listings/{uuid.uuid4()}/install",
        json={},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


async def test_install_requires_write(make_test_org, client):
    viewer = await make_test_org(role="viewer")
    listing_id = await _seed_listing()
    try:
        resp = await client.post(
            f"/marketplace/listings/{listing_id}/install",
            json={},
            headers=viewer.auth_headers(),
        )
        assert resp.status_code == 403
    finally:
        await _cleanup_listing(listing_id)


async def test_installs_org_scoped(make_test_org, client):
    org_a = await make_test_org()
    org_b = await make_test_org()
    listing_id = await _seed_listing()
    try:
        resp = await client.post(
            f"/marketplace/listings/{listing_id}/install",
            json={},
            headers=org_a.auth_headers(),
        )
        assert resp.status_code == 201, resp.text
        install_id = resp.json()["id"]

        b_installs = await client.get(
            "/marketplace/installs", headers=org_b.auth_headers()
        )
        assert b_installs.status_code == 200
        assert all(i["id"] != install_id for i in b_installs.json())
    finally:
        await _cleanup_listing(listing_id)


# ── daemon tier: provision ────────────────────────────────────────────────────
async def test_provision_plugin_inserts_and_commands(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    resp = await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": "script", "exposed_tools": ["grep"], "args": {"x": 1}},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    cap = resp.json()
    assert cap["install_status"] == "installing"
    assert cap["daemon_id"] == daemon_id
    assert cap["kind"] == "script"

    cmds = [c for c in fresh_bus.sent if c.command_type == "plugin.install"]
    assert len(cmds) == 1
    assert cmds[0].daemon_id == daemon_id
    assert cmds[0].payload["daemon_capability_id"] == cap["id"]


async def test_provision_mcp_uses_mcp_configure(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    resp = await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": "mcp", "endpoint": "http://localhost:9000"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    cmds = [c for c in fresh_bus.sent if c.command_type == "mcp.configure"]
    assert len(cmds) == 1
    assert cmds[0].daemon_id == daemon_id


async def test_provision_bad_kind_422(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    resp = await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": "bogus"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 422
    assert len(fresh_bus.sent) == 0


async def test_provision_requires_write(make_test_org, client, fresh_bus):
    viewer = await make_test_org(role="viewer")
    daemon_id, _ = await viewer.make_daemon()
    resp = await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": "script"},
        headers=viewer.auth_headers(),
    )
    assert resp.status_code == 403
    assert len(fresh_bus.sent) == 0


async def test_provision_daemon_org_scoped(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    daemon_id, _ = await org_a.make_daemon()
    # Org B cannot provision on org A's daemon.
    resp = await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": "script"},
        headers=org_b.auth_headers(),
    )
    assert resp.status_code == 404
    assert len(fresh_bus.sent) == 0


async def test_list_daemon_capabilities(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": "script"},
        headers=test_org.auth_headers(),
    )
    resp = await client.get(
        f"/daemons/{daemon_id}/capabilities", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1


# ── inbound: capability.status ──────────────────────────────────────────────────
async def test_capability_status_flips_to_ready(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    resp = await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": "mcp"},
        headers=test_org.auth_headers(),
    )
    cap_id = resp.json()["id"]

    n = await dispatch(
        CAPABILITY_STATUS,
        MessageContext(daemon_id=daemon_id, org_id=test_org.org_id),
        {
            "daemon_capability_id": cap_id,
            "status": "ready",
            "exposed_tools": ["search", "fetch"],
        },
    )
    assert n >= 1

    db = await service_db()
    rows = (
        await db.table("daemon_capabilities")
        .select("install_status, exposed_tools")
        .eq("org_id", test_org.org_id)
        .eq("id", cap_id)
        .execute()
    ).data
    assert rows[0]["install_status"] == "ready"
    assert set(rows[0]["exposed_tools"]) == {"search", "fetch"}


async def test_capability_status_failed(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    resp = await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": "script"},
        headers=test_org.auth_headers(),
    )
    cap_id = resp.json()["id"]
    await dispatch(
        CAPABILITY_STATUS,
        MessageContext(daemon_id=daemon_id, org_id=test_org.org_id),
        {"daemon_capability_id": cap_id, "status": "failed"},
    )
    db = await service_db()
    rows = (
        await db.table("daemon_capabilities")
        .select("install_status")
        .eq("id", cap_id)
        .execute()
    ).data
    assert rows[0]["install_status"] == "failed"


# ── agent tier: attach / detach ─────────────────────────────────────────────────
async def _provision_cap(client, headers, daemon_id, kind="script") -> str:
    resp = await client.post(
        f"/daemons/{daemon_id}/capabilities",
        json={"kind": kind},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_attach_inserts_and_commands(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _seed_agent(test_org, daemon_id)
    cap_id = await _provision_cap(client, test_org.auth_headers(), daemon_id)

    resp = await client.post(
        f"/agents/{agent_id}/capabilities",
        json={"daemon_capability_id": cap_id},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    row = resp.json()
    assert row["enabled"] is True
    assert row["auto_attached"] is False
    assert row["attached_by"] == test_org.user_id
    assert row["daemon_capability_id"] == cap_id

    cmds = [c for c in fresh_bus.sent if c.command_type == "capability.attach"]
    assert len(cmds) == 1
    assert cmds[0].daemon_id == daemon_id
    assert cmds[0].payload["agent_id"] == agent_id
    assert cmds[0].payload["daemon_capability_id"] == cap_id


async def test_attach_is_idempotent_upsert(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _seed_agent(test_org, daemon_id)
    cap_id = await _provision_cap(client, test_org.auth_headers(), daemon_id)
    for _ in range(2):
        resp = await client.post(
            f"/agents/{agent_id}/capabilities",
            json={"daemon_capability_id": cap_id},
            headers=test_org.auth_headers(),
        )
        assert resp.status_code == 201, resp.text
    resp = await client.get(
        f"/agents/{agent_id}/capabilities", headers=test_org.auth_headers()
    )
    assert len([r for r in resp.json() if r["daemon_capability_id"] == cap_id]) == 1


async def test_attach_requires_write(make_test_org, client, fresh_bus):
    owner = await make_test_org()
    viewer = await make_test_org(role="viewer")
    # Give the viewer their own daemon/agent/cap to attempt the attach on.
    daemon_id, _ = await viewer.make_daemon()
    agent_id = await _seed_agent(viewer, daemon_id)
    # Provision the cap as a write-capable principal of the SAME org as viewer?
    # viewer can't provision; seed the cap directly.
    db = await service_db()
    cap = (
        await db.table("daemon_capabilities")
        .insert(
            {
                "org_id": viewer.org_id,
                "daemon_id": daemon_id,
                "kind": "script",
                "install_status": "ready",
            }
        )
        .execute()
    ).data[0]
    resp = await client.post(
        f"/agents/{agent_id}/capabilities",
        json={"daemon_capability_id": cap["id"]},
        headers=viewer.auth_headers(),
    )
    assert resp.status_code == 403
    assert len(fresh_bus.sent) == 0


async def test_detach_removes_and_commands(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _seed_agent(test_org, daemon_id)
    cap_id = await _provision_cap(client, test_org.auth_headers(), daemon_id)
    await client.post(
        f"/agents/{agent_id}/capabilities",
        json={"daemon_capability_id": cap_id},
        headers=test_org.auth_headers(),
    )

    resp = await client.delete(
        f"/agents/{agent_id}/capabilities/{cap_id}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["detached"] is True

    cmds = [c for c in fresh_bus.sent if c.command_type == "capability.detach"]
    assert len(cmds) == 1
    assert cmds[0].daemon_id == daemon_id

    db = await service_db()
    rows = (
        await db.table("agent_capabilities")
        .select("id")
        .eq("org_id", test_org.org_id)
        .eq("agent_id", agent_id)
        .eq("daemon_capability_id", cap_id)
        .execute()
    ).data
    assert rows == []


async def test_detach_404_when_not_attached(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _seed_agent(test_org, daemon_id)
    cap_id = await _provision_cap(client, test_org.auth_headers(), daemon_id)
    resp = await client.delete(
        f"/agents/{agent_id}/capabilities/{cap_id}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


# ── plugin.remove cascades to agent_capabilities ────────────────────────────────
async def test_remove_daemon_cap_detaches_all_agents(test_org, client, fresh_bus):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _seed_agent(test_org, daemon_id)
    cap_id = await _provision_cap(client, test_org.auth_headers(), daemon_id)
    await client.post(
        f"/agents/{agent_id}/capabilities",
        json={"daemon_capability_id": cap_id},
        headers=test_org.auth_headers(),
    )

    resp = await client.delete(
        f"/daemons/{daemon_id}/capabilities/{cap_id}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text

    remove_cmds = [c for c in fresh_bus.sent if c.command_type == "plugin.remove"]
    assert len(remove_cmds) == 1
    assert remove_cmds[0].payload["daemon_capability_id"] == cap_id

    db = await service_db()
    daemon_rows = (
        await db.table("daemon_capabilities")
        .select("id")
        .eq("id", cap_id)
        .execute()
    ).data
    agent_rows = (
        await db.table("agent_capabilities")
        .select("id")
        .eq("daemon_capability_id", cap_id)
        .execute()
    ).data
    assert daemon_rows == []
    assert agent_rows == []


async def test_remove_daemon_cap_requires_write(make_test_org, client, fresh_bus):
    viewer = await make_test_org(role="viewer")
    daemon_id, _ = await viewer.make_daemon()
    db = await service_db()
    cap = (
        await db.table("daemon_capabilities")
        .insert(
            {
                "org_id": viewer.org_id,
                "daemon_id": daemon_id,
                "kind": "script",
                "install_status": "ready",
            }
        )
        .execute()
    ).data[0]
    resp = await client.delete(
        f"/daemons/{daemon_id}/capabilities/{cap['id']}",
        headers=viewer.auth_headers(),
    )
    assert resp.status_code == 403
    assert len(fresh_bus.sent) == 0


# ── agent-tier org scoping ──────────────────────────────────────────────────────
async def test_agent_capabilities_org_scoped(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    daemon_id, _ = await org_a.make_daemon()
    agent_id = await _seed_agent(org_a, daemon_id)
    # Org B cannot see org A's agent capabilities.
    resp = await client.get(
        f"/agents/{agent_id}/capabilities", headers=org_b.auth_headers()
    )
    assert resp.status_code == 404
