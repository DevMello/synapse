"""Tests for webhooks (management + public HMAC ingress) and gateways CRUD."""
from __future__ import annotations

import json

import pytest_asyncio

from synapse_cloud.command_bus import (
    InMemoryCommandBus,
    get_command_bus,
    set_command_bus,
)
from synapse_cloud.db import service_db
from synapse_cloud.security import hash_token
from synapse_cloud.workers.webhooks import (
    apply_payload_template,
    compute_signature,
    parse_signature_header,
)


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
    row: dict = {"org_id": org_id, "name": "hook-agent", "type": "cli"}
    if daemon_id is not None:
        row["daemon_id"] = daemon_id
    inserted = (await db.table("agents").insert(row).execute()).data[0]
    return inserted["id"]


def _sign_header(secret: str, raw_body: bytes) -> str:
    # Contract: signing key is hash_token(secret) == stored secret_hash.
    return "sha256=" + compute_signature(hash_token(secret), raw_body)


# ── helper unit tests ─────────────────────────────────────────────────────────
def test_parse_signature_header():
    assert parse_signature_header("sha256=abc") == "abc"
    assert parse_signature_header(" sha256=deadbeef ") == "deadbeef"
    assert parse_signature_header(None) is None
    assert parse_signature_header("md5=abc") is None
    assert parse_signature_header("sha256=") is None


def test_apply_payload_template_passthrough():
    assert apply_payload_template(None, {"a": 1}) == {"a": 1}
    assert apply_payload_template({}, {"a": 1}) == {"a": 1}
    assert apply_payload_template(None, "x") == {"body": "x"}


def test_apply_payload_template_mapping():
    body = {"ref": "main", "commit": "abc"}
    tmpl = {"branch": "ref", "literal": "constant"}
    out = apply_payload_template(tmpl, body)
    assert out["branch"] == "main"  # mapped from body["ref"]
    assert out["literal"] == "constant"  # literal default
    assert out["ref"] == "main"  # body preserved


