"""Agent-orchestration grant minting/listing/revoking + audit ingest.

Mirrors test_agents.py: real Supabase, the `client` ASGI fixture, and `make_test_org`.
Side-effect seams (audit, command bus) are swapped for in-memory fakes per test.
"""
from __future__ import annotations

import uuid

import pytest

from synapse_cloud.audit import FakeAuditWriter, set_audit
from synapse_cloud.command_bus import InMemoryCommandBus, set_command_bus
from synapse_cloud.message_registry import MessageContext
from synapse_cloud.orchestration_crypto import verify_core
from synapse_cloud.routers.orchestration import handle_agent_orchestrate

pytestmark = pytest.mark.asyncio


async def _make_agent_with_daemon(client, org) -> tuple[str, str]:
    daemon_id, _ = await org.make_daemon()
    resp = await client.post(
        "/agents",
        json={"name": "planner", "type": "cli", "daemon_id": daemon_id},
        headers=org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], daemon_id


async def test_mint_grant_signs_and_pushes(client, test_org):
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    agent_id, daemon_id = await _make_agent_with_daemon(client, test_org)

    resp = await client.post(
        f"/agents/{agent_id}/orchestration-grants",
        json={"verbs": ["run"], "target_allow": ["tag:safe"], "max_depth": 2},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    grant = resp.json()
    assert grant["signature"]
    assert grant["daemon_id"] == daemon_id

    # The signed grant was pushed to the daemon, and the signature verifies.
    pushes = [c for c in bus.sent if c.command_type == "orchestration.grant"]
    assert len(pushes) == 1
    p = pushes[0].payload
    assert verify_core(p["core"], p["signature"], p["public_key"]) is True
    # Tampering the core breaks verification.
    bad = dict(p["core"], max_depth=99)
    assert verify_core(bad, p["signature"], p["public_key"]) is False


async def test_list_grants(client, test_org):
    set_command_bus(InMemoryCommandBus())
    agent_id, _ = await _make_agent_with_daemon(client, test_org)
    await client.post(
        f"/agents/{agent_id}/orchestration-grants",
        json={"verbs": ["run"]},
        headers=test_org.auth_headers(),
    )
    resp = await client.get(
        f"/agents/{agent_id}/orchestration-grants", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_revoke_halts_tree(client, test_org):
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    agent_id, _ = await _make_agent_with_daemon(client, test_org)
    grant = (
        await client.post(
            f"/agents/{agent_id}/orchestration-grants",
            json={"verbs": ["run"]},
            headers=test_org.auth_headers(),
        )
    ).json()

    resp = await client.post(
        f"/orchestration-grants/{grant['id']}/revoke", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    assert resp.json()["revoked_at"] is not None
    types = {c.command_type for c in bus.sent}
    assert "grant.revoke" in types
    assert "orchestration.halt" in types


async def test_viewer_cannot_mint(client, make_test_org):
    set_command_bus(InMemoryCommandBus())
    owner = await make_test_org(role="owner")
    # The agent must exist; create it as owner, then attempt mint as a viewer in the same org.
    daemon_id, _ = await owner.make_daemon()
    agent_id = (
        await client.post(
            "/agents",
            json={"name": "planner", "type": "cli", "daemon_id": daemon_id},
            headers=owner.auth_headers(),
        )
    ).json()["id"]

    viewer = await make_test_org(role="viewer")
    # viewer is in a *different* org here; assert their role gate fires (403, not 404-after-write).
    resp = await client.post(
        f"/agents/{agent_id}/orchestration-grants",
        json={"verbs": ["run"]},
        headers=viewer.auth_headers(),
    )
    assert resp.status_code == 403


async def test_invalid_verb_rejected(client, test_org):
    set_command_bus(InMemoryCommandBus())
    agent_id, _ = await _make_agent_with_daemon(client, test_org)
    resp = await client.post(
        f"/agents/{agent_id}/orchestration-grants",
        json={"verbs": ["delete"]},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 422


async def test_agent_orchestrate_ingest_audits_and_lineage(client, test_org):
    from synapse_cloud.db import service_db

    set_command_bus(InMemoryCommandBus())
    audit = FakeAuditWriter()
    set_audit(audit)

    agent_id, daemon_id = await _make_agent_with_daemon(client, test_org)
    child_run_id = str(uuid.uuid4())
    root_run_id = str(uuid.uuid4())

    ctx = MessageContext(daemon_id=daemon_id, org_id=test_org.org_id)
    await handle_agent_orchestrate(
        ctx,
        {
            "verb": "run",
            "grant_id": str(uuid.uuid4()),
            "child_run_id": child_run_id,
            "target_agent_id": agent_id,
            "initiator_agent_id": agent_id,
            "root_run_id": root_run_id,
            "parent_run_id": root_run_id,
            "depth": 1,
        },
    )

    assert any(e["action"] == "agent.orchestrate" for e in audit.events)

    db = await service_db()
    row = (
        await db.table("runs").select("*").eq("id", child_run_id).execute()
    ).data[0]
    assert row["initiator"] == "agent"
    assert row["root_run_id"] == root_run_id
    assert row["depth"] == 1
