"""Daemon health/heartbeat emitter + ping/update handlers (§6, §5, §4.2).

``app.build_daemon`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one wires three things:

  * ``health`` background service — every ``heartbeat_interval_seconds`` (15s) it samples a
    rich HEALTH SNAPSHOT (CPU, mem, disk, active runs, queue depth, version) and ships it
    upstream as ``telemetry.metric`` frames on the TELEMETRY channel. This is the dashboard
    feed; it is DISTINCT from the Connection unit's app-level ``{"type":"heartbeat"}``
    liveness frame (which we deliberately do NOT duplicate). Keeping it on the telemetry
    channel means a slow/backed-up snapshot can never head-of-line-block control traffic.
  * ``@on_command("daemon.ping")`` — an on-demand health probe: emit a fresh snapshot now.
  * ``@on_command("daemon.update")`` — a signature/checksum-verified self-update (§5);
    delegates the integrity gate + install to :mod:`synapse_worker.selfupdate`.

Everything here is best-effort: a sampling/emit failure is logged and swallowed so the
health loop (and the control loop) can never be torn down by telemetry.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from .. import health as _health
from ..config import get_settings
from ..logging import get_logger
from ..router import CommandContext, on_command
from ..selfupdate import UpdateRequest, UpdateRunner, apply_update
from ..services import register_service
from ..store import get_store
from ..uplink import CHANNEL_CONTROL, CHANNEL_TELEMETRY, get_uplink

log = get_logger(__name__)

# Per-field metric names — each shipped as a scalar telemetry.metric (numeric value).

_FIELD_METRICS = {
    "cpu_percent": "daemon.cpu_percent",
    "mem_mb": "daemon.mem_mb",
    "disk_percent": "daemon.disk_percent",
    "active_runs": "daemon.active_runs",
    "queue_depth": "daemon.queue_depth",
    "uptime_seconds": "daemon.uptime_seconds",
}


async def _queue_depth() -> int:
    """Best-effort outbound queue depth (the daemon's backlog of unsent frames).

    Reads ``get_store().pending_outbound()`` length; if the store isn't open (lightweight
    tests, very early boot) we report 0 rather than raising.
    """
    try:
        pending = await get_store().pending_outbound()
        return len(pending)
    except Exception:  # noqa: BLE001 - store not ready / query failed => unknown depth
        return 0


def _active_runs() -> int:
    """Best-effort count of in-flight runs.

    The runtime unit owns the authoritative count; we read it through a documented seam if
    present and fall back to 0 so the snapshot still emits standalone. Kept import-local so
    this module has no hard dependency on the runtime unit's load order.
    """
    try:
        from ..runtime import base as _runtime_base  # type: ignore

        getter = getattr(_runtime_base, "active_run_count", None)
        if callable(getter):
            return int(getter())
    except Exception:  # noqa: BLE001 - runtime unit absent or shape changed
        pass
    return 0


async def collect_snapshot() -> dict[str, Any]:
    """Sample a fresh health snapshot payload (active runs + queue depth filled in)."""
    snap = _health.collect(active_runs=_active_runs(), queue_depth=await _queue_depth())
    return snap.to_payload()


async def emit_snapshot(*, channel: str = CHANNEL_TELEMETRY) -> dict[str, Any]:
    """Sample and ship the health snapshot upstream as SCALAR telemetry metrics.

    The cloud's ``telemetry.metric`` value is numeric (a ``double precision`` column), so we
    emit one scalar metric per numeric field — NEVER the whole snapshot dict as a single
    metric value (Postgres rejects a non-numeric value: ``22P02``). The full point-in-time
    snapshot is still available to a prober via the ``daemon.pong`` reply. All on the
    telemetry channel so it can't block control/ack traffic. Best-effort; failures logged.
    Returns the sampled payload.
    """
    payload = await collect_snapshot()
    uplink = get_uplink()
    version = payload.get("version")
    try:
        for field, metric_name in _FIELD_METRICS.items():
            value = payload.get(field)
            if isinstance(value, (int, float)):
                await uplink.send(
                    "telemetry.metric",
                    {"name": metric_name, "value": value, "labels": {"version": version}},
                    channel=channel,
                )
    except Exception:  # noqa: BLE001 - telemetry is best-effort; never sink the loop
        log.exception("health: failed to emit snapshot")
    return payload


# ── background service: periodic snapshot emitter ─────────────────────────────
class HealthService:
    """Emits a health snapshot every ``heartbeat_interval_seconds`` until stopped.

    Distinct from the Connection unit's liveness heartbeat: this is the richer dashboard
    feed. ``run()`` loops until ``stop()`` is called (or the task is cancelled); a slow tick
    can't accumulate because we sleep AFTER each emit and tolerate cancellation cleanly.
    """

    def __init__(self, daemon: Any = None, *, interval: Optional[float] = None) -> None:
        self._daemon = daemon
        self._interval = interval
        self._stopped = asyncio.Event()

    @property
    def interval(self) -> float:
        if self._interval is not None:
            return self._interval
        return float(get_settings().heartbeat_interval_seconds)

    async def run(self) -> None:
        """Emit immediately, then every ``interval`` seconds until stopped/cancelled."""
        try:
            while not self._stopped.is_set():
                await emit_snapshot()
                # Wait for the interval OR an early stop, whichever comes first.
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=self.interval)
                except asyncio.TimeoutError:
                    pass  # normal: interval elapsed, emit again
        except asyncio.CancelledError:  # graceful shutdown via task cancel
            raise
        except Exception:  # noqa: BLE001 - a bug in emit must not kill the daemon
            log.exception("health: emit loop crashed")

    async def stop(self) -> None:
        self._stopped.set()


@register_service("health")
def make_health_service(daemon: Any):  # (Daemon) -> service with async run()/stop()
    return HealthService(daemon)


# ── command handlers ──────────────────────────────────────────────────────────
@on_command("daemon.ping")
async def handle_daemon_ping(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Health probe (§4.2): emit a fresh snapshot upstream and a ``daemon.pong`` ack.

    Defensive about the payload (a ping may carry a correlation id we echo back). The
    snapshot goes on telemetry; the small pong goes on control so the prober gets a prompt
    point-to-point reply.
    """
    snapshot = await emit_snapshot()
    echo = {}
    if isinstance(payload, dict):
        for key in ("id", "ping_id", "nonce"):
            if key in payload:
                echo[key] = payload[key]
    try:
        await get_uplink().send(
            "daemon.pong",
            {**echo, "health": snapshot},
            channel=CHANNEL_CONTROL,
        )
    except Exception:  # noqa: BLE001 - pong is best-effort
        log.exception("daemon.ping: failed to emit pong")


