"""Health emitter + self-update tests (§6, §5).

Self-contained, no network. Exercises:
  * the periodic health snapshot emitter (telemetry.metric frames),
  * the daemon.ping probe (snapshot + daemon.pong),
  * the self-update INTEGRITY GATE — a good checksum installs, a bad one never does,
  * the version/health CLI.
"""
from __future__ import annotations

import asyncio
import hashlib

import pytest

from synapse_worker import selfupdate
from synapse_worker.commands.daemon import (
    HealthService,
    collect_snapshot,
    emit_snapshot,
    handle_daemon_ping,
)
from synapse_worker.router import CommandContext, known_commands
from synapse_worker.selfupdate import UpdateRequest, UpdateRunner, apply_update, verify_checksum


# ── health snapshot ──────────────────────────────────────────────────────────
async def test_collect_snapshot_has_version(store):
    snap = await collect_snapshot()
    assert snap["version"]
    assert "cpu_percent" in snap and "mem_mb" in snap


async def test_emit_snapshot_sends_telemetry_metrics(store, uplink):
    payload = await emit_snapshot()
    metrics = uplink.of_type("telemetry.metric")
    assert metrics, "expected at least one telemetry.metric frame"
    # All health telemetry rides the telemetry channel (never control).
    assert all(f.channel == "telemetry" for f in metrics)
    # Every metric value is NUMERIC — the cloud's metrics.value is double precision, so a
    # dict-valued metric would be rejected (the bug a live-cloud run caught).
    assert all(isinstance(f.payload.get("value"), (int, float)) for f in metrics)
    names = {f.payload.get("name") for f in metrics}
    assert "daemon.cpu_percent" in names and "daemon.uptime_seconds" in names
    assert payload["version"]


async def test_health_service_ticks_then_stops(store, uplink):
    svc = HealthService(interval=0.01)
    task = asyncio.create_task(svc.run())
    await asyncio.sleep(0.05)
    await svc.stop()
    await asyncio.wait_for(task, timeout=1.0)
    # One uptime metric per tick -> emitted at least twice (immediate + an interval).
    ticks = [f for f in uplink.of_type("telemetry.metric")
             if f.payload.get("name") == "daemon.uptime_seconds"]
    assert len(ticks) >= 2


# ── daemon.ping ──────────────────────────────────────────────────────────────
async def test_daemon_ping_emits_snapshot_and_pong(store, uplink):
    await handle_daemon_ping(
        CommandContext(command_type="daemon.ping"), {"id": "probe-1"}
    )
    pongs = uplink.of_type("daemon.pong")
    assert len(pongs) == 1
    assert pongs[0].channel == "control"
    assert pongs[0].payload["id"] == "probe-1"
    assert "health" in pongs[0].payload


def test_daemon_commands_registered():
    # conftest clears the router each test and the module is import-cached, so reload to
    # re-run the @on_command decorators (matches how the daemon registers at assembly).
    import importlib

    import synapse_worker.commands.daemon as daemon_cmd

    importlib.reload(daemon_cmd)
    cmds = known_commands()
    assert "daemon.ping" in cmds
    assert "daemon.update" in cmds


# ── self-update integrity gate ───────────────────────────────────────────────
def test_verify_checksum_matches():
    data = b"package-bytes"
    digest = hashlib.sha256(data).hexdigest()
    assert verify_checksum(data, digest) is True
    assert verify_checksum(data, "sha256:" + digest) is True
    assert verify_checksum(data, "deadbeef") is False
    assert verify_checksum(data, "") is False  # no checksum => not trusted


async def test_apply_update_installs_only_when_checksum_matches():
    data = b"new-worker-wheel"
    good = hashlib.sha256(data).hexdigest()
    installed: list[tuple[str, str]] = []

    async def fake_download(url: str) -> bytes:
        return data

    async def fake_install(path: str, version: str) -> None:
        installed.append((path, version))

    runner = UpdateRunner(download=fake_download, install=fake_install)

    # Good checksum -> verified -> installed.
    res = await apply_update(
        UpdateRequest(version="0.2.0", url="https://x/pkg.whl", checksum=good),
        runner=runner,
    )
    assert res.ok is True and res.installed is True
    assert installed and installed[0][1] == "0.2.0"


async def test_apply_update_aborts_on_bad_checksum():
    data = b"tampered"
    installed: list = []

    async def fake_download(url: str) -> bytes:
        return data

    async def fake_install(path: str, version: str) -> None:
        installed.append(path)

    runner = UpdateRunner(download=fake_download, install=fake_install)
    res = await apply_update(
        UpdateRequest(version="0.2.0", url="https://x/pkg.whl", checksum="00" * 32),
        runner=runner,
    )
    # The installer must NEVER run on a verification failure.
    assert res.ok is False
    assert res.installed is False
    assert installed == []


async def test_apply_update_no_url_is_clean_failure():
    res = await apply_update(UpdateRequest(version="0.2.0"))
    assert res.ok is False and res.installed is False


# ── CLI ──────────────────────────────────────────────────────────────────────
def test_version_and_health_cli():
    from typer.testing import CliRunner

    from synapse_worker.cli.main import app

    runner = CliRunner()
    v = runner.invoke(app, ["version"])
    assert v.exit_code == 0
    assert "synapse-worker" in v.stdout

    h = runner.invoke(app, ["health"])
    assert h.exit_code == 0
