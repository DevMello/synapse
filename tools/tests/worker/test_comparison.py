"""Model Comparison Runs — daemon unit tests (possible-features §10).

Covers the four daemon pieces: blast-radius classification, the draft-mode shim
(read-only runs / side-effecting simulated / HITL "would have paused"), the agentic
tool-calling loop added to the API adapter, and the group executor's fan-out + cost cap +
variant model override. All self-contained: NO network (``_post`` is monkeypatched), NO
Supabase. Uses the conftest ``store``/``uplink`` fixtures.
"""
from __future__ import annotations

import asyncio

import pytest

from synapse_worker.comparison.draft_shim import DraftCollector, DraftToolExecutor
from synapse_worker.comparison.executor import run_group
from synapse_worker.runtime.api_adapter import ApiAdapter
from synapse_worker.runtime.base import (
    AgentManifest,
    RunContext,
    get_price_table,
    set_price_table,
)
from synapse_worker.runtime.tools import (
    HITL_GATED,
    READ_ONLY,
    SIDE_EFFECTING,
    DefaultToolExecutor,
    classify_tool,
)

# ── manifest helpers ─────────────────────────────────────────────────────────
_TOOLS = [
    {"name": "send_email", "blast_radius": "side_effecting"},
    {"name": "read_file", "blast_radius": "read_only"},
    {"name": "charge_card", "hitl": True},
]


def _manifest(model: str = "base-model", tools=None, max_tool_calls: int = 3) -> AgentManifest:
    return AgentManifest(
        id="agt_x",
        name="X",
        type="api",
        api={"provider": "anthropic", "model": model, "max_tokens": 128},
        limits={"max_tool_calls": max_tool_calls},
        tools=tools if tools is not None else list(_TOOLS),
    )


def _ctx(manifest: AgentManifest, executor=None, run_id: str = "run-1") -> RunContext:
    return RunContext(
        run_id=run_id,
        agent_id=manifest.id,
        manifest=manifest,
        prompt_vars={"prompt": "do the task"},
        env={},
        emit=None,
        tool_executor=executor,
    )


_AGENT_TOML = """
[agent]
id = "agt_cmp"
name = "Compare Me"
type = "api"
version = 1

[api]
provider = "anthropic"
model = "base-model"
max_tokens = 128

[limits]
max_tool_calls = 2

[[tools]]
name = "send_email"
blast_radius = "side_effecting"
"""


async def _deploy_agent(store, agent_id: str = "agt_cmp") -> None:
    import time

    await store.execute(
        "INSERT INTO agents (id, name, type, platform, version, manifest, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (agent_id, "Compare Me", "api", "any", 1, _AGENT_TOML, time.time()),
    )


# ── 1. blast-radius classification ───────────────────────────────────────────
def test_classify_from_manifest_and_default():
    assert classify_tool("send_email", _TOOLS) == SIDE_EFFECTING
    assert classify_tool("read_file", _TOOLS) == READ_ONLY
    assert classify_tool("charge_card", _TOOLS) == HITL_GATED
    # builtin default for a known-safe name
    assert classify_tool("search", []) == READ_ONLY
    # unknown -> conservative side_effecting (never run for real in draft mode)
    assert classify_tool("mystery_tool", []) == SIDE_EFFECTING


# ── 2. draft-mode shim ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_draft_shim_read_only_executes():
    inner = DefaultToolExecutor()
    inner.register("read_file", lambda args: _ok({"contents": "hello"}))
    collector = DraftCollector()
    shim = DraftToolExecutor(inner, collector, _TOOLS)

    result = await shim.execute("read_file", {"path": "./a"})
    assert result == {"contents": "hello"}          # real result fed back
    assert collector.proposed_actions == []         # no side effect recorded
    assert collector.tool_calls[0]["simulated"] is False


@pytest.mark.asyncio
async def test_draft_shim_side_effecting_simulated_and_redacted():
    inner = DefaultToolExecutor()
    collector = DraftCollector()
    shim = DraftToolExecutor(inner, collector, _TOOLS)

    result = await shim.execute("send_email", {"to": "alice@example.com", "body": "hi"})
    assert result == {"status": "ok", "simulated": True}
    assert len(collector.proposed_actions) == 1
    redacted = collector.proposed_actions[0]["args_redacted"]
    # the email is screened through Layer A before being recorded
    assert "alice@example.com" not in str(redacted)
    assert "REDACTED" in str(redacted)


