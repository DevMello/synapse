"""In-process periodic scheduler + Postgres lease (replaces Arq/Redis).

Verifies job autodiscovery, single-winner lease claiming (real job_leases table), and
that the Scheduler actually fires a job.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from synapse_cloud.scheduler import (
    PeriodicJob,
    Scheduler,
    claim_lease,
    discover_periodic_jobs,
)

pytestmark = pytest.mark.asyncio


async def test_discover_finds_the_worker_jobs():
    names = {j.name for j in discover_periodic_jobs()}
    assert {
        "anomaly.run_all_detectors",
        "heartbeat.sweep_interrupted_runs",
        "notify.sweep_expired_hitl",
        "rollups.compute_metric_rollups",
        "rollups.compute_cost_rollups",
    } <= names


async def test_lease_is_single_winner(test_org):
    # test_org ensures real Supabase creds (skips otherwise).
    from synapse_cloud.db import service_db

    job = f"test.lease.{uuid.uuid4().hex[:8]}"
    try:
        assert await claim_lease(job, ttl_seconds=60) is True   # first claim wins
        assert await claim_lease(job, ttl_seconds=60) is False  # held within ttl
    finally:
        db = await service_db()
        await db.table("job_leases").delete().eq("job", job).execute()


async def test_scheduler_fires_a_job():
    fired = asyncio.Event()

    async def _job(_ctx=None):
        fired.set()

    sched = Scheduler(
        [PeriodicJob(f"test.run.{uuid.uuid4().hex[:8]}", _job, interval_seconds=0.05, run_at_startup=True)]
    )
    await sched.start()
    try:
        await asyncio.wait_for(fired.wait(), timeout=3.0)
    finally:
        await sched.stop()
    assert fired.is_set()
