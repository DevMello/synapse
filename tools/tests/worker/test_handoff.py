"""Daemon handoff (§11): broker authorize matrix + chain-grant cache + handoff + halt.

Self-contained (InMemoryUplink, tmp store, an ephemeral ed25519 key). Covers the security
core (no cloud, no network) — the edge-graph enforcement (H3), mode/hop/budget gates,
envelope redaction (H4), unified-trace lineage (H5), and revoke/halt.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pytest
from nacl.signing import SigningKey

from synapse_worker.commands.orchestrator import handle_halt
from synapse_worker.handoff.broker import (
    Decision,
    authorize_handoff,
    cache_chain_grant,
    canonical_bytes,
    grant_for_edge,
    set_trusted_grant_key,
    successors,
)
from synapse_worker.handoff.mcp_server import HandoffMcpServer
from synapse_worker.handoff.runner import redact_envelope
from synapse_worker.router import CommandContext, on_command

pytestmark = pytest.mark.asyncio

DAEMON = "dmn_1"


def _key():
    sk = SigningKey.generate()
    pub = base64.b64encode(bytes(sk.verify_key)).decode()
    return sk, pub


def _sign(core: dict, sk: SigningKey) -> str:
    return base64.b64encode(sk.sign(canonical_bytes(core)).signature).decode()


def _core(**over):
    base = {
        "org_id": "org1",
        "daemon_id": DAEMON,
        "flow_id": "flw_1",
        "edges": [
            {"from": "agt_planner", "to": "agt_critic", "mode": "tail", "when": None},
            {"from": "agt_critic", "to": "agt_executor", "mode": "tail", "when": "approved"},
        ],
        "routing": "first_match",
        "max_hops": 8,
        "chain_budget_usd": 5.0,
        "max_payload_bytes": 32768,
        "modes": ["return", "tail"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "key_id": "k1",
    }
    base.update(over)
    return base


# ── broker authorize matrix (pure) ──────────────────────────────────────────
async def test_authorize_allows_edge_in_graph():
    sk, pub = _key()
    core = _core()
    res = authorize_handoff(core=core, signature=_sign(core, sk), daemon_id=DAEMON,
                            from_agent_id="agt_planner", to_agent_id="agt_critic",
                            mode="tail", hop=0, trusted_key=pub)
    assert res.decision is Decision.ALLOW


async def test_authorize_rejects_bad_signature():
    sk, pub = _key()
    sig = _sign(_core(), sk)
    res = authorize_handoff(core=_core(max_hops=99), signature=sig, daemon_id=DAEMON,
                            from_agent_id="agt_planner", to_agent_id="agt_critic",
                            mode="tail", trusted_key=pub)
    assert res.decision is Decision.DENY and "signature" in res.reason


async def test_authorize_rejects_off_graph_edge():
    sk, pub = _key()
    core = _core()
    # planner → executor is NOT an edge in the grant (must route via critic).
    res = authorize_handoff(core=core, signature=_sign(core, sk), daemon_id=DAEMON,
                            from_agent_id="agt_planner", to_agent_id="agt_executor",
                            mode="tail", trusted_key=pub)
    assert res.decision is Decision.DENY and "off-graph" in res.reason


async def test_authorize_rejects_cross_daemon():
    sk, pub = _key()
    core = _core(daemon_id="other")
    res = authorize_handoff(core=core, signature=_sign(core, sk), daemon_id=DAEMON,
                            from_agent_id="agt_planner", to_agent_id="agt_critic",
                            mode="tail", trusted_key=pub)
    assert res.decision is Decision.DENY and "daemon" in res.reason


async def test_authorize_rejects_disallowed_mode():
    sk, pub = _key()
    core = _core(modes=["tail"])  # return not allowed
    res = authorize_handoff(core=core, signature=_sign(core, sk), daemon_id=DAEMON,
                            from_agent_id="agt_planner", to_agent_id="agt_critic",
                            mode="return", trusted_key=pub)
    assert res.decision is Decision.DENY and "mode" in res.reason


async def test_authorize_rejects_max_hops():
    sk, pub = _key()
    core = _core(max_hops=2)
    res = authorize_handoff(core=core, signature=_sign(core, sk), daemon_id=DAEMON,
                            from_agent_id="agt_planner", to_agent_id="agt_critic",
                            mode="tail", hop=2, trusted_key=pub)
    assert res.decision is Decision.DENY and "hops" in res.reason


async def test_authorize_rejects_budget_exhausted():
    sk, pub = _key()
    core = _core(chain_budget_usd=1.0)
    res = authorize_handoff(core=core, signature=_sign(core, sk), daemon_id=DAEMON,
                            from_agent_id="agt_planner", to_agent_id="agt_critic",
                            mode="tail", chain_cost_usd=1.5, trusted_key=pub)
    assert res.decision is Decision.DENY and "budget" in res.reason


# ── envelope redaction (H4) ─────────────────────────────────────────────────
async def test_redact_envelope_strips_secrets():
    env = redact_envelope(
        {"task": "ship it", "summary": "key sk-ABCDEF0123456789ABCDEF0123456789", "hop": 1}
    )
    assert "sk-ABCDEF0123456789ABCDEF0123456789" not in env["summary"]
    assert env["task"] == "ship it"  # non-secret text passes through
    assert env["hop"] == 1           # non-text fields preserved


# ── grant cache + handoff + revoke + halt (store-backed) ─────────────────────
async def test_chain_grant_command_caches(store):
    from synapse_worker.commands.handoff import handle_chain_grant

    sk, pub = _key()
    core = _core()
    await handle_chain_grant(
        CommandContext(command_type="chain.grant", daemon_id=DAEMON),
        {"grant_id": "chn_1", "core": core, "signature": _sign(core, sk), "public_key": pub},
    )
    grant = await grant_for_edge("agt_planner", "agt_critic")
    assert grant is not None and grant["grant_id"] == "chn_1"
    succ = await successors("agt_critic")
    assert any(s["to"] == "agt_executor" for s in succ)


async def test_handoff_starts_successor_with_unified_trace(store, uplink):
    sk, pub = _key()
    set_trusted_grant_key(pub)
    core = _core()
    await cache_chain_grant("chn_1", DAEMON, "flw_1", core, _sign(core, sk), pub)

    captured: list[dict] = []

    @on_command("agent.run")
    async def _capture(ctx, payload):  # noqa: ANN001
        captured.append(payload)

    server = HandoffMcpServer(
        default_run_id="rn_root", default_agent_id="agt_planner", daemon_id=DAEMON
    )
    out = await server.call("synapse.handoff", {"to": "agt_critic", "context": {"task": "review"}})

    assert out.get("status") == "handed_off" and out["mode"] == "tail"
    child = out["child_run_id"]
    row = await store.fetchone(
        "SELECT * FROM orchestration_lineage WHERE child_run_id=?", (child,)
    )
    assert row is not None and row["root_run_id"] == "rn_root" and row["verb"] == "handoff"
    assert uplink.of_type("agent.handoff")
    assert captured and captured[0]["agent_id"] == "agt_critic"
    assert captured[0]["root_run_id"] == "rn_root" and captured[0]["handoff_mode"] == "tail"


async def test_handoff_denied_off_graph(store):
    sk, pub = _key()
    set_trusted_grant_key(pub)
    core = _core()
    await cache_chain_grant("chn_1", DAEMON, "flw_1", core, _sign(core, sk), pub)
    server = HandoffMcpServer(
        default_run_id="rn_root", default_agent_id="agt_planner", daemon_id=DAEMON
    )
    # planner may hand off to critic, NOT directly to executor.
    out = await server.call("synapse.handoff", {"to": "agt_executor"})
    assert "error" in out


async def test_chain_revoke_drops_grant(store):
    from synapse_worker.commands.handoff import handle_chain_revoke

    sk, pub = _key()
    core = _core()
    await cache_chain_grant("chn_1", DAEMON, "flw_1", core, _sign(core, sk), pub)
    await handle_chain_revoke(
        CommandContext(command_type="chain.revoke", daemon_id=DAEMON), {"grant_id": "chn_1"}
    )
    assert await grant_for_edge("agt_planner", "agt_critic") is None


async def test_halt_cancels_running_chain(store):
    sk, pub = _key()
    set_trusted_grant_key(pub)
    core = _core()
    await cache_chain_grant("chn_1", DAEMON, "flw_1", core, _sign(core, sk), pub)

    cancels: list[dict] = []

    @on_command("agent.run")
    async def _run(ctx, payload):  # noqa: ANN001
        pass

    @on_command("agent.cancel")
    async def _cancel(ctx, payload):  # noqa: ANN001
        cancels.append(payload)

    server = HandoffMcpServer(
        default_run_id="rn_root", default_agent_id="agt_planner", daemon_id=DAEMON
    )
    out = await server.call("synapse.handoff", {"to": "agt_critic"})
    child = out["child_run_id"]

    # Handoff hops share §2's lineage WAL, so orchestration.halt cancels chains too.
    await handle_halt(
        CommandContext(command_type="orchestration.halt", daemon_id=DAEMON),
        {"grant_id": "chn_1"},
    )
    assert any(c["run_id"] == child for c in cancels)
    row = await store.fetchone(
        "SELECT status FROM orchestration_lineage WHERE child_run_id=?", (child,)
    )
    assert row["status"] == "halted"
