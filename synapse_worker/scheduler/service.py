"""Scheduler service — cron/interval/date schedules with a durable jobstore (§4.4).

Built on APScheduler 3.x. A :class:`SchedulerService` owns one ``AsyncIOScheduler``
backed by a **SQLAlchemy SQLite jobstore** under the daemon home, so schedules authored
in the Web UI and pushed via ``schedule.set`` survive a daemon restart. On startup the
service re-hydrates from the local ``schedules`` table as a defensive reconcile (the
jobstore already persists jobs, but the table is the daemon's own source of truth).

When a job fires it triggers a real agent run: the firing target loads the stored
``agent.toml``, mints a fresh ``run_id``, and drives :class:`RunEngine`. The target is a
**module-level coroutine** (not a bound method) so APScheduler can persist a job by
reference into the SQLite jobstore without pickling ``self``/the scheduler.

Missed-run policy (daemon was offline) maps onto APScheduler's misfire handling:

  * ``skip``     → ``misfire_grace_time`` small (1s) so missed runs are dropped.
  * ``coalesce`` → ``coalesce=True`` so a backlog collapses into a single run.
  * ``run_once`` → ``coalesce=True`` with a generous grace time so exactly one
    catch-up run fires after the daemon comes back.

Robustness contract: a fire that can't find the agent dir/manifest logs and skips
rather than tearing the scheduler down.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..logging import get_logger
from ..paths import WorkerPaths, get_paths

log = get_logger(__name__)

# Misfire grace (seconds) per policy. "skip" drops anything not fired ~immediately;
# "run_once" keeps a generous window so exactly one catch-up run survives a long offline
# window. Mapped here (not inline) so the policy->APScheduler contract is in one place.
_GRACE_SKIP = 1
_GRACE_DEFAULT = 3600  # 1h: ample for a coalesced catch-up run after reconnect.

# Recognized trigger kinds. Anything else is rejected (logged + skipped) at set time.
_KINDS = ("cron", "interval", "date")


def _policy_options(policy: Optional[str]) -> dict[str, Any]:
    """Translate a missed-run policy into APScheduler ``coalesce`` + ``misfire_grace_time``.

    Defensive: an unknown/empty policy falls back to ``coalesce`` semantics, the safest
    default (collapse a backlog into one run rather than replaying every missed slot).
    """
    p = (policy or "").strip().lower()
    if p == "skip":
        return {"coalesce": True, "misfire_grace_time": _GRACE_SKIP}
    if p == "run_once":
        return {"coalesce": True, "misfire_grace_time": _GRACE_DEFAULT}
    # "coalesce" and any unknown value: collapse missed runs into one.
    return {"coalesce": True, "misfire_grace_time": _GRACE_DEFAULT}


def _build_trigger(kind: str, expr: str):
    """Build the APScheduler trigger for ``kind``/``expr``. Raises ``ValueError`` on bad input."""
    kind = (kind or "").strip().lower()
    expr = (expr or "").strip()
    if not expr:
        raise ValueError("empty schedule expression")

    if kind == "cron":
        # CronTrigger.from_crontab parses a 5-field crontab string ("*/5 * * * *").
        return CronTrigger.from_crontab(expr)

    if kind == "interval":
        return IntervalTrigger(**_interval_kwargs(expr))

    if kind == "date":
        # ISO 8601 datetime; fromisoformat handles "2030-01-01T00:00:00[+00:00]".
        return DateTrigger(run_date=datetime.fromisoformat(expr))

    raise ValueError(f"unknown schedule kind {kind!r}")


def _interval_kwargs(expr: str) -> dict[str, int]:
    """Interpret an interval ``expr`` as seconds, or "<n><unit>" (s/m/h/d).

    The cloud may send a bare number (seconds) or a unit-suffixed string; both are
    accepted so the daemon never rejects a schedule on a cosmetic format difference.
    """
    s = expr.strip().lower()
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    if s and s[-1] in units and s[:-1].strip().isdigit():
        return {units[s[-1]]: int(s[:-1])}
    # Bare number => seconds.
    return {"seconds": int(float(s))}


# ── module-level firing target (must be importable for the SQLite jobstore) ──────────
async def _fire(schedule_id: str, agent_id: str, payload: Optional[dict[str, Any]]) -> None:
    """Trigger one agent run for a fired schedule.

    Defensive end to end: a missing agent dir/manifest, a bad ``agent.toml``, or an
    engine error logs and returns rather than propagating out of the scheduler's job
    execution (which would otherwise just be swallowed by APScheduler anyway, but we
    want a clean log line and no noisy traceback for the common "agent gone" case).
    """
    # Imported lazily so the SQLite jobstore can reference this function without pulling
    # the heavy runtime import graph at module import time.
    from ..errors import ManifestError
    from ..runtime.base import AgentManifest
    from ..runtime.engine import RunEngine

    try:
        paths = get_paths()
    except Exception:  # noqa: BLE001 - settings/paths unavailable -> skip this fire
        log.warning("schedule %s fired but paths unavailable; skipping", schedule_id)
        return

    toml_path = paths.agent_dir(agent_id) / "agent.toml"
    if not toml_path.exists():
        log.warning(
            "schedule %s fired but agent %s has no agent.toml; skipping",
            schedule_id,
            agent_id,
        )
        return

    try:
        manifest = AgentManifest.from_toml(toml_path.read_text(encoding="utf-8"))
    except (ManifestError, OSError) as exc:
        log.warning("schedule %s: bad agent.toml for %s: %s; skipping", schedule_id, agent_id, exc)
        return

    run_id = f"rn_{uuid4().hex}"
    log.info("schedule %s fired -> run %s (agent %s)", schedule_id, run_id, agent_id)
    try:
        await RunEngine().run_agent(
            manifest=manifest, run_id=run_id, prompt_vars=payload or {}
        )
    except Exception:  # noqa: BLE001 - run_agent shouldn't raise, but never sink the scheduler
        log.exception("schedule %s: run %s failed to launch", schedule_id, run_id)


class SchedulerService:
    """Long-running APScheduler service with a durable SQLite jobstore.

    Lifecycle mirrors the other daemon services: ``run()`` starts the scheduler, reconciles
    persisted schedules, and blocks until ``stop()``; ``stop()`` shuts it down cleanly.
    """

    def __init__(self, daemon: Any = None, *, paths: Optional[WorkerPaths] = None) -> None:
        # Accept either the assembled Daemon (production) or explicit paths (tests).
        self._paths = paths or getattr(daemon, "paths", None) or get_paths()
        self._scheduler = self._build_scheduler(self._paths)
        self._stop_event: Optional[asyncio.Event] = None  # created in run()
        self._started = False

    # ── construction ─────────────────────────────────────────────────────────
    @staticmethod
    def _build_scheduler(paths: WorkerPaths) -> AsyncIOScheduler:
        # A SEPARATE db file from the main state.db keeps APScheduler's schema isolated
        # from the daemon store (simplest + avoids cross-locking the WAL store).
        db_path = paths.home / "scheduler.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path.as_posix()}"
        jobstores = {"default": SQLAlchemyJobStore(url=url)}
        return AsyncIOScheduler(jobstores=jobstores)

    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler

    # ── schedule registration (called by the schedule.set handler) ─────────────
    def set_schedule(
        self,
        *,
        schedule_id: str,
        agent_id: str,
        kind: str,
        expr: str,
        policy: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        """Register or replace one APScheduler job (id == ``schedule_id``).

        Raises ``ValueError`` for an unparseable kind/expr so the caller can log + persist
        nothing. The scheduler need not be running yet — APScheduler buffers ``add_job``
        and applies it on ``start()``.
        """
        if (kind or "").strip().lower() not in _KINDS:
            raise ValueError(f"unknown schedule kind {kind!r}")
        trigger = _build_trigger(kind, expr)
        opts = _policy_options(policy)
        self._scheduler.add_job(
            _fire,
            trigger=trigger,
            id=schedule_id,
            args=[schedule_id, agent_id, payload or {}],
            replace_existing=True,
            coalesce=opts["coalesce"],
            misfire_grace_time=opts["misfire_grace_time"],
        )
        log.info(
            "schedule.set: registered %s (kind=%s, policy=%s)", schedule_id, kind, policy or "default"
        )

    def remove_schedule(self, schedule_id: str) -> None:
        """Remove a job if present (idempotent — a missing job is not an error)."""
        try:
            self._scheduler.remove_job(schedule_id)
            log.info("schedule.set: removed %s", schedule_id)
        except Exception:  # noqa: BLE001 - JobLookupError or scheduler-not-started; treat as gone
            log.debug("schedule.set: no job %s to remove", schedule_id)

    # ── lifecycle ──────────────────────────────────────────────────────────────
    async def run(self) -> None:
        """Start the scheduler, reconcile persisted schedules, and block until stopped."""
        self._stop_event = asyncio.Event()
        self.start()
        await self._reconcile_from_store()
        log.info("scheduler started (jobs=%d)", len(self._scheduler.get_jobs()))
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        finally:
            self.shutdown()

    def start(self) -> None:
        """Start the AsyncIOScheduler (idempotent within this service)."""
        if not self._started:
            self._scheduler.start()
            self._started = True

    async def stop(self) -> None:
        """Signal ``run()`` to unblock; shutdown happens in its ``finally``."""
        if self._stop_event is not None:
            self._stop_event.set()
        else:
            # run() was never entered (e.g. direct unit use): shut down inline.
            self.shutdown()

    def shutdown(self) -> None:
        """Shut the scheduler down cleanly (idempotent)."""
        if self._started and self._scheduler.running:
            # wait=False: don't block the event loop waiting for in-flight jobs.
            self._scheduler.shutdown(wait=False)
        self._started = False

    # ── startup reconcile ────────────────────────────────────────────────────
    async def _reconcile_from_store(self) -> None:
        """Re-hydrate jobs from the ``schedules`` table.

        APScheduler's jobstore already persists jobs across restarts, but the daemon's
        ``schedules`` table is its own authoritative record (rows written by the handler).
        Re-applying them defensively heals a divergence where a row exists but the
        jobstore was wiped (e.g. scheduler.db deleted), and is a no-op when they agree
        thanks to ``replace_existing=True``.
        """
        try:
            from ..store import get_store

            rows = await get_store().fetchall(
                "SELECT id, agent_id, kind, expr, policy, payload FROM schedules"
            )
        except Exception:  # noqa: BLE001 - store not ready -> rely on the jobstore alone
            log.debug("scheduler: store unavailable for reconcile; using jobstore only")
            return

        for row in rows:
            expr = row.get("expr")
            if not expr:
                # An empty expr marks a removed schedule; ensure no stale job lingers.
                self.remove_schedule(row["id"])
                continue
            payload: dict[str, Any] = {}
            raw = row.get("payload")
            if raw:
                try:
                    payload = json.loads(raw)
                except (ValueError, TypeError):
                    payload = {}
            try:
                self.set_schedule(
                    schedule_id=row["id"],
                    agent_id=row.get("agent_id") or "",
                    kind=row.get("kind") or "",
                    expr=expr,
                    policy=row.get("policy"),
                    payload=payload,
                )
            except ValueError as exc:
                log.warning("scheduler: skipping unparseable schedule %s: %s", row.get("id"), exc)