# ── webhook management ─────────────────────────────────────────────────────────
async def test_create_webhook_returns_secret_once(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    resp = await client.post(
        f"/agents/{agent_id}/webhooks",
        json={"payload_template": {"branch": "ref"}},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    wh = resp.json()
    assert wh["token"]
    assert wh["secret"]  # returned once
    assert "secret_hash" not in wh  # never leaked

    # The secret is not returned on subsequent list calls.
    lst = await client.get(
        f"/agents/{agent_id}/webhooks", headers=test_org.auth_headers()
    )
    assert lst.status_code == 200
    rows = lst.json()
    assert len(rows) == 1
    assert "secret" not in rows[0]
    assert "secret_hash" not in rows[0]


async def test_patch_and_delete_webhook(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    wh = (
        await client.post(
            f"/agents/{agent_id}/webhooks", json={}, headers=test_org.auth_headers()
        )
    ).json()

    patched = await client.patch(
        f"/webhooks/{wh['id']}",
        json={"enabled": False},
        headers=test_org.auth_headers(),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["enabled"] is False

    deleted = await client.delete(
        f"/webhooks/{wh['id']}", headers=test_org.auth_headers()
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


async def test_create_webhook_agent_not_found(test_org, client, fresh_bus):
    resp = await client.post(
        "/agents/00000000-0000-0000-0000-000000000000/webhooks",
        json={},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 404


async def test_webhook_org_isolation(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent_id = await _make_agent(org_a.org_id)
    wh = (
        await client.post(
            f"/agents/{agent_id}/webhooks", json={}, headers=org_a.auth_headers()
        )
    ).json()
    # org_b cannot delete org_a's webhook.
    resp = await client.delete(f"/webhooks/{wh['id']}", headers=org_b.auth_headers())
    assert resp.status_code == 404


# ── public ingress ─────────────────────────────────────────────────────────────
async def test_ingress_valid_signature_creates_run_and_dispatches(
    test_org, client, fresh_bus
):
    daemon_id, _ = await test_org.make_daemon()
    agent_id = await _make_agent(test_org.org_id, daemon_id=daemon_id)
    wh = (
        await client.post(
            f"/agents/{agent_id}/webhooks",
            json={"payload_template": {"branch": "ref"}},
            headers=test_org.auth_headers(),
        )
    ).json()

    body = {"ref": "main", "sha": "deadbeef"}
    raw = json.dumps(body).encode("utf-8")
    resp = await client.post(
        f"/hooks/{wh['token']}",
        content=raw,
        headers={
            "X-Synapse-Signature": _sign_header(wh["secret"], raw),
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    assert run_id

    # A runs row with trigger='webhook' exists.
    db = await service_db()
    run = (
        await db.table("runs").select("*").eq("id", run_id).execute()
    ).data[0]
    assert run["trigger"] == "webhook"
    assert run["status"] == "pending"
    assert run["org_id"] == test_org.org_id
    assert run["agent_id"] == agent_id

    # agent.run dispatched to the owning daemon with the mapped payload.
    runs = [s for s in fresh_bus.sent if s.command_type == "agent.run"]
    assert len(runs) == 1
    assert runs[0].daemon_id == daemon_id
    assert runs[0].payload["run_id"] == run_id
    assert runs[0].payload["trigger"] == "webhook"
    assert runs[0].payload["input"]["branch"] == "main"


async def test_ingress_bad_signature_401(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    wh = (
        await client.post(
            f"/agents/{agent_id}/webhooks", json={}, headers=test_org.auth_headers()
        )
    ).json()

    raw = json.dumps({"x": 1}).encode("utf-8")
    resp = await client.post(
        f"/hooks/{wh['token']}",
        content=raw,
        headers={"X-Synapse-Signature": "sha256=" + "00" * 32},
    )
    assert resp.status_code == 401
    assert not fresh_bus.sent


async def test_ingress_missing_signature_401(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    wh = (
        await client.post(
            f"/agents/{agent_id}/webhooks", json={}, headers=test_org.auth_headers()
        )
    ).json()
    raw = b"{}"
    resp = await client.post(f"/hooks/{wh['token']}", content=raw)
    assert resp.status_code == 401


async def test_ingress_unknown_token_404(client, fresh_bus):
    resp = await client.post("/hooks/does-not-exist", content=b"{}")
    assert resp.status_code == 404


async def test_ingress_disabled_webhook_404(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)
    wh = (
        await client.post(
            f"/agents/{agent_id}/webhooks", json={}, headers=test_org.auth_headers()
        )
    ).json()
    await client.patch(
        f"/webhooks/{wh['id']}",
        json={"enabled": False},
        headers=test_org.auth_headers(),
    )

    raw = b"{}"
    resp = await client.post(
        f"/hooks/{wh['token']}",
        content=raw,
        headers={"X-Synapse-Signature": _sign_header(wh["secret"], raw)},
    )
    assert resp.status_code == 404


async def test_ingress_no_daemon_skips_dispatch(test_org, client, fresh_bus):
    agent_id = await _make_agent(test_org.org_id)  # no daemon_id
    wh = (
        await client.post(
            f"/agents/{agent_id}/webhooks", json={}, headers=test_org.auth_headers()
        )
    ).json()

    raw = b"{}"
    resp = await client.post(
        f"/hooks/{wh['token']}",
        content=raw,
        headers={"X-Synapse-Signature": _sign_header(wh["secret"], raw)},
    )
    assert resp.status_code == 200, resp.text
    # Run created but nothing dispatched (no owning daemon).
    assert not [s for s in fresh_bus.sent if s.command_type == "agent.run"]


# ── gateways CRUD ──────────────────────────────────────────────────────────────
async def test_gateway_crud(test_org, client, fresh_bus):
    headers = test_org.auth_headers()
    created = await client.post(
        "/gateways",
        json={"name": "gh", "kind": "http", "config": {"path": "/x"}},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    gw = created.json()
    assert gw["kind"] == "http"
    assert gw["config"] == {"path": "/x"}

    listed = await client.get("/gateways", headers=headers)
    assert listed.status_code == 200
    assert gw["id"] in [g["id"] for g in listed.json()]

    one = await client.get(f"/gateways/{gw['id']}", headers=headers)
    assert one.status_code == 200
    assert one.json()["id"] == gw["id"]

    patched = await client.patch(
        f"/gateways/{gw['id']}",
        json={"name": "gh2", "config": {"path": "/y"}},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "gh2"
    assert patched.json()["config"] == {"path": "/y"}

    deleted = await client.delete(f"/gateways/{gw['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


async def test_gateway_invalid_kind_422(test_org, client, fresh_bus):
    resp = await client.post(
        "/gateways",
        json={"name": "bad", "kind": "smtp"},
        headers=test_org.auth_headers(),
    )
    assert resp.status_code == 422


async def test_gateway_org_isolation(make_test_org, client, fresh_bus):
    org_a = await make_test_org()
    org_b = await make_test_org()
    gw = (
        await client.post(
            "/gateways",
            json={"name": "a", "kind": "api"},
            headers=org_a.auth_headers(),
        )
    ).json()
    # org_b cannot see org_a's gateway.
    resp = await client.get(f"/gateways/{gw['id']}", headers=org_b.auth_headers())
    assert resp.status_code == 404
