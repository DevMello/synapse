"""Tests for the hash-chained audit log + SIEM export (Unit 16).

Because test mode swaps in the in-memory ``FakeAuditWriter``, the real
hash-chaining behaviour is exercised by instantiating ``SupabaseAuditWriter``
directly and writing against the real ``audit_events`` table under a fresh
isolated org. The query/export endpoints are driven through the ASGI client
after seeding rows with the real writer.
"""
from __future__ import annotations

import pytest_asyncio

from synapse_cloud.audit import (
    FakeAuditWriter,
    SupabaseAuditWriter,
    chain_hash,
    get_audit,
    hash_payload,
    set_audit,
)
from synapse_cloud.db import service_db


@pytest_asyncio.fixture
def real_writer():
    """Force the real DB-backed writer for a test, restoring the prior one after."""
    prev = get_audit()
    writer = SupabaseAuditWriter()
    set_audit(writer)
    yield writer
    set_audit(prev)


async def _rows_for(org_id: str) -> list[dict]:
    db = await service_db()
    return (
        await db.table("audit_events")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at")
        .order("id")
        .execute()
    ).data or []


# ── public surface (backward-compat) ──────────────────────────────────────────
def test_test_mode_uses_fake_writer():
    """Under SYNAPSE_ENV=test the default writer must remain the FakeAuditWriter."""
    set_audit(None)  # reset cache so the factory re-selects
    import synapse_cloud.audit as audit_mod

    audit_mod._writer = None
    w = get_audit()
    assert isinstance(w, FakeAuditWriter)
    assert hasattr(w, "events")


async def test_fake_writer_records_events():
    w = FakeAuditWriter()
    await w.write(
        "org-1",
        "thing.did",
        actor="user:1",
        resource_type="thing",
        resource_id="t1",
        detail={"k": "v"},
    )
    assert len(w.events) == 1
    ev = w.events[0]
    assert ev["org_id"] == "org-1"
    assert ev["action"] == "thing.did"
    assert ev["actor"] == "user:1"
    assert ev["resource_type"] == "thing"
    assert ev["resource_id"] == "t1"
    assert ev["detail"] == {"k": "v"}


# ── hash helpers ──────────────────────────────────────────────────────────────
def test_chain_hash_deterministic_and_links_prev():
    payload = hash_payload(
        action="a",
        actor="u",
        resource_type="rt",
        resource_id="ri",
        run_id=None,
        detail={"x": 1},
        created_at="2026-06-01T00:00:00+00:00",
    )
    h1 = chain_hash(None, payload)
    h1b = chain_hash(None, payload)
    assert h1 == h1b  # deterministic
    assert len(h1) == 64  # sha256 hex
    # Different prev_hash -> different chained hash.
    assert chain_hash("deadbeef", payload) != h1


# ── real DB-backed chain ──────────────────────────────────────────────────────
async def test_real_writer_chains_rows(test_org, real_writer):
    actions = ["run.created", "run.started", "run.finished"]
    for a in actions:
        await real_writer.write(
            test_org.org_id,
            a,
            actor=test_org.user_id,
            resource_type="run",
            resource_id="r-1",
            detail={"action": a},
        )

    rows = await _rows_for(test_org.org_id)
    assert [r["action"] for r in rows] == actions

    # Genesis row has no prev_hash.
    assert rows[0]["prev_hash"] is None
    assert rows[0]["hash"]

    # Each subsequent prev_hash links to the previous row's hash.
    for prev, cur in zip(rows, rows[1:]):
        assert cur["prev_hash"] == prev["hash"]

    # Each stored hash recomputes from the canonical payload + prev_hash.
    for r in rows:
        payload = hash_payload(
            action=r["action"],
            actor=r["actor"],
            resource_type=r["resource_type"],
            resource_id=r["resource_id"],
            run_id=r["run_id"],
            detail=r["detail"] or {},
            created_at=r["created_at"],
        )
        assert chain_hash(r["prev_hash"], payload) == r["hash"]


