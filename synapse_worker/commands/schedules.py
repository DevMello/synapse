"""Schedule command + service wiring: ``schedule.set`` (§4.4).

``app.build_daemon`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one (a) registers the ``schedule.set`` ``@on_command`` handler AND (b) registers the
``scheduler`` service factory. ``run_daemon`` instantiates the factory after the store is
open; the factory stashes the live :class:`SchedulerService` here so the handler can add /
remove APScheduler jobs against the already-running scheduler.

Payload shape (read defensively — the cloud is the wire source of truth, but a renamed /
missing field must degrade gracefully rather than crash the control loop)::

    {
      "schedule_id": "sch_...",
      "agent_id":    "agt_...",
      "kind":        "cron" | "interval" | "date",
      "expr":        "*/5 * * * *" | "300" | "2030-01-01T00:00:00",
      "policy":      "skip" | "run_once" | "coalesce",
      "payload":     { ... }            # optional prompt_vars for the run
    }

An empty/``None`` ``expr`` (or a truthy ``delete``/``remove`` flag) removes the schedule:
the APScheduler job is dropped and the ``schedules`` row is deleted.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from ..logging import get_logger
from ..router import CommandContext, on_command
from ..scheduler.service import SchedulerService
from ..services import register_service
from ..store import get_store

log = get_logger(__name__)

# The live scheduler instance, stashed by the factory at daemon assembly so the command
# handler can mutate the running scheduler. None until run_daemon constructs the service
# (handlers tolerate that: they still persist the row so a later reconcile picks it up).
_service: Optional[SchedulerService] = None


@register_service("scheduler")
def make_scheduler(daemon) -> SchedulerService:  # (Daemon) -> service with async run()/stop()
    global _service
    _service = SchedulerService(daemon)
    return _service


def _is_delete(payload: dict[str, Any], expr: Optional[str]) -> bool:
    """A schedule is being removed if expr is empty or a delete/remove flag is set."""
    if not (expr or "").strip():
        return True
    return bool(payload.get("delete") or payload.get("remove"))


@on_command("schedule.set")
async def handle_schedule_set(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Register/replace (or remove) a schedule: update APScheduler + the ``schedules`` row."""
    schedule_id = payload.get("schedule_id") or payload.get("id")
    if not schedule_id:
        log.warning("schedule.set: missing schedule_id; ignoring")
        return

    agent_id = payload.get("agent_id") or ""
    kind = payload.get("kind") or ""
    expr = payload.get("expr")
    policy = payload.get("policy")
    job_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}

    if _is_delete(payload, expr):
        await _remove(schedule_id)
        return

    # Register the job FIRST so an unparseable kind/expr aborts before we persist a row
    # the scheduler can't honor. If no live service yet, skip job registration but still
    # persist the row — the next run()/reconcile will pick it up from the table.
    if _service is not None:
        try:
            _service.set_schedule(
                schedule_id=schedule_id,
                agent_id=agent_id,
                kind=kind,
                expr=str(expr),
                policy=policy,
                payload=job_payload,
            )
        except ValueError as exc:
            log.warning("schedule.set %s: %s; not persisting", schedule_id, exc)
            return

    await _upsert_row(
        schedule_id=schedule_id,
        agent_id=agent_id,
        kind=kind,
        expr=str(expr),
        policy=policy,
        payload=job_payload,
    )
    log.info("schedule.set: stored schedule %s (agent %s)", schedule_id, agent_id)


# ── persistence helpers ──────────────────────────────────────────────────────
async def _upsert_row(
    *,
    schedule_id: str,
    agent_id: str,
    kind: str,
    expr: str,
    policy: Optional[str],
    payload: dict[str, Any],
) -> None:
    try:
        await get_store().execute(
            "INSERT INTO schedules (id, agent_id, kind, expr, policy, payload, updated_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET agent_id=excluded.agent_id, kind=excluded.kind,"
            " expr=excluded.expr, policy=excluded.policy, payload=excluded.payload,"
            " updated_at=excluded.updated_at",
            (
                schedule_id,
                agent_id,
                kind,
                expr,
                policy,
                json.dumps(payload, separators=(",", ":")),
                time.time(),
            ),
        )
    except Exception:  # noqa: BLE001 - persistence best-effort; never sink the control loop
        log.exception("schedule.set %s: failed to persist row", schedule_id)


async def _remove(schedule_id: str) -> None:
    if _service is not None:
        _service.remove_schedule(schedule_id)
    try:
        await get_store().execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
    except Exception:  # noqa: BLE001
        log.exception("schedule.set %s: failed to delete row", schedule_id)
    log.info("schedule.set: removed schedule %s", schedule_id)
