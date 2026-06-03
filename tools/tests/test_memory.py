"""Tests for the agent-memory sync + editor unit (#13).

The cloud stores a redacted plaintext snapshot of agent memory (NOT E2E — the UI
reads/edits it). Covers: upsert -> list -> get round trip, version bump on
re-upsert, bytes accounting, the `memory.sync` command emitted on POST/DELETE
(asserted via the in-memory bus), the inbound `memory.delta` handler upserting
rows with updated_by='daemon', org-scoping isolation, and RBAC.
"""
from __future__ import annotations

import json

import pytest_asyncio

from synapse_cloud.command_bus import (
    InMemoryCommandBus,
    get_command_bus,
    set_command_bus,
)
from synapse_cloud.db import service_db
from synapse_cloud.message_registry import MEMORY_DELTA, MessageContext, dispatch
from synapse_cloud.services import memory_sync


@pytest_asyncio.fixture
def fresh_bus():
    prev = get_command_bus()
    bus = InMemoryCommandBus()
    set_command_bus(bus)
    yield bus
    set_command_bus(prev)


async def _make_agent_with_daemon(org) -> tuple[str, str]:
    """Create a daemon + an agent owned by it."""
    daemon_id, _ = await org.make_daemon()
    db = await service_db()
    agent = (
        await db.table("agents")
        .insert(
            {
                "org_id": org.org_id,
                "daemon_id": daemon_id,
                "name": "mem-agent",
                "type": "api",
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
                "name": "lonely-mem-agent",
                "type": "api",
                "status": "active",
            }
        )
        .execute()
    ).data[0]
    return agent["id"]


# ── pure helper: bytes accounting ───────────────────────────────────────────────
def test_compute_bytes():
    value = {"a": 1}
    text = "hello"
    expected = len(json.dumps(value)) + len(text)
    assert memory_sync.compute_bytes(value, text) == expected
    # None value -> "null" (4 bytes); None text -> 0
    assert memory_sync.compute_bytes(None, None) == len("null")