@on_command("daemon.update")
async def handle_daemon_update(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Self-update this worker (§5): SIGNATURE/CHECKSUM-VERIFIED before install.

    Delegates the download → verify → install pipeline to :mod:`synapse_worker.selfupdate`,
    which aborts before install on any verification failure (an unverified package is never
    executed). The terminal result is reported upstream as ``daemon.update.status`` so the
    Web UI can show success/failure — best-effort, on the control channel.
    """
    req = UpdateRequest.from_payload(payload if isinstance(payload, dict) else {})
    result = await apply_update(req, runner=_update_runner())

    status = {
        "version": result.version,
        "ok": result.ok,
        "installed": result.installed,
    }
    if result.error:
        status["error"] = result.error
    try:
        await get_uplink().send("daemon.update.status", status, channel=CHANNEL_CONTROL)
    except Exception:  # noqa: BLE001 - status report is best-effort
        log.exception("daemon.update: failed to report status")
    log.info(
        "daemon.update: version=%s ok=%s installed=%s (%s)",
        result.version or "?",
        result.ok,
        result.installed,
        result.error or "ok",
    )


def _update_runner() -> Optional[UpdateRunner]:
    """Hook for tests to inject a fake download+install runner.

    Production uses the default (real httpx download + uv/pip install). Tests monkeypatch
    this function to return a runner whose ``download`` yields known bytes and whose
    ``install`` records the call, so the checksum gate is exercised without network/upgrade.
    """
    return None
