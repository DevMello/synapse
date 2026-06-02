"""Agent Runtime + API Adapter tests (§4.3) — no network, no real keys.

Strategy: monkeypatch ``ApiAdapter._post`` (the single HTTP choke point) to return a
canned provider body, so the whole engine path runs offline. We assert the durable
``run_history`` lifecycle, redacted ``telemetry.trace`` frames, and the ``run.finished``
control frame the cloud reads.
"""
from __future__ import annotations

import asyncio

import pytest

from synapse_worker.router import CommandContext
from synapse_worker.runtime.api_adapter import ApiAdapter
from synapse_worker.runtime.base import (
    AgentManifest,
    RunResult,
    Usage,
    has_adapter,
    register_adapter,
    set_price_table,
)
from synapse_worker.runtime.engine import RunEngine, render_template


def _manifest(agent_id="agt_1", type_="api", **limits) -> AgentManifest:
    return AgentManifest.from_dict(
        {
            "agent": {"id": agent_id, "name": "bot", "type": type_, "version": 1},
            "api": {"provider": "anthropic", "model": "claude-x"},
            "limits": limits,
        }
    )


# ── template rendering ──────────────────────────────────────────────────────
def test_render_template_substitutes_and_keeps_unknown():
    out = render_template("Hi {{name}}, ticket {{id}} {{missing}}", {"name": "Sam", "id": 7})
    assert out == "Hi Sam, ticket 7 {{missing}}"


# ── engine happy path via a fake adapter ────────────────────────────────────
async def test_run_agent_succeeds_and_persists(store, uplink):
    async def fake_run(ctx):
        await ctx.trace("prompt", role="user", content="hello")
        await ctx.trace("completion", role="assistant", content="world")
        return RunResult(status="success", usage=Usage(input_tokens=5, output_tokens=3,
                                                        cost_usd=0.02), output="world")

    register_adapter("fake", lambda: type("A", (), {"run": staticmethod(fake_run)})())

    engine = RunEngine()
    m = _manifest(type_="fake")
    result = await engine.run_agent(manifest=m, run_id="rn_1", prompt_vars={"prompt": "hi"})

    assert result.status == "success"

    row = await store.fetchone("SELECT * FROM run_history WHERE run_id=?", ("rn_1",))
    assert row["status"] == "succeeded"  # wire vocabulary
    assert row["cost_usd"] == 0.02
    assert row["tokens_input"] == 5 and row["tokens_output"] == 3
    assert row["started_at"] is not None and row["finished_at"] is not None

    # Two content traces -> two redacted telemetry frames.
    traces = uplink.of_type("telemetry.trace")
    assert len(traces) == 2
    assert traces[0].channel == "telemetry"
    assert traces[0].payload["content_redacted"] == "hello"
    assert traces[0].payload["run_id"] == "rn_1"

    finished = uplink.of_type("run.finished")
    assert len(finished) == 1
    f = finished[0].payload
    assert f["status"] == "succeeded"
    assert f["cost_usd"] == 0.02
    assert f["tokens_in"] == 5 and f["tokens_out"] == 3
    assert finished[0].channel == "control"


async def test_run_agent_no_adapter_fails_gracefully(store, uplink):
    engine = RunEngine()
    m = _manifest(type_="does-not-exist")
    result = await engine.run_agent(manifest=m, run_id="rn_x", prompt_vars={})
    assert result.status == "failed"
    row = await store.fetchone("SELECT status FROM run_history WHERE run_id=?", ("rn_x",))
    assert row["status"] == "failed"
    assert uplink.of_type("run.finished")[0].payload["status"] == "failed"


async def test_run_agent_adapter_raises_is_failed(store, uplink):
    async def boom(ctx):
        raise RuntimeError("kaboom")

    register_adapter("boom", lambda: type("A", (), {"run": staticmethod(boom)})())
    engine = RunEngine()
    result = await engine.run_agent(manifest=_manifest(type_="boom"), run_id="rn_b",
                                    prompt_vars={})
    assert result.status == "failed"
    assert "kaboom" in (result.error or "")
    assert uplink.of_type("run.finished")[0].payload["status"] == "failed"


