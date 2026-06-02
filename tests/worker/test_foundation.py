"""Foundation smoke tests: the seams every feature unit builds on.

These don't exercise feature behavior (no units installed yet) — they prove the
skeleton assembles, the store round-trips durable state, the wire envelope matches the
cloud, the crypto primitives work, and the registries ship the right defaults.
"""
from __future__ import annotations

import pytest

from synapse_worker import wire
from synapse_worker.app import build_daemon
from synapse_worker.capabilities.registry import DEFAULT_CAPABILITIES, get_capability_registry
from synapse_worker.crypto import generate_keypair, seal, seal_open
from synapse_worker.filtering.base import get_filter_chain
from synapse_worker.router import CommandContext, clear_handlers, dispatch, on_command
from synapse_worker.runtime.base import AgentManifest, Usage


def test_settings_is_test(settings):
    assert settings.is_test is True
    assert settings.home_dir.name == "home"


def test_build_daemon_assembles(settings):
    daemon = build_daemon(settings)
    assert daemon.store is not None
    assert isinstance(daemon.commands, list)  # no units yet -> empty, but importable


def test_ws_url_derivation(monkeypatch):
    from synapse_worker import config

    monkeypatch.setenv("SYNAPSE_CLOUD_BASE_URL", "https://cloud.example.com")
    config.reset_settings_cache()
    s = config.get_settings()
    assert s.control_ws_url == "wss://cloud.example.com/ws/daemon"
    assert s.telemetry_ws_url == "wss://cloud.example.com/ws/daemon/telemetry"


# ── wire envelope matches the cloud ─────────────────────────────────────────
def test_command_frame_roundtrip():
    frame = {
        "type": "command",
        "seq": 7,
        "command_type": "agent.run",
        "payload": {"run_id": "rn_1"},
        "idempotency_key": "k1",
    }
    cmd = wire.parse_command(frame)
    assert cmd is not None
    assert cmd.command_type == "agent.run"
    assert cmd.seq == 7
    assert cmd.payload == {"run_id": "rn_1"}
    assert cmd.idempotency_key == "k1"


def test_ack_and_message_frames():
    assert wire.build_ack(5) == {"type": "ack", "ack": 5}
    msg = wire.build_message("run.finished", {"status": "success"}, 3)
    assert msg == {"type": "run.finished", "seq": 3, "payload": {"status": "success"}}


def test_parse_frame_rejects_garbage():
    assert wire.parse_frame("{not json") is None
    assert wire.parse_frame("[1,2,3]") is None  # not an object


# ── store durability ────────────────────────────────────────────────────────
async def test_outbound_queue_orders_and_acks(store):
    s1 = await store.enqueue_outbound("telemetry", "run.finished", {"i": 1})
    s2 = await store.enqueue_outbound("telemetry", "run.finished", {"i": 2})
    assert s2 > s1
    pending = await store.pending_outbound("telemetry")
    assert [p["payload"]["i"] for p in pending] == [1, 2]
    await store.ack_outbound(s1)
    pending = await store.pending_outbound("telemetry")
    assert [p["payload"]["i"] for p in pending] == [2]


async def test_idempotency_dedupe(store):
    assert await store.mark_seen("key-a", "agent.run") is True
    assert await store.mark_seen("key-a", "agent.run") is False  # duplicate
    assert await store.mark_seen("key-b", "agent.run") is True


async def test_kv_roundtrip(store):
    await store.kv_set("daemon_id", {"id": "dmn_1"})
    assert await store.kv_get("daemon_id") == {"id": "dmn_1"}
    assert await store.kv_get("missing") is None


# ── command dispatch seam ───────────────────────────────────────────────────
async def test_dispatch_invokes_registered_handler():
    clear_handlers()
    seen = []

    @on_command("daemon.ping")
    async def _h(ctx: CommandContext, payload: dict):
        seen.append((ctx.command_type, payload))

    n = await dispatch("daemon.ping", CommandContext(command_type="daemon.ping"), {"x": 1})
    assert n == 1
    assert seen == [("daemon.ping", {"x": 1})]
    clear_handlers()


async def test_dispatch_swallows_handler_errors():
    clear_handlers()

    @on_command("boom")
    async def _h(ctx, payload):
        raise RuntimeError("kaboom")

    # Should not raise — handler failures are isolated so the control loop survives.
    assert await dispatch("boom", CommandContext(command_type="boom"), {}) == 1
    clear_handlers()


# ── crypto ──────────────────────────────────────────────────────────────────
def test_sealed_box_roundtrip():
    kp = generate_keypair()
    ct = seal(kp.public_key, b"sk-secret-value")
    assert seal_open(kp.private_key, ct) == b"sk-secret-value"


def test_seal_open_rejects_wrong_key():
    kp = generate_keypair()
    other = generate_keypair()
    ct = seal(kp.public_key, b"x")
    with pytest.raises(Exception):
        seal_open(other.private_key, ct)


# ── registries ship the right defaults ──────────────────────────────────────
def test_capability_defaults_auto_attached():
    reg = get_capability_registry()
    attached = reg.attached("agt_new")
    for cap in DEFAULT_CAPABILITIES:
        assert cap in attached
    # A non-default capability is opt-in.
    assert "browser" not in attached


def test_filter_chain_passthrough_by_default():
    chain = get_filter_chain()
    out = chain.screen_outbound("nothing to redact")
    assert out.text == "nothing to redact"
    assert out.findings == []


# ── manifest + usage ────────────────────────────────────────────────────────
def test_agent_manifest_from_toml():
    text = """
[agent]
id = "agt_1"
name = "triage-bot"
type = "cli"
version = 3

[cli]
command = "claude"

[limits]
max_cost_usd = 2.0
"""
    m = AgentManifest.from_toml(text)
    assert m.id == "agt_1"
    assert m.type == "cli"
    assert m.version == 3
    assert m.max_cost_usd == 2.0


def test_secure_write_preserves_binary(settings):
    # Regression: secure_write must not translate bytes (no \n -> \r\n on Windows),
    # or sealed ciphertext / keys round-trip corrupt.
    from synapse_worker.paths import paths_for, secure_write

    paths = paths_for(settings)
    paths.ensure_layout()
    blob = bytes(range(256)) + b"\n\r\n\x00line"
    target = paths.keys_dir / "binblob.bin"
    secure_write(target, blob)
    assert target.read_bytes() == blob


def test_usage_add():
    a = Usage(input_tokens=10, output_tokens=5, cost_usd=0.01)
    b = Usage(input_tokens=3, output_tokens=2, cost_usd=0.02, estimated=True)
    c = a.add(b)
    assert c.input_tokens == 13
    assert c.output_tokens == 7
    assert c.cost_usd == 0.03
    assert c.estimated is True
