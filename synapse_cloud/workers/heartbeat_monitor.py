"""Heartbeat monitor worker: detect dead daemons → interrupt their runs.

Daemons hold a ``daemon_presence`` lease (``expires_at``) refreshed by
heartbeats. When a daemon dies, its lease expires; this worker sweeps stale
presence rows and marks the daemon's in-flight runs ``interrupted`` and the
daemon ``offline`` so an operator can ``run.recover`` them onto another daemon.

Autodiscovery: exposes a module-level ``periodic_jobs`` list which the in-process
``synapse_cloud.scheduler`` aggregates and runs — no shared file is edited, no Redis.
The function is a plain ``async def fn(ctx=None)`` so tests can call
``sweep_interrupted_runs(ctx=None)`` directly.
"""
from __future__ import annotations

from typing import Any, Optional

from ..scheduler import PeriodicJob

from ..db import service_db
from ..services.recovery import sweep_interrupted_runs as _sweep_core


async def sweep_interrupted_runs(ctx: Optional[dict] = None) -> dict[str, Any]:
    """Arq task: mark stale daemons offline + their in-flight runs interrupted.

    Delegates to the plain async core in ``services.recovery`` so the DB logic is
    shared with (and unit-tested without Redis by) the recovery tests. ``ctx`` is
    the Arq context (unused) and defaults to ``None`` for direct invocation.
    """
    db = await service_db()
    return await _sweep_core(db)


# ── Autodiscovery hooks ──────────────────────────────────────────────────────
tasks = [sweep_interrupted_runs]

periodic_jobs = [
    # Sweep for dead daemons every 30 seconds.
    PeriodicJob("heartbeat.sweep_interrupted_runs", sweep_interrupted_runs, 30),
]
