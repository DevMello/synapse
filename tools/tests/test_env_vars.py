"""Tests for the env-var relay unit (zero-knowledge for values).

Covers: public-key endpoint (key returned / 404 / 409), set relays ciphertext
via the command bus while persisting NAME-only (no value/ciphertext anywhere),
list returns metadata only, delete commands + removes the ref, the inbound
`env.local` handler creates an origin='local' ref, org scoping, and RBAC.
"""
from __future__ import annotations

import pytest_asyncio

from synapse_cloud.command_bus import (
    InMemoryCommandBus,
    get_command_bus,
    set_command_bus,
)
from synapse_cloud.db import service_db
from synapse_cloud.message_registry import ENV_VAR_LOCAL, MessageContext, dispatch

_PUBKEY = "Zm9vYmFy" * 6  # arbitrary base64-ish stand-in for an X25519 pubkey
_CIPHERTEXT = "c2VhbGVkLWJveC1jaXBoZXJ0ZXh0"  # base64 "sealed-box-ciphertext"


@pytest_asyncio.fixture
def fresh_bus():
    prev = get_command_bus()
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    yield bus
    set_command_bus(prev)


async def _make_agent_with_daemon(org, *, with_key: bool = True) -> tuple[str, str]:
    """Create a daemon (optionally with a pubkey) + an agent owned by it."""
    daemon_id, _ = await org.make_daemon()
    db = await service_db()
    if with_key:
        await db.table("daemons").update({"e2e_public_key": _PUBKEY}).eq(
            "id", daemon_id
        ).execute()
    agent = (
        await db.table("agents")
        .insert(
            {
                "org_id": org.org_id,
                "daemon_id": daemon_id,
                "name": "env-agent",
                "type": "cli",
                "status": "active",
            }
        )
        .execute()
    ).data[0]
    return agent["id"], daemon_id


async def _make_agent_no_daemon(org) -> str:
    db = await service_db()
    agent = (
        await db.table("agents")
        .insert(
            {
                "org_id": org.org_id,
                "name": "lonely-agent",
                "type": "cli",
                "status": "active",
            }
        )
        .execute()
    ).data[0]
    return agent["id"]


