"""Heartbeat monitor worker: detect dead daemons → interrupt their runs.

Daemons hold a ``daemon_presence`` lease (``expires_at``) refreshed by
heartbeats. When a daemon dies, its lease expires; this worker sweeps stale
presence rows and marks the daemon's in-flight runs ``interrupted`` and the
daemon ``offline`` so an operator can ``run.recover`` them onto another daemon.

Autodiscovery: exposes module-level ``tasks`` / ``cron_jobs`` which
``synapse_cloud.workers.__init__`` aggregates into ``WorkerSettings`` — no shared
file is edited. The task function is a plain ``async def fn(ctx, ...)`` so tests
can call ``sweep_interrupted_runs(ctx=None)`` directly with no running Redis.
"""
from __future__ import annotations

from typing import Any, Optional

from arq.cron import cron

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

cron_jobs = [
    # Sweep for dead daemons every 30 seconds (on the :00 and :30 marks).
    cron(sweep_interrupted_runs, second={0, 30}, run_at_startup=False),
]
