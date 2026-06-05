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


async def test_register_sent_on_connect(mock_cloud, store, settings):
    # §2.3: on connecting the control channel the daemon registers its identity.
    async with _running(mock_cloud, store):
        msg = await mock_cloud.wait_for("daemon.register")
    payload = msg["payload"]
    # All four identity fields are present; name/platform/version are non-empty.
    assert set(payload) >= {"name", "tags", "platform", "version"}
    assert payload["name"]
    assert payload["version"]
    assert "-" in payload["platform"]  # "<system>-<machine>"
    assert isinstance(payload["tags"], list)


async def test_register_reports_configured_name_and_tags(mock_cloud, store):
    # daemon_name / daemon_tags from config are what we report upstream.
    ks = get_keystore()
    ks.set(tokens_mod.KEYSTORE_SERVICE, tokens_mod.KEY_ACCESS, "access-1")
    ks.set(tokens_mod.KEYSTORE_SERVICE, tokens_mod.KEY_REFRESH, "refresh-1")
    base = mock_cloud.url.replace("ws://", "http://")
    settings = Settings(
        worker_env="test",
        cloud_base_url=base,
        heartbeat_interval_seconds=1,
        reconnect_max_seconds=2,
        verify_tls=False,
        daemon_name="prod-box-7",
        daemon_tags="gpu, us-east, beta",
    )
    mgr = ConnectionManager(_FakeDaemon(settings=settings, store=store))
    task = asyncio.create_task(mgr.run())
    try:
        msg = await mock_cloud.wait_for("daemon.register")
    finally:
        await mgr.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    assert msg["payload"]["name"] == "prod-box-7"
    assert msg["payload"]["tags"] == ["gpu", "us-east", "beta"]


async def test_register_includes_e2e_public_key_when_paired(mock_cloud, store):
    # A paired daemon has a stored X25519 public key; register must carry it so the
    # cloud can populate daemons.e2e_public_key (env-var sealing, §4.6).
    from synapse_worker.auth import keys as auth_keys

    ks = get_keystore()
    ks.set(tokens_mod.KEYSTORE_SERVICE, tokens_mod.KEY_ACCESS, "access-1")
    ks.set(tokens_mod.KEYSTORE_SERVICE, tokens_mod.KEY_REFRESH, "refresh-1")
    ks.set(auth_keys.SERVICE, auth_keys.KEY_DAEMON_PUBLIC, "PUBKEY-b64")

    settings = _settings_for(mock_cloud)
    mgr = ConnectionManager(_FakeDaemon(settings=settings, store=store))
    task = asyncio.create_task(mgr.run())
    try:
        msg = await mock_cloud.wait_for("daemon.register")
    finally:
        await mgr.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    assert msg["payload"]["e2e_public_key"] == "PUBKEY-b64"


async def test_register_omits_public_key_when_unpaired(mock_cloud, store):
    # No daemon public key in the keystore -> the field is simply absent (no crash).
    async with _running(mock_cloud, store):
        msg = await mock_cloud.wait_for("daemon.register")
    assert "e2e_public_key" not in msg["payload"]


async def test_handle_token_expiry_signals_refresh_outcome(mock_cloud, store, monkeypatch):
    # Unit-level: _handle_token_expiry returns True on a successful refresh, False on
    # failure (the signal the channel loop uses to decide reconnect-now vs back-off).
    mgr = ConnectionManager(_FakeDaemon(settings=_settings_for(mock_cloud), store=store))

    async def _ok(_settings):
        return "new-access"

    monkeypatch.setattr(tokens_mod, "refresh", _ok)
    assert await mgr._handle_token_expiry() is True

    async def _fail(_settings):
        return None

    monkeypatch.setattr(tokens_mod, "refresh", _fail)
    assert await mgr._handle_token_expiry() is False


async def test_failed_refresh_backs_off_not_hotloops(mock_cloud, store, monkeypatch):
    # A revoked daemon: the cloud 4401s EVERY handshake and refresh always fails. The
    # loop must take the backoff path (sleep) instead of `continue`-ing into a hot loop.
    mock_cloud.reject_all = True

    async def _no_refresh(_settings):
        return None

    monkeypatch.setattr(tokens_mod, "refresh", _no_refresh)

    sleeps = {"n": 0}

    async def _counting_sleep(self, base):
        sleeps["n"] += 1
        await asyncio.sleep(0.01)  # keep the test fast but still yield like real backoff

    monkeypatch.setattr(ConnectionManager, "_sleep_with_jitter", _counting_sleep)

    async with _running(mock_cloud, store):
        # Backoff must run at least once -> we did NOT skip it via an immediate continue.
        await _wait(lambda: sleeps["n"] >= 1, timeout=3.0)
    assert sleeps["n"] >= 1
