"""Plugin Runtime & Capability Packs unit tests (§4.11) — self-contained.

NO network, NO real venv builds, NO real downloads: the heavy provisioning step
(``PluginRuntime._provision`` → venv create + dep install + post_install) is monkeypatched
to a no-op, so we exercise the full status/registry/table flow without side effects.

Coverage:
  * ``plugin.install`` / ``mcp.configure`` write a ``capabilities`` row, mark the registry
    available, and emit a ``capability.status`` (ready) frame upstream.
  * a checksum mismatch fails provisioning (status=failed).
  * ``plugin.remove`` tears down + removes the registry/table rows.
  * ``capability.attach`` / ``capability.detach`` toggle ``is_attached`` + the
    ``agent_capabilities`` table; a default stays attached, a non-default attaches only
    after attach.
  * the CLI: ``plugin install <path>`` (local plugin.toml) → ``plugin list`` shows it;
    ``agent attach/capabilities``.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from typer.testing import CliRunner

from synapse_worker.capabilities.registry import (
    DEFAULT_CAPABILITIES,
    get_capability_registry,
)
from synapse_worker.plugins.base import PluginManifest, get_plugin_registry
from synapse_worker.plugins.runtime import (
    McpServerSpec,
    PluginRuntime,
    get_plugin_runtime,
    reset_plugin_runtime,
    verify_checksum,
)
from synapse_worker.router import CommandContext, dispatch, known_commands

# Importing the command module registers the @on_command handlers under test.
import synapse_worker.commands.plugins as plugins_cmd  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_runtime():
    """Each test gets a clean PluginRuntime singleton + re-registered handlers.

    conftest's autouse ``_isolate`` calls ``clear_handlers()`` around every test, so we
    reload the command module to re-run its ``@on_command`` registrations (same pattern as
    the other command-unit tests).
    """
    import importlib

    reset_plugin_runtime()
    importlib.reload(plugins_cmd)
    yield
    reset_plugin_runtime()


@pytest.fixture
def no_real_provision(monkeypatch):
    """Stub the heavy venv/dep/post_install step so nothing is built or downloaded."""
    calls: list[str] = []

    async def _fake_provision(self, *, name, manifest):
        calls.append(name)

    monkeypatch.setattr(PluginRuntime, "_provision", _fake_provision)
    return calls


def _ctx(command_type: str, key: str | None = None) -> CommandContext:
    return CommandContext(command_type=command_type, idempotency_key=key)


# ── checksum gate ─────────────────────────────────────────────────────────────
def test_verify_checksum_matches_and_mismatches():
    import hashlib

    data = b"plugin-artifact"
    digest = hashlib.sha256(data).hexdigest()
    assert verify_checksum(data, digest) is True
    assert verify_checksum(data, f"sha256:{digest}") is True
    assert verify_checksum(data, "deadbeef") is False
    # Absent checksum is treated as "nothing to verify" → ok.
    assert verify_checksum(data, "") is True


# ── handlers registered ───────────────────────────────────────────────────────
def test_handlers_registered():
    for cmd in (
        "plugin.install",
        "mcp.configure",
        "plugin.remove",
        "capability.attach",
        "capability.detach",
    ):
        assert cmd in known_commands()


# ── plugin.install (script/composite) ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_plugin_install_provisions_and_reports(store, uplink, no_real_provision):
    payload = {
        "daemon_capability_id": "cap_abc",
        "kind": "script",
        "plugin_id": "file-explorer",
        "plugin_version": "1.0.0",
        "exposed_tools": ["browse", "read"],
        "args": {"deps": ["rich"]},
    }
    await dispatch("plugin.install", _ctx("plugin.install"), payload)

    # capabilities row written, status ready.
    row = await store.fetchone("SELECT * FROM capabilities WHERE id=?", ("cap_abc",))
    assert row is not None
    assert row["status"] == "ready"
    assert row["kind"] == "script"
    assert row["name"] == "file-explorer"

    # heavy provisioning actually invoked (our stub recorded it).
    assert no_real_provision == ["file-explorer"]

    # registry marks it available + ready.
    cap = get_capability_registry().get("file-explorer")
    assert cap is not None and cap.status == "ready"
    assert get_plugin_registry().get("file-explorer").status == "ready"

    # capability.status (ready) emitted upstream on the control channel.
    statuses = uplink.of_type("capability.status")
    assert statuses, "expected a capability.status frame"
    final = statuses[-1]
    assert final.payload["daemon_capability_id"] == "cap_abc"
    assert final.payload["status"] == "ready"
    assert set(final.payload["exposed_tools"]) == {"browse", "read"}


@pytest.mark.asyncio
async def test_mcp_configure_registers_spec(store, uplink, no_real_provision):
    payload = {
        "daemon_capability_id": "cap_mcp",
        "kind": "mcp",
        "plugin_id": "github",
        "exposed_tools": ["create_issue"],
        "endpoint": "python -m github_mcp",
        "args": {},
    }
    await dispatch("mcp.configure", _ctx("mcp.configure"), payload)

    row = await store.fetchone("SELECT * FROM capabilities WHERE id=?", ("cap_mcp",))
    assert row is not None and row["status"] == "ready" and row["kind"] == "mcp"

    # mcp kind does NOT build a venv.
    assert no_real_provision == []

    # a spawnable spec was recorded for later start().
    spec = get_plugin_runtime().spec_for("cap_mcp")
    assert isinstance(spec, McpServerSpec)
    assert spec.argv()[:3] == ["python", "-m", "github_mcp"]


@pytest.mark.asyncio
async def test_plugin_install_checksum_mismatch_fails(store, uplink, no_real_provision):
    payload = {
        "daemon_capability_id": "cap_bad",
        "kind": "script",
        "plugin_id": "evil",
        "checksum": "sha256:deadbeef",
        "args": {"manifest": {"plugin": {"name": "evil", "kind": "script"}}},
    }
    # The handler doesn't carry artifact bytes, so a checksum alone won't fail; drive the
    # runtime directly with mismatching data to exercise the integrity gate.
    manifest = PluginManifest.from_dict({"plugin": {"name": "evil", "kind": "script"}})
    result = await get_plugin_runtime().install(
        daemon_capability_id="cap_bad",
        kind="script",
        manifest=manifest,
        exposed_tools=[],
        checksum="sha256:deadbeef",
        checksum_data=b"tampered",
    )
    assert result.status == "failed"
    assert "checksum" in (result.error or "")
    row = await store.fetchone("SELECT status FROM capabilities WHERE id=?", ("cap_bad",))
    assert row["status"] == "failed"
    # provisioning was never invoked because the gate failed first.
    assert no_real_provision == []


@pytest.mark.asyncio
async def test_unsupported_platform_fails(store, no_real_provision):
    manifest = PluginManifest.from_dict(
        {"plugin": {"name": "winonly", "kind": "script", "platforms": ["windows"]}}
    )
    result = await get_plugin_runtime().install(
        daemon_capability_id="cap_plat",
        kind="script",
        manifest=manifest,
        exposed_tools=[],
        platform="linux",
    )
    assert result.status == "failed"
    assert "platform" in (result.error or "")


# ── plugin.remove ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_plugin_remove_tears_down(store, uplink, no_real_provision):
    await dispatch(
        "plugin.install",
        _ctx("plugin.install"),
        {"daemon_capability_id": "cap_rm", "kind": "script", "plugin_id": "doomed"},
    )
    assert get_capability_registry().is_available("doomed")

    # attach to an agent so we can confirm remove detaches it.
    await store.execute(
        "INSERT INTO agent_capabilities (agent_id, capability, enabled, updated_at)"
        " VALUES (?,?,1,?)",
        ("agt_1", "doomed", 0.0),
    )

    await dispatch("plugin.remove", _ctx("plugin.remove"), {"daemon_capability_id": "cap_rm"})

    assert await store.fetchone("SELECT id FROM capabilities WHERE id=?", ("cap_rm",)) is None
    assert not get_capability_registry().is_available("doomed")
    assert get_plugin_registry().get("doomed") is None
    rows = await store.fetchall(
        "SELECT * FROM agent_capabilities WHERE capability=?", ("doomed",)
    )
    assert rows == []


# ── capability.attach / detach ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_attach_and_detach_toggle(store, no_real_provision):
    # Provision a non-default capability first.
    await dispatch(
        "plugin.install",
        _ctx("plugin.install"),
        {"daemon_capability_id": "cap_at", "kind": "mcp", "plugin_id": "slack",
         "endpoint": "python -m slack_mcp"},
    )
    reg = get_capability_registry()

    # A default stays attached out of the box; the non-default is not yet attached.
    assert reg.is_attached("agt_x", DEFAULT_CAPABILITIES[0])
    assert not reg.is_attached("agt_x", "slack")

    # Attach (agent_id from payload).
    await dispatch(
        "capability.attach",
        _ctx("capability.attach"),
        {"agent_id": "agt_x", "daemon_capability_id": "cap_at"},
    )
    assert reg.is_attached("agt_x", "slack")
    row = await store.fetchone(
        "SELECT enabled FROM agent_capabilities WHERE agent_id=? AND capability=?",
        ("agt_x", "slack"),
    )
    assert row is not None and row["enabled"] == 1

    # Detach.
    await dispatch(
        "capability.detach",
        _ctx("capability.detach"),
        {"agent_id": "agt_x", "daemon_capability_id": "cap_at"},
    )
    assert not reg.is_attached("agt_x", "slack")
    assert await store.fetchone(
        "SELECT 1 FROM agent_capabilities WHERE agent_id=? AND capability=?",
        ("agt_x", "slack"),
    ) is None
    # A default remains attached after the non-default churn.
    assert reg.is_attached("agt_x", DEFAULT_CAPABILITIES[0])


@pytest.mark.asyncio
async def test_attach_applies_permissions_per_agent(store, no_real_provision):
    """A pack's declared permissions land on the TARGET agent only, never the global default."""
    from synapse_worker.ruleset import base as ruleset_base
    from synapse_worker.ruleset.engine import RulesetEngine

    engine = RulesetEngine()
    ruleset_base.set_ruleset(engine)

    # Provision a pack whose manifest declares a network allow-list.
    await dispatch(
        "plugin.install",
        _ctx("plugin.install"),
        {
            "daemon_capability_id": "cap_perm",
            "kind": "mcp",
            "plugin_id": "scoped",
            "endpoint": "python -m scoped",
            "args": {"permissions": {"network": ["api.github.com"]}},
        },
    )

    # Before attach, the off-list host is unrestricted for an UNRELATED agent.
    assert engine.check_network("evil.example.com", agent_id="other").allowed

    await dispatch(
        "capability.attach",
        _ctx("capability.attach"),
        {"agent_id": "agt_p", "daemon_capability_id": "cap_perm"},
    )

    # The attached agent now has the allow-list (off-list host blocked)...
    assert not engine.check_network("evil.example.com", agent_id="agt_p").allowed
    assert engine.check_network("api.github.com", agent_id="agt_p").allowed
    # ...but an unrelated agent's policy is untouched (no global clobber).
    assert engine.check_network("evil.example.com", agent_id="other").allowed