# ── public-key ──────────────────────────────────────────────────────────────
async def test_public_key_returned(test_org, client):
    agent_id, daemon_id = await _make_agent_with_daemon(test_org)
    resp = await client.get(
        f"/agents/{agent_id}/env/public-key", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["e2e_public_key"] == _PUBKEY
    assert body["daemon_id"] == daemon_id


async def test_public_key_409_when_no_daemon(test_org, client):
    agent_id = await _make_agent_no_daemon(test_org)
    resp = await client.get(
        f"/agents/{agent_id}/env/public-key", headers=test_org.auth_headers()
    )
    assert resp.status_code == 409


async def test_public_key_404_when_no_key(test_org, client):
    agent_id, _ = await _make_agent_with_daemon(test_org, with_key=False)
    resp = await client.get(
        f"/agents/{agent_id}/env/public-key", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


# ── set: relay ciphertext, store name only ─────────────────────────────────────
async def test_set_relays_ciphertext_and_stores_name_only(test_org, client, fresh_bus):
    agent_id, daemon_id = await _make_agent_with_daemon(test_org)

    resp = await client.post(
        f"/agents/{agent_id}/env",
        json={"name": "OPENAI_API_KEY", "ciphertext": _CIPHERTEXT},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "OPENAI_API_KEY"
    assert body["origin"] == "ui"
    assert body["updated_by"] == test_org.user_id
    # Ciphertext/value must NOT appear in the response.
    assert _CIPHERTEXT not in resp.text

    # The command bus relays the ciphertext to the owning daemon.
    assert len(fresh_bus.sent) == 1
    cmd = fresh_bus.sent[0]
    assert cmd.command_type == "env.set"
    assert cmd.daemon_id == daemon_id
    assert cmd.payload["name"] == "OPENAI_API_KEY"
    assert cmd.payload["ciphertext"] == _CIPHERTEXT

    # The persisted row holds the NAME only — never value/ciphertext.
    db = await service_db()
    rows = (
        await db.table("env_var_refs")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("agent_id", agent_id)
        .eq("name", "OPENAI_API_KEY")
        .execute()
    ).data
    assert len(rows) == 1
    row = rows[0]
    assert row["origin"] == "ui"
    assert row["daemon_id"] == daemon_id
    # No column carries a value/ciphertext, and none of the stored values equal it.
    assert "ciphertext" not in row
    assert "value" not in row
    assert _CIPHERTEXT not in str(row)


async def test_set_409_when_no_daemon(test_org, client, fresh_bus):
    agent_id = await _make_agent_no_daemon(test_org)
    resp = await client.post(
        f"/agents/{agent_id}/env",
        json={"name": "FOO", "ciphertext": _CIPHERTEXT},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 409
    assert len(fresh_bus.sent) == 0


async def test_set_upsert_overwrites_same_name(test_org, client, fresh_bus):
    agent_id, _ = await _make_agent_with_daemon(test_org)
    for ct in ("Y2lwaGVyMQ==", "Y2lwaGVyMg=="):
        resp = await client.post(
            f"/agents/{agent_id}/env",
            json={"name": "TOKEN", "ciphertext": ct},
            headers=test_org.auth_headers(),
        )
        assert resp.status_code == 201, resp.text

    db = await service_db()
    rows = (
        await db.table("env_var_refs")
        .select("name")
        .eq("org_id", test_org.org_id)
        .eq("agent_id", agent_id)
        .eq("name", "TOKEN")
        .execute()
    ).data
    assert len(rows) == 1  # unique(agent_id, name)


async def test_set_requires_write(make_test_org, client, fresh_bus):
    viewer = await make_test_org(role="viewer")
    agent_id, _ = await _make_agent_with_daemon(viewer)
    resp = await client.post(
        f"/agents/{agent_id}/env",
        json={"name": "FOO", "ciphertext": _CIPHERTEXT},
        headers=viewer.auth_headers(),
    )
    assert resp.status_code == 403
    assert len(fresh_bus.sent) == 0


# ── list (metadata only) ───────────────────────────────────────────────────────
async def test_list_returns_metadata_only(test_org, client, fresh_bus):
    agent_id, _ = await _make_agent_with_daemon(test_org)
    await client.post(
        f"/agents/{agent_id}/env",
        json={"name": "DB_URL", "ciphertext": _CIPHERTEXT},
        headers=test_org.auth_headers(),
    )
    resp = await client.get(
        f"/agents/{agent_id}/env", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert any(i["name"] == "DB_URL" for i in items)
    ref = next(i for i in items if i["name"] == "DB_URL")
    assert set(ref.keys()) == {"name", "scope", "origin", "updated_by", "updated_at"}
    assert _CIPHERTEXT not in resp.text


# ── delete ──────────────────────────────────────────────────────────────────
async def test_delete_commands_and_removes_ref(test_org, client, fresh_bus):
    agent_id, daemon_id = await _make_agent_with_daemon(test_org)
    await client.post(
        f"/agents/{agent_id}/env",
        json={"name": "SECRET", "ciphertext": _CIPHERTEXT},
        headers=test_org.auth_headers(),
    )

    resp = await client.delete(
        f"/agents/{agent_id}/env/SECRET", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True

    delete_cmds = [c for c in fresh_bus.sent if c.command_type == "env.delete"]
    assert len(delete_cmds) == 1
    assert delete_cmds[0].daemon_id == daemon_id
    assert delete_cmds[0].payload == {"name": "SECRET"}

    db = await service_db()
    rows = (
        await db.table("env_var_refs")
        .select("id")
        .eq("org_id", test_org.org_id)
        .eq("agent_id", agent_id)
        .eq("name", "SECRET")
        .execute()
    ).data
    assert rows == []


async def test_delete_404_when_missing(test_org, client, fresh_bus):
    agent_id, _ = await _make_agent_with_daemon(test_org)
    resp = await client.delete(
        f"/agents/{agent_id}/env/NOPE", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


# ── inbound env.local handler ──────────────────────────────────────────────────
async def test_env_local_dispatch_creates_local_ref(test_org):
    agent_id, daemon_id = await _make_agent_with_daemon(test_org)

    n = await dispatch(
        ENV_VAR_LOCAL,
        MessageContext(
            daemon_id=daemon_id,
            org_id=test_org.org_id,
            run_id=None,
            agent_id=agent_id,
            seq=1,
        ),
        {"name": "LOCAL_VAR"},
    )
    assert n >= 1

    db = await service_db()
    rows = (
        await db.table("env_var_refs")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("agent_id", agent_id)
        .eq("name", "LOCAL_VAR")
        .execute()
    ).data
    assert len(rows) == 1
    assert rows[0]["origin"] == "local"
    assert rows[0]["daemon_id"] == daemon_id


# ── org scoping ─────────────────────────────────────────────────────────────
async def test_env_org_scoped(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent_id, _ = await _make_agent_with_daemon(org_a)
    await client.post(
        f"/agents/{agent_id}/env",
        json={"name": "A_ONLY", "ciphertext": _CIPHERTEXT},
        headers=org_a.auth_headers(),
    )
    # Org B cannot see org A's agent at all.
    resp = await client.get(
        f"/agents/{agent_id}/env", headers=org_b.auth_headers()
    )
    assert resp.status_code == 404
