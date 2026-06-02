"""Unit 14 — Agent memory interface + storage providers (§4.13).

Self-contained: no network, no Docker, no vector extra. Uses the conftest ``store`` /
``uplink`` / ``settings`` fixtures. Covers the sqlite provider round-trip, redaction on
write, the ``memory.delta`` sync path, the ``memory.sync`` command (incl. the no-loop
guarantee), the vector→sqlite fallback, and the ``memory`` MCP server tool surface.
"""
from __future__ import annotations

import pytest

from synapse_worker.capabilities.registry import DEFAULT_CAPABILITIES
from synapse_worker.filtering import base as _filtering
from synapse_worker.filtering.redaction import RedactionFilter
from synapse_worker.memory.api import MemoryAPI, flush_deltas, get_memory, reset_memory
from synapse_worker.memory.mcp_server import build_memory_mcp_server
from synapse_worker.memory.providers import (
    SQLITE_MEMORY,
    SqliteMemoryProvider,
    get_provider,
)
from synapse_worker.router import CommandContext

pytestmark = pytest.mark.asyncio

AGENT = "agt_test"
SECRET = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


@pytest.fixture(autouse=True)
def _reset_memory_singleton():
    reset_memory()
    yield
    reset_memory()


# ── SqliteMemoryProvider round-trip ──────────────────────────────────────────
async def test_sqlite_store_get_list_delete_roundtrip(store):
    p = SqliteMemoryProvider()
    e = await p.store(AGENT, "k1", "hello world", tags=["a", "b"])
    assert e.version == 1 and e.tags == ["a", "b"]

    got = await p.get(AGENT, "k1")
    assert got is not None and got.value == "hello world" and got.tags == ["a", "b"]

    listed = await p.list(AGENT)
    assert [x.key for x in listed] == ["k1"]

    assert await p.delete(AGENT, "k1") is True
    assert await p.get(AGENT, "k1") is None
    assert await p.delete(AGENT, "k1") is False  # already gone


async def test_sqlite_substring_query(store):
    p = SqliteMemoryProvider()
    await p.store(AGENT, "fruit", "the apple is red")
    await p.store(AGENT, "veg", "the carrot is orange")
    hits = await p.query(AGENT, "apple")
    assert [h.key for h in hits] == ["fruit"]
    # tag substring also matches
    await p.store(AGENT, "tagged", "value", tags=["important"])
    assert [h.key for h in await p.query(AGENT, "important")] == ["tagged"]


async def test_namespaces_isolate(store):
    p = SqliteMemoryProvider()
    await p.store(AGENT, "k", "in-default", namespace="default")
    await p.store(AGENT, "k", "in-other", namespace="ns2")
    assert (await p.get(AGENT, "k", namespace="default")).value == "in-default"
    assert (await p.get(AGENT, "k", namespace="ns2")).value == "in-other"
    assert [x.key for x in await p.list(AGENT, namespace="ns2")] == ["k"]
    assert len(await p.list(AGENT, namespace="default")) == 1


async def test_versioning_increments_on_restore(store):
    p = SqliteMemoryProvider()
    await p.store(AGENT, "k", "v1")
    e2 = await p.store(AGENT, "k", "v2")
    assert e2.version == 2
    assert (await p.get(AGENT, "k")).value == "v2"


# ── redaction on write ───────────────────────────────────────────────────────
async def test_store_redacts_secret_in_db_and_delta(store, uplink):
    # Register Unit 6's redaction filter on a fresh chain.
    _filtering.reset_filter_chain()
    _filtering.get_filter_chain().register(RedactionFilter())

    api = get_memory()
    entry = await api.store(AGENT, "creds", f"my key is {SECRET}")
    assert SECRET not in entry.value
    assert "<REDACTED:" in entry.value

    # Raw secret absent from the DB.
    row = await store.fetchone(
        "SELECT value FROM memory WHERE agent_id=? AND key=?", (AGENT, "creds")
    )
    assert SECRET not in row["value"]

    # Raw secret absent from the journal row.
    jrow = await store.fetchone(
        "SELECT value FROM memory_journal WHERE agent_id=? AND key=?", (AGENT, "creds")
    )
    assert SECRET not in (jrow["value"] or "")

    # And absent from the emitted memory.delta.
    await flush_deltas(AGENT)
    deltas = uplink.of_type("memory.delta")
    assert len(deltas) == 1
    blob = str(deltas[0].payload)
    assert SECRET not in blob