@pytest.mark.asyncio
async def test_draft_shim_hitl_records_would_have_paused():
    collector = DraftCollector()
    shim = DraftToolExecutor(DefaultToolExecutor(), collector, _TOOLS)

    result = await shim.execute("charge_card", {"amount": 9})
    assert result["simulated"] is True and result["would_have_paused"] is True
    assert len(collector.simulated_hitl) == 1
    assert len(collector.proposed_actions) == 1 and collector.proposed_actions[0]["hitl"] is True


def _ok(value):
    async def _coro():
        return value

    return _coro()


# ── 3. API adapter agentic tool loop ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_api_adapter_tool_loop_anthropic(monkeypatch):
    """Model proposes a tool (turn 1) -> shim simulates it -> model answers (turn 2)."""
    calls = {"n": 0}

    async def fake_post(self, url, *, headers, json):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "send_email", "input": {"to": "x@y.com"}}
                ],
                "usage": {"input_tokens": 10, "output_tokens": 4},
            }
        # second turn: the model produced final text after seeing the tool result
        return {
            "content": [{"type": "text", "text": "done"}],
            "usage": {"input_tokens": 6, "output_tokens": 3},
        }

    monkeypatch.setattr(ApiAdapter, "_post", fake_post)
    collector = DraftCollector()
    manifest = _manifest()
    ctx = _ctx(manifest, DraftToolExecutor(DefaultToolExecutor(), collector, manifest.tools))

    result = await ApiAdapter().run(ctx)
    assert result.status == "success"
    assert result.output == "done"
    assert calls["n"] == 2                                  # looped
    assert len(collector.proposed_actions) == 1            # send_email simulated, not run
    # tokens accumulate across both turns
    assert result.usage.input_tokens == 16


@pytest.mark.asyncio
async def test_api_adapter_no_tools_single_shot(monkeypatch):
    """With no tools the loop is a single turn (back-compat with the old adapter)."""
    posts = {"n": 0}

    async def fake_post(self, url, *, headers, json):
        posts["n"] += 1
        return {"content": [{"type": "text", "text": "hi"}], "usage": {"input_tokens": 2, "output_tokens": 1}}

    monkeypatch.setattr(ApiAdapter, "_post", fake_post)
    manifest = _manifest(tools=[])
    result = await ApiAdapter().run(_ctx(manifest))
    assert result.output == "hi"
    assert posts["n"] == 1


