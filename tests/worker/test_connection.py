"""Connection Manager unit tests (§4.1).

Self-contained: drives a real :class:`ConnectionManager` against the in-process
:class:`MockCloud` WS hub (the ``mock_cloud`` fixture), using the tmp ``store`` +
``settings`` from conftest. No Supabase, no real keychain, no network.

We point the manager at the mock by building a Settings whose ``cloud_base_url`` is the
mock's ``http://`` form (``Settings.ws_url`` turns http→ws), then construct the manager
with a tiny daemon stand-in carrying that settings + the connected store.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass

import pytest

from synapse_worker.config import Settings
from synapse_worker.connection.manager import ConnectionManager
from synapse_worker.connection import tokens as tokens_mod
from synapse_worker.crypto import get_keystore
from synapse_worker.router import CommandContext, clear_handlers, on_command
from synapse_worker.store import LocalStore
from synapse_worker.uplink import CHANNEL_CONTROL, CHANNEL_TELEMETRY, get_uplink

pytestmark = pytest.mark.asyncio


@dataclass
class _FakeDaemon:
    settings: Settings
    store: LocalStore


def _settings_for(mock_cloud) -> Settings:
    """Settings whose ws_url points at the mock hub (http -> ws derivation)."""
    base = mock_cloud.url.replace("ws://", "http://")
    return Settings(
        worker_env="test",
        cloud_base_url=base,
        ws_control_path="/ws/daemon",
        ws_telemetry_path="/ws/daemon/telemetry",
        heartbeat_interval_seconds=1,
        reconnect_max_seconds=2,
        verify_tls=False,
    )


@contextlib.asynccontextmanager
async def _running(mock_cloud, store, *, seed_tokens: bool = True):
    """Start a ConnectionManager against the mock; guarantee teardown."""
    if seed_tokens:
        ks = get_keystore()
        ks.set(tokens_mod.KEYSTORE_SERVICE, tokens_mod.KEY_ACCESS, "access-1")
        ks.set(tokens_mod.KEYSTORE_SERVICE, tokens_mod.KEY_REFRESH, "refresh-1")
    settings = _settings_for(mock_cloud)
    mgr = ConnectionManager(_FakeDaemon(settings=settings, store=store))
    task = asyncio.create_task(mgr.run())
    try:
        yield mgr
    finally:
        await mgr.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def _wait(predicate, timeout: float = 3.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


async def test_connects_both_channels(mock_cloud, store, settings):
    async with _running(mock_cloud, store):
        await _wait(lambda: len(mock_cloud.control_conns) >= 1
                    and len(mock_cloud.telemetry_conns) >= 1)
        assert mock_cloud.connect_count >= 2


async def test_presents_bearer_token(mock_cloud, store, settings):
    async with _running(mock_cloud, store):
        await _wait(lambda: mock_cloud.last_token is not None)
    # The handshake carried our access token as a Bearer header.
    assert mock_cloud.last_token == "Bearer access-1"


async def test_command_dispatched_and_acked(mock_cloud, store, settings):
    clear_handlers()
    seen: list[tuple[str, dict]] = []

    @on_command("daemon.ping")
    async def _h(ctx: CommandContext, payload: dict):
        seen.append((ctx.command_type, payload))

    try:
        async with _running(mock_cloud, store):
            await _wait(lambda: len(mock_cloud.control_conns) >= 1)
            seq = await mock_cloud.send_command("daemon.ping", {"x": 1})
            await _wait(lambda: seen and seq in mock_cloud.acks)
        assert seen == [("daemon.ping", {"x": 1})]
        assert seq in mock_cloud.acks
    finally:
        clear_handlers()


async def test_duplicate_command_dispatched_once(mock_cloud, store, settings):
    clear_handlers()
    seen: list[dict] = []

    @on_command("agent.run")
    async def _h(ctx: CommandContext, payload: dict):
        seen.append(payload)

    try:
        async with _running(mock_cloud, store):
            await _wait(lambda: len(mock_cloud.control_conns) >= 1)
            s1 = await mock_cloud.send_command("agent.run", {"n": 1}, idempotency_key="dup-1")
            await _wait(lambda: s1 in mock_cloud.acks)
            s2 = await mock_cloud.send_command("agent.run", {"n": 2}, idempotency_key="dup-1")
            await _wait(lambda: s2 in mock_cloud.acks)
        # Dispatched exactly once despite two deliveries; BOTH are acked.
        assert len(seen) == 1
        assert s1 in mock_cloud.acks and s2 in mock_cloud.acks
    finally:
        clear_handlers()


async def test_upstream_send_arrives_and_marks_acked(mock_cloud, store, settings):
    async with _running(mock_cloud, store):
        await _wait(lambda: len(mock_cloud.control_conns) >= 1)
        await get_uplink().send("run.finished", {"status": "success"}, channel=CHANNEL_CONTROL)
        msg = await mock_cloud.wait_for("run.finished")
        assert msg["payload"] == {"status": "success"}
        seq = msg["seq"]
        # The cloud acked by seq -> the receive loop marked that outbound row acked.
        await _wait(lambda: True)  # let the ack round-trip
        async def _row_acked() -> bool:
            pending = await store.pending_outbound(CHANNEL_CONTROL)
            return all(p["seq"] != seq for p in pending)
        for _ in range(100):
            if await _row_acked():
                break
            await asyncio.sleep(0.02)
        assert await _row_acked()


async def test_telemetry_channel_upstream(mock_cloud, store, settings):
    async with _running(mock_cloud, store):
        await _wait(lambda: len(mock_cloud.telemetry_conns) >= 1)
        await get_uplink().send("memory.delta", {"d": 1}, channel=CHANNEL_TELEMETRY)
        msg = await mock_cloud.wait_for("memory.delta")
        assert msg["payload"] == {"d": 1}


async def test_heartbeat_emitted(mock_cloud, store, settings):
    async with _running(mock_cloud, store):
        await _wait(lambda: mock_cloud.heartbeats >= 1, timeout=4.0)
    assert mock_cloud.heartbeats >= 1


async def test_offline_buffer_replays_on_connect(mock_cloud, store, settings):
    # Enqueue an outbound row directly (as if produced while disconnected), then start
    # the manager: on connect it must replay the unacked row in order.
    seq = await store.enqueue_outbound(CHANNEL_CONTROL, "run.finished", {"buffered": True})
    async with _running(mock_cloud, store):
        msg = await mock_cloud.wait_for("run.finished")
        assert msg["payload"] == {"buffered": True}
        assert msg["seq"] == seq
        # And it gets acked -> row cleared.
        async def _cleared() -> bool:
            pending = await store.pending_outbound(CHANNEL_CONTROL)
            return all(p["seq"] != seq for p in pending)
        for _ in range(100):
            if await _cleared():
                break
            await asyncio.sleep(0.02)
        assert await _cleared()


async def test_reconnect_after_4401_refreshes_token(mock_cloud, store, settings, monkeypatch):
    refreshed = asyncio.Event()

    async def _fake_refresh(_settings):
        # Simulate a successful rotation: store a new access token + return it.
        tokens_mod.store_tokens("access-2", "refresh-2")
        refreshed.set()
        return "access-2"

    monkeypatch.setattr(tokens_mod, "refresh", _fake_refresh)

    # Reject the very first socket with 4401 -> manager refreshes, then reconnects.
    mock_cloud.reject_next = True
    async with _running(mock_cloud, store):
        await _wait(lambda: refreshed.is_set(), timeout=4.0)
        # After refresh it reconnects and the new token is presented.
        await _wait(lambda: mock_cloud.last_token == "Bearer access-2", timeout=4.0)
    assert refreshed.is_set()
    assert mock_cloud.last_token == "Bearer access-2"


async def test_reconcile_sent_on_connect(mock_cloud, store, settings):
    # An in-flight run with a checkpoint -> reconcile should list it.
    import time

    await store.execute(
        "INSERT INTO run_history (run_id, agent_id, status, started_at)"
        " VALUES (?,?,?,?)",
        ("rn_1", "agt_1", "running", time.time()),
    )
    await store.execute(
        "INSERT INTO checkpoints (run_id, seq, step_cursor, status, created_at)"
        " VALUES (?,?,?,?,?)",
        ("rn_1", 5, 5, "committed", time.time()),
    )
    async with _running(mock_cloud, store):
        msg = await mock_cloud.wait_for("run.reconcile")
        runs = msg["payload"]["runs"]
        assert any(r["run_id"] == "rn_1" and r["checkpoint_seq"] == 5 for r in runs)


async def test_reconcile_empty_is_defensive(mock_cloud, store, settings):
    # No runs at all -> reconcile still sent with an empty list (no crash).
    async with _running(mock_cloud, store):
        msg = await mock_cloud.wait_for("run.reconcile")
        assert msg["payload"]["runs"] == []