# ── memory.delta sync ────────────────────────────────────────────────────────
async def test_flush_deltas_emits_then_noop(store, uplink):
    api = get_memory()
    await api.store(AGENT, "a", "alpha", tags=["t"])
    await api.store(AGENT, "b", "beta")
    await api.delete(AGENT, "a")

    n = await flush_deltas(AGENT)
    assert n == 3  # 2 stores + 1 delete journalled

    frames = uplink.of_type("memory.delta")
    assert len(frames) == 1
    frame = frames[0]
    assert frame.channel == "telemetry"
    payload = frame.payload
    assert payload["agent_id"] == AGENT
    keys = {e["key"] for e in payload["entries"]}
    assert keys == {"a", "b"}  # journal carries both store ops
    assert {d["key"] for d in payload["deletes"]} == {"a"}

    # Second flush emits nothing new (rows marked synced).
    assert await flush_deltas(AGENT) == 0
    assert len(uplink.of_type("memory.delta")) == 1


async def test_flush_empty_sends_no_frame(store, uplink):
    assert await flush_deltas(AGENT) == 0
    assert uplink.of_type("memory.delta") == []


# ── memory.sync command ──────────────────────────────────────────────────────
async def test_memory_sync_upsert_and_delete(store, uplink):
    from synapse_worker.commands.memory import handle_memory_sync

    ctx = CommandContext(
        command_type="memory.sync",
        idempotency_key=f"memory.sync:upsert:{AGENT}:default:pref",
    )
    await handle_memory_sync(ctx, {"op": "upsert", "key": "pref", "value": "dark"})

    api = get_memory()
    got = await api.get(AGENT, "pref")
    assert got is not None and got.value == "dark"

    # A cloud-originated sync must NOT produce a memory.delta (no loop).
    assert await flush_deltas(AGENT) == 0
    assert uplink.of_type("memory.delta") == []

    # delete via command
    ctx2 = CommandContext(
        command_type="memory.sync",
        idempotency_key=f"memory.sync:delete:{AGENT}:default:pref",
    )
    await handle_memory_sync(ctx2, {"op": "delete", "key": "pref"})
    assert await api.get(AGENT, "pref") is None
    assert await flush_deltas(AGENT) == 0  # still no loop


async def test_memory_sync_agent_id_from_payload(store):
    from synapse_worker.commands.memory import handle_memory_sync

    ctx = CommandContext(command_type="memory.sync")  # no idempotency key
    await handle_memory_sync(
        ctx,
        {"op": "upsert", "agent_id": AGENT, "namespace": "ns", "key": "x", "value": "y"},
    )
    assert (await get_memory().get(AGENT, "x", namespace="ns")).value == "y"


# ── vector fallback ──────────────────────────────────────────────────────────
async def test_vector_falls_back_to_sqlite_without_docker(store, monkeypatch):
    import synapse_worker.memory.providers as providers

    # Force the configured provider to vector and make Docker absent.
    monkeypatch.setattr(providers, "_configured_provider_name", lambda agent_id=None: providers.VECTOR_MEMORY)
    monkeypatch.setattr(providers.shutil, "which", lambda _: None)

    p = get_provider(AGENT)
    assert isinstance(p, SqliteMemoryProvider)
    assert p.name == SQLITE_MEMORY
    # Memory still works on the fallback provider.
    await p.store(AGENT, "k", "v")
    assert (await p.get(AGENT, "k")).value == "v"


# ── MCP server ───────────────────────────────────────────────────────────────
async def test_memory_is_default_capability(store):
    assert "memory" in DEFAULT_CAPABILITIES


async def test_mcp_server_exposes_five_tools_and_routes(store):
    api = MemoryAPI(provider=SqliteMemoryProvider())
    server = build_memory_mcp_server(default_agent_id=AGENT, api=api)

    names = set(server.tool_names())
    assert names == {
        "memory.store",
        "memory.query",
        "memory.get",
        "memory.list",
        "memory.delete",
    }
    assert len(server.tools()) == 5

    # store routes to the API → readable via get
    await server.call("memory.store", {"key": "k", "value": "hello", "tags": ["x"]})
    got = await server.call("memory.get", {"key": "k"})
    assert got["value"] == "hello" and got["tags"] == ["x"]

    # query routes through substring search
    hits = await server.call("memory.query", {"search_term": "hello"})
    assert [h["key"] for h in hits] == ["k"]

    listed = await server.call("memory.list", {})
    assert [x["key"] for x in listed] == ["k"]

    res = await server.call("memory.delete", {"key": "k"})
    assert res["deleted"] is True
    assert await server.call("memory.get", {"key": "k"}) is None


async def test_mcp_unknown_tool_raises(store):
    server = build_memory_mcp_server(default_agent_id=AGENT)
    with pytest.raises(KeyError):
        await server.call("memory.nope", {})