@pytest.mark.asyncio
async def test_attach_agent_id_from_idempotency_key(store, no_real_provision):
    await dispatch(
        "plugin.install",
        _ctx("plugin.install"),
        {"daemon_capability_id": "cap_k", "kind": "mcp", "plugin_id": "pg",
         "endpoint": "python -m pg_mcp"},
    )
    # No agent_id in the payload — it must be parsed from the idempotency key.
    await dispatch(
        "capability.attach",
        _ctx("capability.attach", key="capability.attach:agt_key:cap_k"),
        {"daemon_capability_id": "cap_k"},
    )
    assert get_capability_registry().is_attached("agt_key", "pg")


# ── MCP process management ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_mcp_process_start_stop(store, no_real_provision):
    """Spawn a trivial python process as the 'MCP server', confirm lifecycle control."""
    import sys

    rt = get_plugin_runtime()
    # Pass the exact argv via args.args (avoids shell-splitting a Windows path with
    # spaces); the command is the bare interpreter, the rest is explicit argv.
    await dispatch(
        "mcp.configure",
        _ctx("mcp.configure"),
        {"daemon_capability_id": "cap_proc", "kind": "mcp", "plugin_id": "sleeper",
         "args": {"args": [sys.executable, "-c", "import time; time.sleep(30)"]}},
    )
    proc = await rt.start_mcp("cap_proc")
    assert proc is not None and proc.is_running()
    assert proc.pid is not None
    await rt.stop_mcp("cap_proc")
    assert not proc.is_running()


