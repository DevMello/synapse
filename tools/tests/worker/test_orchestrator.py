"""Daemon orchestration: broker authorize matrix + grant cache + run_agent + halt.

Self-contained (InMemoryUplink, tmp store, an ephemeral ed25519 key). Covers the
security core (no cloud, no network).
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pytest
from nacl.signing import SigningKey

from synapse_worker.orchestrator import broker
from synapse_worker.orchestrator.broker import (
    Decision,
    authorize,
    canonical_bytes,
    cache_grant,
    grant_for_agent,
    set_trusted_grant_key,
)
from synapse_worker.orchestrator.mcp_server import OrchestratorMcpServer
from synapse_worker.router import CommandContext, dispatch, on_command

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
        "agent_id": "agt_planner",
        "daemon_id": DAEMON,
        "verbs": ["run"],
        "target_allow": ["agt_researcher"],
        "max_depth": 3,
        "max_fan_out": 5,
        "tree_budget_usd": 10.0,
        "protected_fields": [],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "key_id": "k1",
    }
    base.update(over)
    return base


# ── broker authorize matrix (pure) ──────────────────────────────────────────
async def test_authorize_allows_valid():
    sk, pub = _key()
    core = _core()
    res = authorize(core=core, signature=_sign(core, sk), daemon_id=DAEMON, verb="run",
                    target_agent_id="agt_researcher", caller_depth=0, trusted_key=pub)
    assert res.decision is Decision.ALLOW


async def test_authorize_rejects_bad_signature():
    sk, pub = _key()
    core = _core()
    sig = _sign(core, sk)
    res = authorize(core=_core(max_depth=99), signature=sig, daemon_id=DAEMON, verb="run",
                    target_agent_id="agt_researcher", caller_depth=0, trusted_key=pub)
    assert res.decision is Decision.DENY and "signature" in res.reason


async def test_authorize_rejects_expired():
    sk, pub = _key()
    core = _core(expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    res = authorize(core=core, signature=_sign(core, sk), daemon_id=DAEMON, verb="run",
                    target_agent_id="agt_researcher", caller_depth=0, trusted_key=pub)
    assert res.decision is Decision.DENY and "expired" in res.reason


async def test_authorize_rejects_cross_daemon():
    sk, pub = _key()
    core = _core(daemon_id="other-daemon")
    res = authorize(core=core, signature=_sign(core, sk), daemon_id=DAEMON, verb="run",
                    target_agent_id="agt_researcher", caller_depth=0, trusted_key=pub)
    assert res.decision is Decision.DENY and "daemon" in res.reason


async def test_authorize_rejects_ungranted_verb():
    sk, pub = _key()
    core = _core(verbs=["run"])
    res = authorize(core=core, signature=_sign(core, sk), daemon_id=DAEMON, verb="create",
                    target_agent_id="agt_researcher", caller_depth=0, trusted_key=pub)
    assert res.decision is Decision.DENY and "verb" in res.reason


async def test_authorize_rejects_target_not_allowed():
    sk, pub = _key()
    core = _core(target_allow=["agt_other"])
    res = authorize(core=core, signature=_sign(core, sk), daemon_id=DAEMON, verb="run",
                    target_agent_id="agt_researcher", caller_depth=0, trusted_key=pub)
    assert res.decision is Decision.DENY and "target" in res.reason


async def test_authorize_rejects_max_depth():
    sk, pub = _key()
    core = _core(max_depth=3)
    res = authorize(core=core, signature=_sign(core, sk), daemon_id=DAEMON, verb="run",
                    target_agent_id="agt_researcher", caller_depth=3, trusted_key=pub)
    assert res.decision is Decision.DENY and "depth" in res.reason


async def test_authorize_no_escalation():
    sk, pub = _key()
    core = _core()
    res = authorize(core=core, signature=_sign(core, sk), daemon_id=DAEMON, verb="run",
                    target_agent_id="agt_researcher", caller_depth=0,
                    caller_perms={"fs"}, target_perms={"fs", "shell"}, trusted_key=pub)
    assert res.decision is Decision.DENY and "escalation" in res.reason


async def test_authorize_create_requires_hitl():
    sk, pub = _key()
    core = _core(verbs=["run", "create"])
    res = authorize(core=core, signature=_sign(core, sk), daemon_id=DAEMON, verb="create",
                    target_agent_id="agt_researcher", caller_depth=0, trusted_key=pub)
    assert res.decision is Decision.REQUIRE_HITL


# ── grant cache + run_agent + revoke + halt (store-backed) ───────────────────
async def test_grant_command_caches(store):
    # Call the handler directly: @on_command registration is a one-time import
    # side-effect, but conftest clear_handlers() wipes the registry each test.
    from synapse_worker.commands.orchestrator import handle_grant

    sk, pub = _key()
    core = _core()
    await handle_grant(
        CommandContext(command_type="orchestration.grant", daemon_id=DAEMON),
        {"grant_id": "grn_1", "core": core, "signature": _sign(core, sk), "public_key": pub},
    )
    cached = await grant_for_agent("agt_planner")
    assert cached is not None and cached["grant_id"] == "grn_1"


async def test_run_agent_spawns_child_with_lineage(store, uplink):
    sk, pub = _key()
    set_trusted_grant_key(pub)
    core = _core()
    await cache_grant("grn_1", "agt_planner", core, _sign(core, sk), pub)

    captured: list[dict] = []

    @on_command("agent.run")
    async def _capture(ctx, payload):  # noqa: ANN001
        captured.append(payload)

    server = OrchestratorMcpServer(
        default_run_id="rn_parent", default_agent_id="agt_planner", daemon_id=DAEMON
    )
    out = await server.call("orchestrator.run_agent", {"agent_id": "agt_researcher"})

    assert out.get("status") == "spawned"
    child = out["child_run_id"]
    # lineage row written
    row = await store.fetchone(
        "SELECT * FROM orchestration_lineage WHERE child_run_id=?", (child,)
    )
    assert row is not None and row["root_run_id"] == "rn_parent" and row["depth"] == 1
    # async audit emitted
    assert uplink.of_type("agent.orchestrate")
    # child agent.run dispatched, lineage-tagged
    assert captured and captured[0]["agent_id"] == "agt_researcher"
    assert captured[0]["initiator"] == "agent"


async def test_run_agent_denied_without_grant(store):
    set_trusted_grant_key("")  # no trusted key configured
    server = OrchestratorMcpServer(
        default_run_id="rn_p", default_agent_id="agt_nogrant", daemon_id=DAEMON
    )
    out = await server.call("orchestrator.run_agent", {"agent_id": "agt_researcher"})
    assert "error" in out


async def test_revoke_drops_grant(store):
    from synapse_worker.commands.orchestrator import handle_revoke

    sk, pub = _key()
    core = _core()
    await cache_grant("grn_1", "agt_planner", core, _sign(core, sk), pub)
    await handle_revoke(
        CommandContext(command_type="grant.revoke", daemon_id=DAEMON),
        {"grant_id": "grn_1"},
    )
    assert await grant_for_agent("agt_planner") is None


async def test_halt_cancels_running_tree(store):
    from synapse_worker.commands.orchestrator import handle_halt

    sk, pub = _key()
    set_trusted_grant_key(pub)
    core = _core()
    await cache_grant("grn_1", "agt_planner", core, _sign(core, sk), pub)

    cancels: list[dict] = []

    @on_command("agent.run")
    async def _run(ctx, payload):  # noqa: ANN001
        pass

    @on_command("agent.cancel")
    async def _cancel(ctx, payload):  # noqa: ANN001
        cancels.append(payload)

    server = OrchestratorMcpServer(
        default_run_id="rn_parent", default_agent_id="agt_planner", daemon_id=DAEMON
    )
    out = await server.call("orchestrator.run_agent", {"agent_id": "agt_researcher"})
    child = out["child_run_id"]

    await handle_halt(
        CommandContext(command_type="orchestration.halt", daemon_id=DAEMON),
        {"grant_id": "grn_1"},
    )
    assert any(c["run_id"] == child for c in cancels)
    row = await store.fetchone(
        "SELECT status FROM orchestration_lineage WHERE child_run_id=?", (child,)
    )
    assert row["status"] == "halted"
