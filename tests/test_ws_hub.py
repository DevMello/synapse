"""Unit/integration tests for the WebSocket daemon hub (unit 2).

We drive the hub against a live in-process uvicorn server inside the test's own
event loop, using the ``websockets`` client lib. This keeps everything on ONE
event loop, so the async conftest fixtures (real Supabase org/daemon) and the
cloud-side ``get_command_bus().send(...)`` calls share the same loop as the hub's
ConnectionRegistry — unlike Starlette's threaded TestClient, which runs the app on
a separate loop and can't be driven cross-loop.

Covers:
  * handshake auth failure (no token / bad token) -> socket closed with 4401
  * connect via query-param token and via Authorization header
  * presence row upsert + daemon marked online on connect
  * command delivery: a CloudMessage frame arrives over the socket
  * ack handling clears the pending-redelivery buffer
  * offline command is queued and redelivered on reconnect
  * inbound frame reaches a registered @on_daemon_message handler
  * close_stream tears the socket down

These talk to the REAL Supabase project; they skip when creds are absent.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest
import pytest_asyncio
import uvicorn
import websockets
from websockets.exceptions import ConnectionClosed

from synapse_cloud import message_registry, ws_hub
from synapse_cloud.command_bus import get_command_bus
from synapse_cloud.config import get_settings
from synapse_cloud.db import service_db
from synapse_cloud.security import encode_daemon_access_token
from synapse_cloud.ws_hub.auth import WS_UNAUTHORIZED

_PORT = 8123
_WS = f"ws://127.0.0.1:{_PORT}"


def _require_supabase() -> None:
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_role_key):
        pytest.skip("real Supabase creds required (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)")


pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def server():
    """Boot the real app under uvicorn ONCE for the module, in the module's loop.

    Booting per-test on the Windows ProactorEventLoop races uvicorn's socket
    teardown; a single module-scoped server (torn down once at the end) avoids it
    while keeping the hub on the SAME loop the tests use, so cloud-side
    ``bus.send`` reaches the registry directly."""
    _require_supabase()
    config = uvicorn.Config(
        "synapse_cloud.app:app", host="127.0.0.1", port=_PORT, log_level="warning"
    )
    srv = uvicorn.Server(config)
    task = asyncio.create_task(srv.serve())
    for _ in range(100):
        if srv.started:
            break
        await asyncio.sleep(0.05)
    else:  # pragma: no cover
        raise RuntimeError("uvicorn did not start")
    try:
        yield srv
    finally:
        srv.should_exit = True
        await task


@pytest_asyncio.fixture(loop_scope="module")
async def daemon():
    """Seed an isolated org + daemon directly; clean up after. Returns (daemon_id, org_id, token)."""
    db = await service_db()
    suffix = uuid.uuid4().hex[:12]
    org = (
        await db.table("organizations").insert({"name": f"ws-org-{suffix}"}).execute()
    ).data[0]
    org_id = org["id"]
    row = (
        await db.table("daemons")
        .insert({"org_id": org_id, "name": f"ws-daemon-{suffix}", "status": "offline"})
        .execute()
    ).data[0]
    daemon_id = row["id"]
    token = encode_daemon_access_token(daemon_id, org_id)
    try:
        yield daemon_id, org_id, token
    finally:
        try:
            await db.table("organizations").delete().eq("id", org_id).execute()
        except Exception:  # noqa: BLE001
            pass


async def _recv_until(ws, predicate, *, limit: int = 12):
    for _ in range(limit):
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if predicate(frame):
            return frame
    raise AssertionError("expected frame not received")


async def _ping_pong(ws) -> None:
    await ws.send(json.dumps({"type": "ping"}))
    frame = await _recv_until(ws, lambda f: f.get("type") == "pong")
    assert frame == {"type": "pong"}


# ── auth ───────────────────────────────────────────────────────────────────
async def test_auth_failure_no_token_closes_4401(server):
    with pytest.raises(ConnectionClosed) as exc:
        async with websockets.connect(f"{_WS}/ws/daemon") as ws:
            await ws.recv()
    assert exc.value.rcvd.code == WS_UNAUTHORIZED


async def test_auth_bad_token_closes_4401(server):
    with pytest.raises(ConnectionClosed) as exc:
        async with websockets.connect(f"{_WS}/ws/daemon?token=not-a-jwt") as ws:
            await ws.recv()
    assert exc.value.rcvd.code == WS_UNAUTHORIZED


# ── connect + presence ───────────────────────────────────────────────────────
async def test_connect_query_param(server, daemon):
    daemon_id, org_id, token = daemon
    async with websockets.connect(f"{_WS}/ws/daemon?token={token}") as ws:
        await _ping_pong(ws)


async def test_connect_header_and_presence(server, daemon):
    daemon_id, org_id, token = daemon
    async with websockets.connect(
        f"{_WS}/ws/daemon", additional_headers={"Authorization": f"Bearer {token}"}
    ) as ws:
        await _ping_pong(ws)
        db = await service_db()
        pres = (
            await db.table("daemon_presence")
            .select("daemon_id, org_id, hub_node")
            .eq("daemon_id", daemon_id)
            .execute()
        ).data
        assert len(pres) == 1 and pres[0]["org_id"] == org_id
        status = (
            await db.table("daemons").select("status").eq("id", daemon_id).execute()
        ).data
        assert status[0]["status"] == "online"


async def test_disconnect_marks_offline(server, daemon):
    daemon_id, org_id, token = daemon
    async with websockets.connect(f"{_WS}/ws/daemon?token={token}") as ws:
        await _ping_pong(ws)
    # Give the server a moment to run the disconnect finally block.
    await asyncio.sleep(0.3)
    db = await service_db()
    status = (
        await db.table("daemons").select("status").eq("id", daemon_id).execute()
    ).data
    assert status[0]["status"] == "offline"


# ── command delivery + ack ───────────────────────────────────────────────────
async def test_command_delivery_and_ack_clears_buffer(server, daemon):
    daemon_id, org_id, token = daemon
    async with websockets.connect(f"{_WS}/ws/daemon?token={token}") as ws:
        await _ping_pong(ws)
        bus = get_command_bus()
        result = await bus.send(
            daemon_id, "agent.run", {"run_id": "r1", "agent_id": "a1"}, idempotency_key="k1"
        )
        assert result.delivered is True

        cmd = await _recv_until(ws, lambda f: f.get("type") == "command")
        assert cmd["command_type"] == "agent.run"
        assert cmd["payload"]["run_id"] == "r1"
        assert cmd["idempotency_key"] == "k1"
        seq = cmd["seq"]

        conn = ws_hub.get_registry().get(daemon_id)
        assert seq in conn.pending

        await ws.send(json.dumps({"type": "ack", "ack": seq}))
        await _ping_pong(ws)  # round-trip ensures the ack was processed
        assert seq not in conn.pending


async def test_offline_command_queued_then_redelivered(server, daemon):
    daemon_id, org_id, token = daemon
    bus = get_command_bus()
    # Daemon not connected yet -> queued.
    result = await bus.send(daemon_id, "agent.run", {"run_id": "r9"}, idempotency_key="k9")
    assert result.delivered is False and result.queued is True
    assert bus.is_connected(daemon_id) is False

    async with websockets.connect(f"{_WS}/ws/daemon?token={token}") as ws:
        cmd = await _recv_until(ws, lambda f: f.get("type") == "command")
        assert cmd["command_type"] == "agent.run"
        assert cmd["payload"]["run_id"] == "r9"
        assert cmd["idempotency_key"] == "k9"


# ── inbound dispatch ─────────────────────────────────────────────────────────
async def test_inbound_dispatch_reaches_handler(server, daemon):
    daemon_id, org_id, token = daemon
    received: list[tuple] = []

    async def handler(ctx, payload):
        received.append((ctx.daemon_id, ctx.org_id, ctx.run_id, payload.get("x")))

    message_registry.register_handler("test.inbound", handler)
    try:
        async with websockets.connect(f"{_WS}/ws/daemon?token={token}") as ws:
            await ws.send(
                json.dumps({"type": "test.inbound", "seq": 5, "payload": {"run_id": "r5", "x": 42}})
            )
            ack = await _recv_until(ws, lambda f: f.get("type") == "ack")
            assert ack["ack"] == 5
        assert received == [(daemon_id, org_id, "r5", 42)]
    finally:
        message_registry.clear_handlers()


# ── close_stream ─────────────────────────────────────────────────────────────
async def test_close_stream_disconnects(server, daemon):
    daemon_id, org_id, token = daemon
    async with websockets.connect(f"{_WS}/ws/daemon?token={token}") as ws:
        await _ping_pong(ws)
        bus = get_command_bus()
        assert bus.is_connected(daemon_id) is True
        await bus.close_stream(daemon_id, "revoked")
        assert bus.is_connected(daemon_id) is False
        # The socket should be closed from the server side with 4401.
        with pytest.raises(ConnectionClosed) as exc:
            await asyncio.wait_for(ws.recv(), timeout=5)
        assert exc.value.rcvd.code == WS_UNAUTHORIZED