async def test_run_agent_cost_cap_flips_to_failed(store, uplink):
    async def pricey(ctx):
        return RunResult(status="success", usage=Usage(cost_usd=5.0), output="x")

    register_adapter("pricey", lambda: type("A", (), {"run": staticmethod(pricey)})())
    engine = RunEngine()
    m = _manifest(type_="pricey", max_cost_usd=1.0)
    result = await engine.run_agent(manifest=m, run_id="rn_c", prompt_vars={})
    assert result.status == "failed"
    assert "exceeded cap" in (result.error or "")


# ── API adapter: monkeypatched HTTP, anthropic shape ────────────────────────
async def test_api_adapter_anthropic_normalizes_and_prices(store, uplink, monkeypatch):
    captured = {}

    async def fake_post(self, url, *, headers, json):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        return {
            "content": [{"type": "text", "text": "the answer"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }

    monkeypatch.setattr(ApiAdapter, "_post", fake_post)
    set_price_table({"claude-x": {"input": 3.0, "output": 15.0}})
    try:
        engine = RunEngine()
        m = _manifest(type_="api")
        result = await engine.run_agent(
            manifest=m, run_id="rn_api", prompt_vars={"prompt": "q"},
            env={"ANTHROPIC_API_KEY": "sk-secret"},
        )
    finally:
        set_price_table({})

    assert result.status == "success"
    assert result.output == "the answer"
    # cost = (100*3 + 50*15) / 1e6 = 0.00105
    assert result.usage.cost_usd == pytest.approx(0.00105)
    assert result.usage.estimated is False
    # Key was sent in the header (read from env), and the messages endpoint was used.
    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["x-api-key"] == "sk-secret"

    row = await store.fetchone("SELECT status FROM run_history WHERE run_id=?", ("rn_api",))
    assert row["status"] == "succeeded"


async def test_api_adapter_unknown_model_is_estimated(monkeypatch):
    async def fake_post(self, url, *, headers, json):
        return {"content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 10, "output_tokens": 2}}

    monkeypatch.setattr(ApiAdapter, "_post", fake_post)
    # No price table entry -> estimated, cost 0.
    from synapse_worker.runtime.base import RunContext

    ctx = RunContext(run_id="r", agent_id="a", manifest=_manifest())
    result = await ApiAdapter().run(ctx)
    assert result.usage.estimated is True
    assert result.usage.cost_usd == 0.0


async def test_api_adapter_post_failure_is_failed(monkeypatch):
    async def boom(self, url, *, headers, json):
        raise RuntimeError("502 bad gateway")

    monkeypatch.setattr(ApiAdapter, "_post", boom)
    from synapse_worker.runtime.base import RunContext

    ctx = RunContext(run_id="r", agent_id="a", manifest=_manifest())
    result = await ApiAdapter().run(ctx)
    assert result.status == "failed"
    assert "502" in (result.error or "")


async def test_api_adapter_openai_shape(monkeypatch):
    async def fake_post(self, url, *, headers, json):
        return {
            "choices": [{"message": {"role": "assistant", "content": "openai says hi"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4},
        }

    monkeypatch.setattr(ApiAdapter, "_post", fake_post)
    from synapse_worker.runtime.base import RunContext

    m = AgentManifest.from_dict(
        {"agent": {"id": "a", "type": "api"},
         "api": {"provider": "openai", "model": "gpt-x"}}
    )
    ctx = RunContext(run_id="r", agent_id="a", manifest=m, env={"OPENAI_API_KEY": "sk-x"})
    result = await ApiAdapter().run(ctx)
    assert result.output == "openai says hi"
    assert result.usage.input_tokens == 7 and result.usage.output_tokens == 4


def test_api_adapter_registered_at_import():
    assert has_adapter("api")


# ── command handlers ────────────────────────────────────────────────────────
async def test_deploy_writes_manifest_and_upserts(store, settings):
    import synapse_worker.commands.agents as agents

    payload = {
        "agent": {"id": "agt_d", "name": "deployed", "type": "api", "version": 2},
        "api": {"provider": "anthropic", "model": "claude-x"},
        "prompt": "You are {{role}}.",
    }
    await agents.handle_deploy(CommandContext(command_type="agent.deploy"), payload)

    from synapse_worker.paths import paths_for

    agent_dir = paths_for(settings).agent_dir("agt_d")
    assert (agent_dir / "agent.toml").exists()
    assert (agent_dir / "prompt.md").read_text(encoding="utf-8") == "You are {{role}}."
    assert (agent_dir / "prompt.v2.md").exists()

    row = await store.fetchone("SELECT * FROM agents WHERE id=?", ("agt_d",))
    assert row["name"] == "deployed" and row["version"] == 2
    # The synthesized manifest must be loadable.
    m = AgentManifest.from_toml(row["manifest"])
    assert m.id == "agt_d" and m.api["provider"] == "anthropic"


async def test_run_handler_triggers_engine(store, uplink, settings, monkeypatch):
    import synapse_worker.commands.agents as agents

    # Deploy first so the manifest exists on disk.
    await agents.handle_deploy(
        CommandContext(command_type="agent.deploy"),
        {"agent": {"id": "agt_r", "type": "api", "version": 1},
         "api": {"provider": "anthropic", "model": "claude-x"},
         "prompt": "hi"},
    )

    async def fake_post(self, url, *, headers, json):
        return {"content": [{"type": "text", "text": "ran"}],
                "usage": {"input_tokens": 1, "output_tokens": 1}}

    monkeypatch.setattr(ApiAdapter, "_post", fake_post)

    await agents.handle_run(
        CommandContext(command_type="agent.run"),
        {"run_id": "rn_run", "agent_id": "agt_r", "prompt_vars": {}},
    )
    # The run is a background task — await it.
    task = agents._running.get("rn_run")
    assert task is not None
    await task

    row = await store.fetchone("SELECT status FROM run_history WHERE run_id=?", ("rn_run",))
    assert row["status"] == "succeeded"


async def test_run_handler_missing_agent_reports_failed(store, uplink):
    import synapse_worker.commands.agents as agents

    await agents.handle_run(
        CommandContext(command_type="agent.run"),
        {"run_id": "rn_missing", "agent_id": "nope"},
    )
    finished = uplink.of_type("run.finished")
    assert finished and finished[0].payload["status"] == "failed"


async def test_cancel_handler_cancels_running_task(store, uplink):
    import synapse_worker.commands.agents as agents

    started = asyncio.Event()

    async def never(ctx):
        started.set()
        await asyncio.sleep(60)

    from synapse_worker.runtime.base import register_adapter as reg

    reg("slow", lambda: type("A", (), {"run": staticmethod(never)})())

    # Deploy a slow agent and start it.
    m = _manifest(agent_id="agt_s", type_="slow")
    task = asyncio.create_task(
        agents._engine.run_agent(manifest=m, run_id="rn_cancel", prompt_vars={})
    )
    agents._running["rn_cancel"] = task
    await started.wait()

    await agents.handle_cancel(
        CommandContext(command_type="agent.cancel"), {"run_id": "rn_cancel"}
    )
    assert task.cancelled() or task.done()

    row = await store.fetchone("SELECT status FROM run_history WHERE run_id=?",
                               ("rn_cancel",))
    assert row["status"] == "cancelled"
    assert uplink.of_type("run.finished")[0].payload["status"] == "cancelled"


async def test_update_prompt_bumps_version(store, settings):
    import synapse_worker.commands.agents as agents

    await agents.handle_deploy(
        CommandContext(command_type="agent.deploy"),
        {"agent": {"id": "agt_u", "type": "api", "version": 1}, "prompt": "v1"},
    )
    await agents.handle_update_prompt(
        CommandContext(command_type="agent.update_prompt"),
        {"agent_id": "agt_u", "version": 5, "prompt": "v5 prompt"},
    )

    from synapse_worker.paths import paths_for

    agent_dir = paths_for(settings).agent_dir("agt_u")
    assert (agent_dir / "prompt.md").read_text(encoding="utf-8") == "v5 prompt"
    assert (agent_dir / "prompt.v5.md").exists()
    row = await store.fetchone("SELECT version FROM agents WHERE id=?", ("agt_u",))
    assert row["version"] == 5