async def test_chain_is_per_org(make_test_org, real_writer):
    org_a = await make_test_org()
    org_b = await make_test_org()
    await real_writer.write(org_a.org_id, "a.1", actor="x")
    await real_writer.write(org_b.org_id, "b.1", actor="y")
    await real_writer.write(org_a.org_id, "a.2", actor="x")

    rows_a = await _rows_for(org_a.org_id)
    rows_b = await _rows_for(org_b.org_id)
    assert len(rows_a) == 2
    assert len(rows_b) == 1
    # B's single row is genesis (its own chain), not linked to A.
    assert rows_b[0]["prev_hash"] is None
    # A's second row links to A's first, not to B.
    assert rows_a[1]["prev_hash"] == rows_a[0]["hash"]


# ── query endpoint ────────────────────────────────────────────────────────────
async def test_list_audit_events(test_org, client, real_writer):
    await real_writer.write(test_org.org_id, "alpha.do", actor="u1", resource_type="alpha")
    await real_writer.write(test_org.org_id, "beta.do", actor="u2", resource_type="beta")

    resp = await client.get("/audit", headers=test_org.auth_headers())
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 2
    # created_at desc -> most recent (beta) first.
    assert items[0]["action"] == "beta.do"
    assert items[1]["action"] == "alpha.do"


async def test_list_audit_filters(test_org, client, real_writer):
    await real_writer.write(test_org.org_id, "alpha.do", actor="u1", resource_type="alpha")
    await real_writer.write(test_org.org_id, "beta.do", actor="u2", resource_type="beta")

    resp = await client.get(
        "/audit", params={"action": "alpha.do"}, headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["action"] == "alpha.do"

    resp = await client.get(
        "/audit", params={"actor": "u2"}, headers=test_org.auth_headers()
    )
    assert [i["action"] for i in resp.json()] == ["beta.do"]

    resp = await client.get(
        "/audit", params={"resource_type": "beta"}, headers=test_org.auth_headers()
    )
    assert [i["action"] for i in resp.json()] == ["beta.do"]


async def test_list_audit_pagination(test_org, client, real_writer):
    for i in range(5):
        await real_writer.write(test_org.org_id, f"evt.{i}", actor="u")
    resp = await client.get(
        "/audit", params={"limit": 2, "offset": 0}, headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── export ────────────────────────────────────────────────────────────────────
async def test_export_json(test_org, client, real_writer):
    await real_writer.write(
        test_org.org_id, "exp.json", actor="u", resource_type="thing", resource_id="t1"
    )
    resp = await client.get(
        "/audit/export", params={"format": "json"}, headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert any(e["action"] == "exp.json" for e in data)


async def test_export_cef(test_org, client, real_writer):
    await real_writer.write(
        test_org.org_id,
        "exp.cef",
        actor="user:42",
        resource_type="run",
        resource_id="run-7",
    )
    resp = await client.get(
        "/audit/export", params={"format": "cef"}, headers=test_org.auth_headers()
    )
    assert resp.status_code == 200, resp.text
    assert "text/plain" in resp.headers["content-type"]
    lines = [ln for ln in resp.text.splitlines() if ln]
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith("CEF:0|Synapse|CloudBackend|1.0|exp.cef|exp.cef|0|")
    assert "suser=user:42" in line
    assert "cs1=run" in line
    assert "cs2=run-7" in line


# ── verify ────────────────────────────────────────────────────────────────────
async def test_verify_intact_chain(test_org, client, real_writer):
    for i in range(3):
        await real_writer.write(test_org.org_id, f"v.{i}", actor="u")
    resp = await client.get("/audit/verify", headers=test_org.auth_headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["count"] == 3
    assert body["broken_at"] is None


# ── org scoping + RBAC ────────────────────────────────────────────────────────
async def test_audit_org_scoped(make_test_org, client, real_writer):
    org_a = await make_test_org()
    org_b = await make_test_org()
    await real_writer.write(org_a.org_id, "a.secret", actor="u")

    resp = await client.get("/audit", headers=org_b.auth_headers())
    assert resp.status_code == 200
    assert all(e["action"] != "a.secret" for e in resp.json())

    resp = await client.get("/audit", headers=org_a.auth_headers())
    assert any(e["action"] == "a.secret" for e in resp.json())


async def test_audit_requires_admin(make_test_org, client, real_writer):
    viewer = await make_test_org(role="viewer")
    await real_writer.write(viewer.org_id, "v.evt", actor="u")
    for path in ("/audit", "/audit/export", "/audit/verify"):
        resp = await client.get(path, headers=viewer.auth_headers())
        assert resp.status_code == 403, f"{path}: {resp.status_code}"