# ── upsert -> list -> get round trip ───────────────────────────────────────────
async def test_upsert_list_get_roundtrip(test_org, client, fresh_bus):
    agent_id, _ = await _make_agent_with_daemon(test_org)

    resp = await client.post(
        f"/agents/{agent_id}/memory",
        json={
            "namespace": "facts",
            "key": "fav_color",
            "value": {"color": "blue"},
            "text": "user likes blue",
            "tags": ["pref"],
        },
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["namespace"] == "facts"
    assert created["key"] == "fav_color"
    assert created["updated_by"] == "ui"
    assert created["version"] == 1
    assert created["value_redacted"] == {"color": "blue"}
    assert created["text_redacted"] == "user likes blue"
    expected_bytes = len(json.dumps({"color": "blue"})) + len("user likes blue")
    assert created["bytes"] == expected_bytes
    entry_id = created["id"]

    # list
    resp = await client.get(
        f"/agents/{agent_id}/memory", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert any(i["id"] == entry_id for i in items)

    # get single
    resp = await client.get(
        f"/agents/{agent_id}/memory/{entry_id}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == entry_id


async def test_get_missing_entry_404(test_org, client, fresh_bus):
    import uuid

    agent_id, _ = await _make_agent_with_daemon(test_org)
    resp = await client.get(
        f"/agents/{agent_id}/memory/{uuid.uuid4()}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


# ── version bump on re-upsert ───────────────────────────────────────────────────
async def test_version_bumps_on_reupsert(test_org, client, fresh_bus):
    agent_id, _ = await _make_agent_with_daemon(test_org)
    body = {"namespace": "facts", "key": "k1", "text": "v1"}

    r1 = await client.post(
        f"/agents/{agent_id}/memory", json=body, headers=test_org.auth_headers()
    )
    assert r1.json()["version"] == 1

    body2 = {"namespace": "facts", "key": "k1", "text": "v2"}
    r2 = await client.post(
        f"/agents/{agent_id}/memory", json=body2, headers=test_org.auth_headers()
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["version"] == 2
    assert r2.json()["text_redacted"] == "v2"

    # Only one row exists (unique on agent_id, namespace, key).
    db = await service_db()
    rows = (
        await db.table("agent_memory")
        .select("id")
        .eq("org_id", test_org.org_id)
        .eq("agent_id", agent_id)
        .eq("namespace", "facts")
        .eq("key", "k1")
        .execute()
    ).data
    assert len(rows) == 1


# ── list filters ────────────────────────────────────────────────────────────────
async def test_list_namespace_and_tag_filters(test_org, client, fresh_bus):
    agent_id, _ = await _make_agent_with_daemon(test_org)
    await client.post(
        f"/agents/{agent_id}/memory",
        json={"namespace": "ns1", "key": "a", "text": "x", "tags": ["red"]},
        headers=test_org.auth_headers(),
    )
    await client.post(
        f"/agents/{agent_id}/memory",
        json={"namespace": "ns2", "key": "b", "text": "y", "tags": ["blue"]},
        headers=test_org.auth_headers(),
    )

    resp = await client.get(
        f"/agents/{agent_id}/memory?namespace=ns1", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    items = resp.json()
    assert {i["namespace"] for i in items} == {"ns1"}

    resp = await client.get(
        f"/agents/{agent_id}/memory?tag=blue", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    items = resp.json()
    assert all("blue" in i["tags"] for i in items)
    assert any(i["key"] == "b" for i in items)


# ── memory.sync command on POST ─────────────────────────────────────────────────
async def test_upsert_emits_sync_command(test_org, client, fresh_bus):
    agent_id, daemon_id = await _make_agent_with_daemon(test_org)
    resp = await client.post(
        f"/agents/{agent_id}/memory",
        json={"namespace": "facts", "key": "k", "value": {"n": 1}, "text": "t"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text

    sync = [c for c in fresh_bus.sent if c.command_type == "memory.sync"]
    assert len(sync) == 1
    cmd = sync[0]
    assert cmd.daemon_id == daemon_id
    assert cmd.payload["op"] == "upsert"
    assert cmd.payload["namespace"] == "facts"
    assert cmd.payload["key"] == "k"
    assert cmd.payload["value"] == {"n": 1}
    assert cmd.payload["version"] == 1


async def test_upsert_no_daemon_skips_command(test_org, client, fresh_bus):
    agent_id = await _make_agent_no_daemon(test_org)
    resp = await client.post(
        f"/agents/{agent_id}/memory",
        json={"namespace": "facts", "key": "k", "text": "t"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    assert [c for c in fresh_bus.sent if c.command_type == "memory.sync"] == []


# ── memory.sync command on DELETE ───────────────────────────────────────────────
async def test_delete_removes_row_and_emits_sync(test_org, client, fresh_bus):
    agent_id, daemon_id = await _make_agent_with_daemon(test_org)
    created = (
        await client.post(
            f"/agents/{agent_id}/memory",
            json={"namespace": "facts", "key": "gone", "text": "t"},
            headers=test_org.auth_headers(),
        )
    ).json()
    entry_id = created["id"]

    resp = await client.delete(
        f"/agents/{agent_id}/memory/{entry_id}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True

    deletes = [
        c
        for c in fresh_bus.sent
        if c.command_type == "memory.sync" and c.payload.get("op") == "delete"
    ]
    assert len(deletes) == 1
    assert deletes[0].daemon_id == daemon_id
    assert deletes[0].payload["namespace"] == "facts"
    assert deletes[0].payload["key"] == "gone"

    db = await service_db()
    rows = (
        await db.table("agent_memory")
        .select("id")
        .eq("org_id", test_org.org_id)
        .eq("id", entry_id)
        .execute()
    ).data
    assert rows == []


async def test_delete_404_when_missing(test_org, client, fresh_bus):
    import uuid

    agent_id, _ = await _make_agent_with_daemon(test_org)
    resp = await client.delete(
        f"/agents/{agent_id}/memory/{uuid.uuid4()}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 404


# ── inbound memory.delta dispatch ───────────────────────────────────────────────
async def test_memory_delta_upserts_with_daemon_origin(test_org):
    agent_id, daemon_id = await _make_agent_with_daemon(test_org)

    n = await dispatch(
        MEMORY_DELTA,
        MessageContext(
            daemon_id=daemon_id,
            org_id=test_org.org_id,
            run_id=None,
            agent_id=agent_id,
            seq=1,
        ),
        {
            "entries": [
                {
                    "namespace": "facts",
                    "key": "from_daemon",
                    "value": {"v": 2},
                    "text": "redacted text",
                    "tags": ["t1"],
                }
            ],
            "deletes": [],
        },
    )
    assert n >= 1

    db = await service_db()
    rows = (
        await db.table("agent_memory")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("agent_id", agent_id)
        .eq("namespace", "facts")
        .eq("key", "from_daemon")
        .execute()
    ).data
    assert len(rows) == 1
    row = rows[0]
    assert row["updated_by"] == "daemon"
    assert row["value_redacted"] == {"v": 2}
    assert row["text_redacted"] == "redacted text"
    assert row["version"] == 1


async def test_memory_delta_delete(test_org):
    agent_id, daemon_id = await _make_agent_with_daemon(test_org)
    db = await service_db()
    # Seed an entry directly via the helper.
    await memory_sync.upsert_entry(
        db,
        org_id=test_org.org_id,
        agent_id=agent_id,
        namespace="facts",
        key="to_delete",
        text="bye",
        updated_by="daemon",
    )

    await dispatch(
        MEMORY_DELTA,
        MessageContext(
            daemon_id=daemon_id,
            org_id=test_org.org_id,
            agent_id=agent_id,
            seq=2,
        ),
        {"entries": [], "deletes": [{"namespace": "facts", "key": "to_delete"}]},
    )

    rows = (
        await db.table("agent_memory")
        .select("id")
        .eq("org_id", test_org.org_id)
        .eq("agent_id", agent_id)
        .eq("namespace", "facts")
        .eq("key", "to_delete")
        .execute()
    ).data
    assert rows == []


# ── org scoping ─────────────────────────────────────────────────────────────────
async def test_memory_org_scoped(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent_id, _ = await _make_agent_with_daemon(org_a)
    await client.post(
        f"/agents/{agent_id}/memory",
        json={"namespace": "facts", "key": "a_only", "text": "secret"},
        headers=org_a.auth_headers(),
    )

    # Org B cannot see org A's agent at all.
    resp = await client.get(
        f"/agents/{agent_id}/memory", headers=org_b.auth_headers()
    )
    assert resp.status_code == 404

    # Nor edit it.
    resp = await client.post(
        f"/agents/{agent_id}/memory",
        json={"namespace": "facts", "key": "intrude", "text": "x"},
        headers=org_b.auth_headers(),
    )
    assert resp.status_code == 404


# ── RBAC ──────────────────────────────────────────────────────────────────────
async def test_viewer_cannot_write(make_test_org, client, fresh_bus):
    viewer = await make_test_org(role="viewer")
    agent_id, _ = await _make_agent_with_daemon(viewer)
    resp = await client.post(
        f"/agents/{agent_id}/memory",
        json={"namespace": "facts", "key": "k", "text": "x"},
        headers=viewer.auth_headers(),
    )
    assert resp.status_code == 403
    assert [c for c in fresh_bus.sent if c.command_type == "memory.sync"] == []