# ── 4. group executor ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_run_group_fans_out_and_marks_ready(store, uplink, monkeypatch):
    await _deploy_agent(store)
    seen_models: list[str] = []

    async def fake_post(self, url, *, headers, json):
        seen_models.append(json.get("model"))
        return {"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 5, "output_tokens": 2}}

    monkeypatch.setattr(ApiAdapter, "_post", fake_post)

    await run_group(
        group_id="grp-1",
        agent_id="agt_cmp",
        daemon_id="dmn-1",
        models=["claude-opus-4-8", "gpt-5", "gemini-2-pro"],
        input={"prompt": "compare me"},
        max_parallel_variants=3,
    )

    variants = uplink.of_type("comparison.variant_finished")
    ready = uplink.of_type("comparison.group_ready")
    assert len(variants) == 3
    assert {v.payload["variant_model"] for v in variants} == {
        "claude-opus-4-8", "gpt-5", "gemini-2-pro"
    }
    assert all(v.payload["run_group_id"] == "grp-1" for v in variants)
    assert len(ready) == 1 and ready[0].payload["status"] == "ready_for_review"
    # only the model varied across variants (§10.3)
    assert set(seen_models) == {"claude-opus-4-8", "gpt-5", "gemini-2-pro"}

    rows = await store.fetchall("SELECT model, status FROM comparison_variants WHERE group_id=?", ("grp-1",))
    assert len(rows) == 3 and all(r["status"] == "succeeded" for r in rows)


@pytest.mark.asyncio
async def test_run_group_cost_cap_hard_stops(store, uplink, monkeypatch):
    await _deploy_agent(store)

    async def fake_post(self, url, *, headers, json):
        return {"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1000, "output_tokens": 1000}}

    monkeypatch.setattr(ApiAdapter, "_post", fake_post)
    # Price the model so each variant has a real, non-zero cost.
    prev = get_price_table()
    set_price_table({"base-model": {"input": 100.0, "output": 100.0}})
    try:
        await run_group(
            group_id="grp-cap",
            agent_id="agt_cmp",
            daemon_id="dmn-1",
            models=["base-model", "base-model", "base-model"],
            input={"prompt": "x"},
            group_cost_cap=0.0001,          # tiny: the first variant blows it
            max_parallel_variants=1,         # sequential so the cap can hard-stop the rest
        )
    finally:
        set_price_table(prev)

    rows = await store.fetchall("SELECT status FROM comparison_variants WHERE group_id=?", ("grp-cap",))
    statuses = [r["status"] for r in rows]
    assert "skipped" in statuses          # at least one variant was hard-stopped by the cap


@pytest.mark.asyncio
async def test_cancel_group_sets_terminal_cancelled_status(store, uplink, monkeypatch):
    """A cancel mid-flight must leave the group 'cancelled' — not be overwritten by the
    run_group coroutine finishing as 'ready_for_review' (cancel/finish race)."""
    await _deploy_agent(store)

    async def slow_post(self, url, *, headers, json):
        await asyncio.sleep(0.05)
        return {"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 1}}

    monkeypatch.setattr(ApiAdapter, "_post", slow_post)

    task = asyncio.create_task(
        run_group(
            group_id="grp-cancel", agent_id="agt_cmp", daemon_id="d",
            models=["base-model", "base-model"], input={"prompt": "x"}, max_parallel_variants=2,
        )
    )
    await asyncio.sleep(0.01)  # let variants start
    from synapse_worker.comparison.executor import cancel_group
    await cancel_group("grp-cancel")
    await task

    row = await store.fetchone("SELECT status FROM comparison_groups WHERE group_id=?", ("grp-cancel",))
    assert row["status"] == "cancelled"
    statuses = [f.payload.get("status") for f in uplink.of_type("comparison.group_ready")]
    assert statuses[-1] == "cancelled"        # never clobbered back to ready_for_review


@pytest.mark.asyncio
async def test_run_group_non_api_agent_closes(store, uplink, monkeypatch):
    import time

    await store.execute(
        "INSERT INTO agents (id, name, type, platform, version, manifest, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        ("agt_cli", "Cli", "cli", "any", 1,
         '[agent]\nid = "agt_cli"\nname = "Cli"\ntype = "cli"\nversion = 1\n', time.time()),
    )
    await run_group(
        group_id="grp-cli", agent_id="agt_cli", daemon_id="d",
        models=["gpt-5"], input={"prompt": "x"},
    )
    ready = uplink.of_type("comparison.group_ready")
    assert ready and ready[-1].payload["status"] == "closed"
    assert uplink.of_type("comparison.variant_finished") == []


# ── 5. command handlers ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_handle_compare_launches_group(store, monkeypatch):
    import synapse_worker.commands.comparison as cmd
    from synapse_worker.router import CommandContext

    captured = {}

    async def fake_run_group(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cmd, "run_group", fake_run_group)

    await cmd.handle_compare(
        CommandContext(command_type="agent.compare", daemon_id="dmn-9"),
        {"group_id": "g1", "agent_id": "a1", "models": ["gpt-5", "claude-opus-4-8"],
         "input": {"prompt": "p"}, "group_cost_cap": 1.5, "max_parallel_variants": 2},
    )
    # the launcher schedules a background task; let it run
    task = cmd._launches.get("g1")
    assert task is not None
    await task

    assert captured["group_id"] == "g1"
    assert captured["agent_id"] == "a1"
    assert captured["models"] == ["gpt-5", "claude-opus-4-8"]
    assert captured["group_cost_cap"] == 1.5
    assert captured["max_parallel_variants"] == 2


@pytest.mark.asyncio
async def test_handle_compare_ignores_bad_payload(store, monkeypatch):
    import synapse_worker.commands.comparison as cmd
    from synapse_worker.router import CommandContext

    called = {"n": 0}

    async def fake_run_group(**kwargs):
        called["n"] += 1

    monkeypatch.setattr(cmd, "run_group", fake_run_group)
    await cmd.handle_compare(
        CommandContext(command_type="agent.compare", daemon_id="d"),
        {"group_id": "g", "agent_id": "a", "models": []},   # empty models -> ignored
    )
    await asyncio.sleep(0)
    assert called["n"] == 0
