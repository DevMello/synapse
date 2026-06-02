"""Scheduler unit tests (§4.4) — self-contained, no network, no real wall-clock waits.

Strategy:
  * Construct :class:`SchedulerService` directly (don't rely on the service registry).
  * Drive the ``schedule.set`` handler against the live service to assert it both
    registers an APScheduler job AND writes the ``schedules`` row.
  * Verify cron/interval/date triggers build the expected job, and that the missed-run
    policy maps to coalesce + misfire_grace_time.
  * Verify a fired job invokes the run path by calling the job's target coroutine
    directly (deterministic — no real timer) with a deployed ``agent.toml``.
  * Always shut the scheduler down so no event-loop warnings leak.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from synapse_worker.paths import paths_for
from synapse_worker.router import CommandContext, handlers_for, known_commands
from synapse_worker.scheduler import service as svc_mod
from synapse_worker.scheduler.service import (
    SchedulerService,
    _interval_kwargs,
    _policy_options,
)


@pytest_asyncio.fixture
async def service(settings):
    """A started SchedulerService on the tmp home; shut down in teardown.

    Async because ``AsyncIOScheduler.start()`` requires a running event loop.
    """
    paths = paths_for(settings)
    paths.ensure_layout()
    s = SchedulerService(paths=paths)
    s.start()
    try:
        yield s
    finally:
        s.shutdown()


def _job(service: SchedulerService, job_id: str):
    return service.scheduler.get_job(job_id)


# ── policy mapping ────────────────────────────────────────────────────────────
def test_policy_skip_drops_missed_runs():
    opts = _policy_options("skip")
    assert opts["coalesce"] is True
    assert opts["misfire_grace_time"] == 1


def test_policy_coalesce_collapses_backlog():
    opts = _policy_options("coalesce")
    assert opts["coalesce"] is True
    assert opts["misfire_grace_time"] > 1


def test_policy_run_once_generous_grace():
    opts = _policy_options("run_once")
    assert opts["coalesce"] is True
    assert opts["misfire_grace_time"] >= 3600


def test_policy_unknown_defaults_to_coalesce():
    opts = _policy_options("nonsense")
    assert opts["coalesce"] is True


# ── interval expr parsing ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "expr,expected",
    [
        ("300", {"seconds": 300}),
        ("30s", {"seconds": 30}),
        ("5m", {"minutes": 5}),
        ("2h", {"hours": 2}),
        ("1d", {"days": 1}),
    ],
)
def test_interval_kwargs(expr, expected):
    assert _interval_kwargs(expr) == expected


# ── trigger construction per kind ─────────────────────────────────────────────
async def test_set_interval_registers_job(service):
    service.set_schedule(
        schedule_id="sch_int", agent_id="agt_1", kind="interval", expr="300", policy="skip"
    )
    job = _job(service, "sch_int")
    assert job is not None
    assert isinstance(job.trigger, IntervalTrigger)
    # "skip" policy -> tiny misfire grace.
    assert job.misfire_grace_time == 1
    assert job.coalesce is True


async def test_set_cron_registers_job(service):
    service.set_schedule(
        schedule_id="sch_cron", agent_id="agt_1", kind="cron", expr="*/5 * * * *", policy="coalesce"
    )
    job = _job(service, "sch_cron")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)


async def test_set_date_registers_job(service):
    service.set_schedule(
        schedule_id="sch_date",
        agent_id="agt_1",
        kind="date",
        expr="2999-01-01T00:00:00",
        policy="run_once",
    )
    job = _job(service, "sch_date")
    assert job is not None
    assert isinstance(job.trigger, DateTrigger)


async def test_set_replaces_existing(service):
    service.set_schedule(schedule_id="sch_x", agent_id="a", kind="interval", expr="60")
    service.set_schedule(schedule_id="sch_x", agent_id="a", kind="interval", expr="120")
    # replace_existing=True => still exactly one job under that id.
    jobs = [j for j in service.scheduler.get_jobs() if j.id == "sch_x"]
    assert len(jobs) == 1


async def test_set_bad_kind_raises(service):
    with pytest.raises(ValueError):
        service.set_schedule(schedule_id="sch_bad", agent_id="a", kind="weekly", expr="x")


async def test_remove_schedule_is_idempotent(service):
    service.set_schedule(schedule_id="sch_r", agent_id="a", kind="interval", expr="60")
    service.remove_schedule("sch_r")
    assert _job(service, "sch_r") is None
    # Removing again must not raise.
    service.remove_schedule("sch_r")


# ── schedule.set handler: job + row ───────────────────────────────────────────
async def test_handler_registers_job_and_writes_row(service, store, monkeypatch):
    # Point the handler module at our live service.
    from synapse_worker.commands import schedules as sched_cmd

    monkeypatch.setattr(sched_cmd, "_service", service)

    ctx = CommandContext(command_type="schedule.set")
    await sched_cmd.handle_schedule_set(
        ctx,
        {
            "schedule_id": "sch_h1",
            "agent_id": "agt_42",
            "kind": "interval",
            "expr": "300",
            "policy": "coalesce",
            "payload": {"prompt": "hi"},
        },
    )

    # APScheduler job registered.
    assert _job(service, "sch_h1") is not None

    # schedules row persisted.
    row = await store.fetchone("SELECT * FROM schedules WHERE id=?", ("sch_h1",))
    assert row is not None
    assert row["agent_id"] == "agt_42"
    assert row["kind"] == "interval"
    assert json.loads(row["payload"]) == {"prompt": "hi"}


async def test_handler_empty_expr_removes(service, store, monkeypatch):
    from synapse_worker.commands import schedules as sched_cmd

    monkeypatch.setattr(sched_cmd, "_service", service)
    ctx = CommandContext(command_type="schedule.set")

    await sched_cmd.handle_schedule_set(
        ctx, {"schedule_id": "sch_del", "agent_id": "a", "kind": "interval", "expr": "60"}
    )
    assert _job(service, "sch_del") is not None
    assert await store.fetchone("SELECT * FROM schedules WHERE id=?", ("sch_del",)) is not None

    # Now an empty expr removes both the job and the row.
    await sched_cmd.handle_schedule_set(ctx, {"schedule_id": "sch_del", "expr": ""})
    assert _job(service, "sch_del") is None
    assert await store.fetchone("SELECT * FROM schedules WHERE id=?", ("sch_del",)) is None


async def test_handler_missing_id_is_noop(service, store, monkeypatch):
    from synapse_worker.commands import schedules as sched_cmd

    monkeypatch.setattr(sched_cmd, "_service", service)
    ctx = CommandContext(command_type="schedule.set")
    # No schedule_id -> handler returns without persisting.
    await sched_cmd.handle_schedule_set(ctx, {"agent_id": "a", "kind": "interval", "expr": "60"})
    rows = await store.fetchall("SELECT * FROM schedules")
    assert rows == []


# ── fired job triggers an agent run ───────────────────────────────────────────
async def test_fired_job_invokes_run_engine(settings, store, monkeypatch):
    # Deploy a minimal agent.toml under the agent dir so _fire can load it.
    paths = paths_for(settings)
    paths.ensure_layout()
    agent_dir = paths.agent_dir("agt_run")
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "agent.toml").write_text(
        '[agent]\nid = "agt_run"\nname = "runner"\ntype = "api"\nversion = 1\n',
        encoding="utf-8",
    )

    calls: list[dict] = []

    async def fake_run_agent(self, *, manifest, run_id, prompt_vars, env=None):
        calls.append({"agent_id": manifest.id, "run_id": run_id, "prompt_vars": prompt_vars})
        from synapse_worker.runtime.base import RunResult

        return RunResult(status="success")

    from synapse_worker.runtime.engine import RunEngine

    monkeypatch.setattr(RunEngine, "run_agent", fake_run_agent)

    # Invoke the job's target coroutine directly (no real timer wait).
    await svc_mod._fire("sch_fire", "agt_run", {"topic": "weekly"})

    assert len(calls) == 1
    assert calls[0]["agent_id"] == "agt_run"
    assert calls[0]["run_id"].startswith("rn_")
    assert calls[0]["prompt_vars"] == {"topic": "weekly"}


async def test_fired_job_missing_agent_is_skipped(settings, store, monkeypatch):
    # No agent dir => _fire must log + skip, never raise, never call the engine.
    paths_for(settings).ensure_layout()
    called = False

    async def fake_run_agent(self, **kwargs):  # pragma: no cover - must NOT run
        nonlocal called
        called = True

    from synapse_worker.runtime.engine import RunEngine

    monkeypatch.setattr(RunEngine, "run_agent", fake_run_agent)

    await svc_mod._fire("sch_missing", "agt_nope", {})
    assert called is False


# ── startup reconcile from the schedules table ────────────────────────────────
async def test_run_reconciles_persisted_schedules(settings, store):
    # Pre-seed a schedules row as if a previous process wrote it.
    await store.execute(
        "INSERT INTO schedules (id, agent_id, kind, expr, policy, payload, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        ("sch_persisted", "agt_p", "interval", "120", "coalesce", json.dumps({"k": "v"}), 0.0),
    )

    paths = paths_for(settings)
    paths.ensure_layout()
    service = SchedulerService(paths=paths)
    service.start()
    try:
        await service._reconcile_from_store()
        job = service.scheduler.get_job("sch_persisted")
        assert job is not None
        assert isinstance(job.trigger, IntervalTrigger)
    finally:
        service.shutdown()


async def test_reconcile_skips_empty_expr_rows(settings, store):
    await store.execute(
        "INSERT INTO schedules (id, agent_id, kind, expr, policy, payload, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        ("sch_empty", "agt_p", "interval", "", "skip", "{}", 0.0),
    )
    paths = paths_for(settings)
    paths.ensure_layout()
    service = SchedulerService(paths=paths)
    service.start()
    try:
        await service._reconcile_from_store()
        assert service.scheduler.get_job("sch_empty") is None
    finally:
        service.shutdown()


# ── command registration smoke ────────────────────────────────────────────────
def test_command_registered():
    # The autouse conftest fixture clears the handler registry around every test, so
    # reload the module to re-run its @on_command registration side-effect.
    import importlib

    import synapse_worker.commands.schedules as sched_cmd

    importlib.reload(sched_cmd)
    assert "schedule.set" in known_commands()
    assert handlers_for("schedule.set")


# ── full lifecycle: run() then stop() ─────────────────────────────────────────
async def test_run_then_stop_lifecycle(settings, store):
    import asyncio

    paths = paths_for(settings)
    paths.ensure_layout()
    service = SchedulerService(paths=paths)
    task = asyncio.create_task(service.run())
    # Let run() start the scheduler + reconcile.
    await asyncio.sleep(0.05)
    assert service.scheduler.running
    await service.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert not service.scheduler.running
