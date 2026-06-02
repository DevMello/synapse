"""CLI adapter + ccusage unit tests (§4.3).

Fully self-contained and cross-platform: every subprocess is the *test interpreter itself*
(``sys.executable -c ...``), so there's no dependency on claude/aider/ccusage being
installed, and no network. We drive :class:`CliAdapter` directly with a hand-built
:class:`RunContext` whose ``emit`` collects trace events.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

from synapse_worker.runtime import ccusage
from synapse_worker.runtime.base import (
    AgentManifest,
    RunContext,
    TraceEvent,
    Usage,
    get_adapter,
    has_adapter,
)
from synapse_worker.runtime.cli_adapter import CliAdapter

# Only the subprocess-driving tests are async; the ccusage/registration tests are sync, so
# we mark each async test individually rather than module-wide (avoids asyncio-on-sync
# warnings).
asyncio_test = pytest.mark.asyncio


def _manifest(cli: dict, limits: dict | None = None) -> AgentManifest:
    return AgentManifest.from_dict(
        {
            "agent": {"id": "agt_1", "type": "cli", "name": "test-cli"},
            "cli": cli,
            "limits": limits or {},
        }
    )


def _ctx(manifest: AgentManifest, *, prompt_vars=None, env=None):
    """Build a RunContext whose emit appends every TraceEvent to a returned list."""
    events: list[TraceEvent] = []

    async def emit(ev: TraceEvent) -> None:
        events.append(ev)

    ctx = RunContext(
        run_id="run_1",
        agent_id="agt_1",
        manifest=manifest,
        prompt_vars=prompt_vars or {},
        env=env or {},
        emit=emit,
    )
    return ctx, events


def _lines(events, stream: str) -> list[str]:
    return [e.data["content"] for e in events if e.data.get("stream") == stream]


# ── adapter: basic run ──────────────────────────────────────────────────────
@asyncio_test
async def test_run_streams_stdout_stderr_and_succeeds():
    manifest = _manifest(
        {
            "command": sys.executable,
            "args": [
                "-c",
                "import sys; print('hello'); print('warn', file=sys.stderr); sys.exit(0)",
            ],
        }
    )
    ctx, events = _ctx(manifest)
    result = await CliAdapter().run(ctx)

    assert result.status == "succeeded"
    assert result.error is None
    assert "hello" in _lines(events, "stdout")
    assert "warn" in _lines(events, "stderr")
    # stdout streams as tool_result, stderr as log.
    kinds = {(e.kind, e.data.get("stream")) for e in events}
    assert ("tool_result", "stdout") in kinds
    assert ("log", "stderr") in kinds


@asyncio_test
async def test_nonzero_exit_is_failed():
    manifest = _manifest(
        {
            "command": sys.executable,
            "args": ["-c", "import sys; print('boom', file=sys.stderr); sys.exit(3)"],
        }
    )
    ctx, events = _ctx(manifest)
    result = await CliAdapter().run(ctx)

    assert result.status == "failed"
    assert "exit code 3" in result.error
    assert "boom" in result.error  # last stderr line appended


@asyncio_test
async def test_missing_command_fails_cleanly():
    manifest = _manifest({"args": ["-c", "pass"]})
    ctx, _ = _ctx(manifest)
    result = await CliAdapter().run(ctx)
    assert result.status == "failed"
    assert "command" in result.error.lower()


# ── adapter: placeholder rendering ──────────────────────────────────────────
@asyncio_test
async def test_prompt_var_placeholders_render():
    manifest = _manifest(
        {
            "command": sys.executable,
            "args": ["-c", "import sys; print(sys.argv[1])", "{{prompt}}"],
        }
    )
    ctx, events = _ctx(manifest, prompt_vars={"prompt": "rendered-value"})
    result = await CliAdapter().run(ctx)
    assert result.status == "succeeded"
    assert "rendered-value" in _lines(events, "stdout")


# ── adapter: JSON output parsing ────────────────────────────────────────────
@asyncio_test
async def test_json_output_parsed_when_format_flag_present():
    manifest = _manifest(
        {
            "command": sys.executable,
            "args": [
                "-c",
                "import json; print(json.dumps({'ok': 1}))",
                "--output-format",
                "json",
            ],
        }
    )
    ctx, _ = _ctx(manifest)
    result = await CliAdapter().run(ctx)
    assert result.status == "succeeded"
    # Raw text preserved as output; it must be valid JSON.
    assert json.loads(result.output) == {"ok": 1}


@asyncio_test
async def test_json_autoparsed_when_stdout_is_json():
    manifest = _manifest(
        {
            "command": sys.executable,
            "args": ["-c", "import json; print(json.dumps({'ok': 1}))"],
        }
    )
    ctx, _ = _ctx(manifest)
    result = await CliAdapter().run(ctx)
    assert result.status == "succeeded"
    assert json.loads(result.output) == {"ok": 1}


@asyncio_test
async def test_line_longer_than_stream_buffer_is_handled():
    # A single line bigger than asyncio's 64 KiB StreamReader limit (realistic for an
    # agent printing a large --output-format json blob on one line) must not crash the
    # adapter; readline() would otherwise raise LimitOverrunError.
    size = 200_000
    manifest = _manifest(
        {
            "command": sys.executable,
            "args": ["-c", f"print('x' * {size})"],
        }
    )
    ctx, events = _ctx(manifest)
    result = await CliAdapter().run(ctx)
    assert result.status == "succeeded"
    # The full oversized line is captured (no data loss, stitched across reads).
    assert len(result.output) == size
    assert set(result.output) == {"x"}


@asyncio_test
async def test_cli_json_usage_block_is_exact():
    blob = {
        "result": "done",
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "cost_usd": 0.0123,
    }
    manifest = _manifest(
        {
            "command": sys.executable,
            "args": [
                "-c",
                f"print({json.dumps(json.dumps(blob))})",
                "--output-format",
                "json",
            ],
        }
    )
    ctx, _ = _ctx(manifest)
    result = await CliAdapter().run(ctx)
    assert result.status == "succeeded"
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 50
    assert result.usage.cost_usd == pytest.approx(0.0123)
    assert result.usage.estimated is False


# ── adapter: timeout ────────────────────────────────────────────────────────
@asyncio_test
async def test_timeout_kills_process_and_fails():
    manifest = _manifest(
        {"command": sys.executable, "args": ["-c", "import time; time.sleep(5)"]},
        limits={"timeout_sec": 1},
    )
    ctx, events = _ctx(manifest)
    result = await CliAdapter().run(ctx)

    assert result.status == "failed"
    assert "timeout" in result.error.lower()
    # An error trace with the timeout reason was emitted.
    assert any(
        e.kind == "error" and e.data.get("reason") == "timeout" for e in events
    )


# ── adapter: env scrubbing ──────────────────────────────────────────────────
@asyncio_test
async def test_env_scrubbing_injects_and_drops(monkeypatch):
    # A secret that must NOT leak to the child (non-whitelisted parent var).
    monkeypatch.setenv("DAEMON_SECRET_TOKEN", "super-secret")
    manifest = _manifest(
        {
            "command": sys.executable,
            "args": [
                "-c",
                "import os, json; print(json.dumps(dict(os.environ)))",
            ],
        }
    )
    ctx, _ = _ctx(manifest, env={"INJECTED_KEY": "injected-value"})
    result = await CliAdapter().run(ctx)

    assert result.status == "succeeded"
    child_env = json.loads(result.output)
    # Injected var reaches the child.
    assert child_env.get("INJECTED_KEY") == "injected-value"
    # Non-whitelisted daemon secret is absent.
    assert "DAEMON_SECRET_TOKEN" not in child_env


# ── ccusage ─────────────────────────────────────────────────────────────────
def test_read_usage_estimated_when_ccusage_absent(monkeypatch):
    monkeypatch.setattr(ccusage.shutil, "which", lambda _name: None)
    usage = ccusage.read_usage("claude")
    assert isinstance(usage, Usage)
    assert usage.estimated is True
    assert usage.cost_usd == 0.0


def test_read_usage_estimated_for_unknown_tool(monkeypatch):
    # Even if ccusage existed, an uncovered tool degrades to estimated (no subprocess).
    called = {"which": False}

    def fake_which(_name):
        called["which"] = True
        return "/usr/bin/ccusage"

    monkeypatch.setattr(ccusage.shutil, "which", fake_which)
    usage = ccusage.read_usage("aider")
    assert usage.estimated is True
    assert called["which"] is False  # short-circuited before touching PATH


def test_read_usage_parses_ccusage_json(monkeypatch):
    monkeypatch.setattr(ccusage.shutil, "which", lambda _name: "/fake/ccusage")

    class _Proc:
        returncode = 0
        stdout = json.dumps(
            {
                "totals": {
                    "inputTokens": 1200,
                    "outputTokens": 300,
                    "cacheReadTokens": 10,
                    "totalCost": 0.42,
                }
            }
        )
        stderr = ""

    monkeypatch.setattr(ccusage.subprocess, "run", lambda *a, **k: _Proc())
    usage = ccusage.read_usage("claude")
    assert usage.input_tokens == 1200
    assert usage.output_tokens == 300
    assert usage.cache_read_tokens == 10
    assert usage.cost_usd == pytest.approx(0.42)
    # Cumulative daily totals -> still flagged estimated.
    assert usage.estimated is True


def test_read_usage_never_raises_on_bad_json(monkeypatch):
    monkeypatch.setattr(ccusage.shutil, "which", lambda _name: "/fake/ccusage")

    class _Proc:
        returncode = 0
        stdout = "not json at all"
        stderr = ""

    monkeypatch.setattr(ccusage.subprocess, "run", lambda *a, **k: _Proc())
    usage = ccusage.read_usage("claude")
    assert usage.estimated is True


def test_usage_from_cli_json_returns_none_without_usage():
    assert ccusage.usage_from_cli_json({"result": "ok"}) is None
    assert ccusage.usage_from_cli_json("plain text") is None


# ── registration ────────────────────────────────────────────────────────────
def test_cli_adapter_registered():
    assert has_adapter("cli")
    adapter = get_adapter("cli")
    assert isinstance(adapter, CliAdapter)
