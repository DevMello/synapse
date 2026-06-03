"""Unit #15 — service install (systemd / launchd / Windows Service, §2).

Self-contained: exercises the PURE generators (string/spec assertions) and the manager's
``dry_run`` path (which renders the would-be path + content without writing/registering or
spawning any process). The real ``synapse daemon run`` is never invoked (it blocks); we
only assert ``synapse daemon --help`` is wired.
"""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import pytest
from typer.testing import CliRunner

from synapse_worker.service import manager, units


# --- pure generators --------------------------------------------------------------


def test_systemd_unit_user_has_restart_and_install():
    unit = units.systemd_unit(exec_path="/usr/bin/synapse")
    assert "Restart=always" in unit
    assert "ExecStart=" in unit
    assert "[Unit]" in unit
    assert "[Service]" in unit
    assert "[Install]" in unit
    # user unit installs to the per-user target.
    assert "WantedBy=default.target" in unit
    # ExecStart points at the daemon entry.
    assert "/usr/bin/synapse daemon run" in unit


def test_systemd_unit_system_target():
    unit = units.systemd_unit(exec_path="/usr/bin/synapse", user=False)
    assert "WantedBy=multi-user.target" in unit


def test_systemd_unit_quotes_spaced_exec_path():
    unit = units.systemd_unit(exec_path="C:\\Program Files\\synapse.exe")
    assert 'ExecStart="C:\\Program Files\\synapse.exe" daemon run' in unit


def test_launchd_plist_is_wellformed_xml_with_keepalive_and_runatload():
    xml = units.launchd_plist(exec_path="/usr/local/bin/synapse")
    root = ElementTree.fromstring(xml)  # raises on malformed XML
    assert root.tag == "plist"
    keys = [e.text for e in root.iter("key")]
    assert "RunAtLoad" in keys
    assert "KeepAlive" in keys
    assert "ProgramArguments" in keys
    # the program args carry the daemon entry.
    strings = [e.text for e in root.iter("string")]
    assert "/usr/local/bin/synapse" in strings
    assert "daemon" in strings and "run" in strings
    assert units.LAUNCHD_LABEL in strings


def test_windows_service_spec_has_binpath_and_autostart():
    spec = units.windows_service_spec(exec_path="C:\\synapse\\synapse.exe")
    assert spec["start"] == "auto"
    assert spec["start_type"] == "auto"
    assert "daemon run" in spec["bin_path"]
    assert spec["name"] == units.SERVICE_NAME
    assert spec["restart_on_failure"] is True


def test_windows_service_spec_quotes_spaced_path():
    spec = units.windows_service_spec(exec_path="C:\\Program Files\\synapse.exe")
    assert spec["bin_path"].startswith('"C:\\Program Files\\synapse.exe"')


# --- platform detection -----------------------------------------------------------


def test_detect_platform_returns_valid_value():
    assert manager.detect_platform() in {"linux", "macos", "windows"}


def test_resolve_exec_returns_path_and_run_args():
    exec_path, args = manager.resolve_exec()
    assert exec_path  # non-empty launcher
    # the daemon run args are always appended (directly or via -m).
    assert args[-2:] == list(units.DAEMON_RUN_ARGS)


# --- dry-run manager (no host mutation) -------------------------------------------


def test_install_dry_run_returns_content_without_writing(settings, tmp_path):
    plan = manager.install(dry_run=True)
    assert plan.dry_run is True
    assert plan.wrote is False
    assert plan.ran is False
    assert plan.content  # rendered unit/spec text present
    assert plan.commands  # would-be registration commands present
    # nothing should have been written under the tmp home.
    home = Path(settings.home_dir)
    if home.exists():
        assert not list(home.rglob("*.service"))
        assert not list(home.rglob("*.plist"))


def test_install_dry_run_target_path_matches_platform(settings):
    plan = manager.install(dry_run=True)
    plat = manager.detect_platform()
    if plat == "linux":
        assert plan.target_path is not None
        assert plan.target_path.name == f"{units.SERVICE_NAME}.service"
    elif plat == "macos":
        assert plan.target_path is not None
        assert plan.target_path.name.endswith(".plist")
    else:  # windows: registered with SCM, no file path
        assert plan.target_path is None


def test_op_dry_run_does_not_spawn(settings):
    for plan in (
        manager.start(dry_run=True),
        manager.stop(dry_run=True),
        manager.status(dry_run=True),
    ):
        assert plan.dry_run is True
        assert plan.ran is False
        assert plan.commands  # would-be argv present


# --- CLI wiring -------------------------------------------------------------------


def test_daemon_help_exits_zero():
    from synapse_worker.cli.main import app

    result = CliRunner().invoke(app, ["daemon", "--help"])
    assert result.exit_code == 0
    assert "install" in result.output


def test_daemon_install_dry_run_via_cli(settings):
    from synapse_worker.cli.main import app

    result = CliRunner().invoke(app, ["daemon", "install", "--dry-run"])
    assert result.exit_code == 0
    assert "dry-run" in result.output
