"""In-process periodic-job scheduler (replaces the Arq/Redis worker).

The cloud's background work is **cron-only** — there is no request→queue→worker path —
and every job is a plain ``async def f(ctx=None)``. So instead of a separate Arq process
backed by Redis, we run the jobs on asyncio loops inside the FastAPI process, started by
the app lifespan. Worker modules export a module-level ``periodic_jobs`` list of
:class:`PeriodicJob`; :func:`discover_periodic_jobs` aggregates them (same autodiscovery
seam the Arq worker used).

Single-execution across multiple app instances is guarded by a Postgres **lease**
(``job_leases`` table) claimed with a conditional UPDATE — only one instance wins each
tick. The lease check is **fail-open**: if the table is missing or the DB errors, the job
still runs (so a single-instance deployment works with zero setup).
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

_log = logging.getLogger("synapse_cloud.scheduler")

PeriodicCoro = Callable[..., Awaitable[Any]]


@dataclass
class PeriodicJob:
    """One periodic background job: a name, a coroutine, and its interval (seconds)."""

    name: str
    coro: PeriodicCoro
    interval_seconds: float
    run_at_startup: bool = False


def discover_periodic_jobs() -> list[PeriodicJob]:
    """Aggregate every worker module's ``periodic_jobs`` list."""
    jobs: list[PeriodicJob] = []
    pkg = importlib.import_module("synapse_cloud.workers")
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        m = importlib.import_module(f"synapse_cloud.workers.{mod.name}")
        jobs.extend(getattr(m, "periodic_jobs", []) or [])
    return jobs


async def claim_lease(job: str, ttl_seconds: float) -> bool:
    """Try to claim this tick's run of ``job`` (single-winner across instances).

    Fail-open: returns True on any error so a single-instance deployment runs even
    before ``job_leases`` exists.
    """
    try:
        from .db import service_db

        db = await service_db()
        now = datetime.now(timezone.utc)
        until = now + timedelta(seconds=ttl_seconds)
        # Ensure a row exists without resetting an existing (possibly future) lease.
        await (
            db.table("job_leases")
            .upsert({"job": job, "locked_until": now.isoformat()},
                    on_conflict="job", ignore_duplicates=True)
            .execute()
        )
        res = await (
            db.table("job_leases")
            .update({"locked_until": until.isoformat(), "updated_at": now.isoformat()})
            .eq("job", job)
            .lte("locked_until", now.isoformat())
            .execute()
        )
        return bool(res.data)
    except Exception:  # noqa: BLE001 - lease is best-effort; never block the job on it
        return True


class Scheduler:
    """Runs each :class:`PeriodicJob` on its own asyncio loop until stopped."""

    def __init__(self, jobs: list[PeriodicJob]) -> None:
        self._jobs = jobs
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._stop.clear()
        for job in self._jobs:
            self._tasks.append(asyncio.create_task(self._loop(job), name=f"sched:{job.name}"))

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _loop(self, job: PeriodicJob) -> None:
        if job.run_at_startup:
            await self._tick(job)
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=job.interval_seconds)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            await self._tick(job)

    async def _tick(self, job: PeriodicJob) -> None:
        try:
            if await claim_lease(job.name, job.interval_seconds):
                await job.coro(None)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - one bad tick must not kill the loop
            _log.exception("periodic job %s failed", job.name)