# ── CLI ───────────────────────────────────────────────────────────────────────
@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_app():
    """A fresh root Typer app with our two CLI modules mounted."""
    import typer
    from synapse_worker.cli import cmd_agent, cmd_plugin

    app = typer.Typer()
    cmd_plugin.register(app)
    cmd_agent.register(app)
    return app


@pytest.fixture
def local_plugin(tmp_path):
    """Write a local plugin.toml fixture and return its dir."""
    d = tmp_path / "my-plugin"
    d.mkdir()
    (d / "plugin.toml").write_text(
        "\n".join(
            [
                "[plugin]",
                'id = "plg_local"',
                'name = "my-plugin"',
                'version = "0.1.0"',
                'kind = "script"',
                "",
                "[[provides.tool]]",
                'name = "lint"',
                'exec = "scripts/lint.py"',
            ]
        ),
        encoding="utf-8",
    )
    return d


def test_cli_plugin_search(runner, cli_app):
    result = runner.invoke(cli_app, ["plugin", "search", "browser"])
    assert result.exit_code == 0
    assert "browser-use" in result.stdout


def test_cli_plugin_install_then_list(runner, cli_app, local_plugin, monkeypatch, settings):
    # Stub the heavy provisioning so the local-path install doesn't build a venv.
    async def _fake_provision(self, *, name, manifest):
        return None

    monkeypatch.setattr(PluginRuntime, "_provision", _fake_provision)

    res_install = runner.invoke(cli_app, ["plugin", "install", str(local_plugin)])
    assert res_install.exit_code == 0, res_install.stdout
    assert "my-plugin" in res_install.stdout

    res_list = runner.invoke(cli_app, ["plugin", "list"])
    assert res_list.exit_code == 0
    assert "my-plugin" in res_list.stdout
    assert "ready" in res_list.stdout


def test_cli_agent_attach_and_capabilities(runner, cli_app, local_plugin, monkeypatch, settings):
    async def _fake_provision(self, *, name, manifest):
        return None

    monkeypatch.setattr(PluginRuntime, "_provision", _fake_provision)

    runner.invoke(cli_app, ["plugin", "install", str(local_plugin)])

    res_attach = runner.invoke(
        cli_app, ["agent", "attach", "my-plugin", "--agent", "web-bot"]
    )
    assert res_attach.exit_code == 0, res_attach.stdout

    res_caps = runner.invoke(cli_app, ["agent", "capabilities", "--agent", "web-bot"])
    assert res_caps.exit_code == 0
    assert "my-plugin" in res_caps.stdout
    # Defaults show up too (auto-attached).
    assert DEFAULT_CAPABILITIES[0] in res_caps.stdout


def test_cli_agent_attach_unprovisioned_fails(runner, cli_app, settings):
    res = runner.invoke(cli_app, ["agent", "attach", "ghost", "--agent", "web-bot"])
    assert res.exit_code == 1
