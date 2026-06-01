"""Schedules REST: CRUD for agent run schedules + schedule.set dispatch.

A *schedule* defines when an agent should run automatically. Three kinds:

  * ``cron``     — recurring on a cron expression (``cron_expr`` required).
  * ``interval`` — every N seconds (``interval_seconds`` required).
  * ``one_shot`` — once at a specific instant (``run_at`` required).

Each create / update / enable-toggle pushes a ``schedule.set`` command to the
agent's owning daemon over the command bus so the daemon's local scheduler stays
in sync. On disable or delete we still send ``schedule.set`` carrying the latest
state (``enabled=false`` / deleted) so the daemon tears the timer down. Sends are
skipped when the agent has no ``daemon_id``; the row is still persisted.

Every query is scoped by ``principal.org_id`` — the service-role client bypasses
RLS, so org scoping is enforced here.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write

router = APIRouter(tags=["schedules"])

_VALID_KINDS = {"cron", "interval", "one_shot"}


# ── request models ────────────────────────────────────────────────────────────
class ScheduleCreate(BaseModel):
    kind: str = Field(description="schedule_kind: 'cron', 'interval' or 'one_shot'")
    cron_expr: Optional[str] = None
    interval_seconds: Optional[int] = Field(default=None, gt=0)
    run_at: Optional[str] = None
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    cron_expr: Optional[str] = None
    interval_seconds: Optional[int] = Field(default=None, gt=0)
    run_at: Optional[str] = None
    enabled: Optional[bool] = None


# ── helpers ─────────────────────────────────────────────────────────────────
async def _get_agent(db, org_id: str, agent_id: str) -> dict:
    rows = (
        await db.table("agents")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", agent_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    return rows[0]


async def _get_schedule(db, org_id: str, schedule_id: str) -> dict:
    rows = (
        await db.table("schedules")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", schedule_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule not found")
    return rows[0]


def _validate_kind(kind: str, cron_expr, interval_seconds, run_at) -> None:
    """Reject create payloads whose fields don't match the declared kind."""
    if kind not in _VALID_KINDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"kind must be one of {sorted(_VALID_KINDS)}",
        )
    if kind == "cron" and not cron_expr:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cron kind requires cron_expr")
    if kind == "interval" and interval_seconds is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "interval kind requires interval_seconds"
        )
    if kind == "one_shot" and not run_at:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "one_shot kind requires run_at"
        )


async def _emit_schedule_set(
    schedule: dict,
    agent: dict,
    *,
    org_id: str,
    actor: Optional[str],
    action: str,
    deleted: bool = False,
) -> bool:
    """Send ``schedule.set`` to the agent's owning daemon and audit.

    No-op send (returns False) when the agent has no owning daemon; still
    audits. ``deleted`` flags a teardown so the daemon drops the timer.
    """
    schedule_id = schedule["id"]
    daemon_id = agent.get("daemon_id")

    sent = False
    if daemon_id:
        payload: dict[str, Any] = {
            "schedule_id": schedule_id,
            "agent_id": agent["id"],
            "kind": schedule.get("kind"),
            "cron_expr": schedule.get("cron_expr"),
            "interval_seconds": schedule.get("interval_seconds"),
            "run_at": schedule.get("run_at"),
            "enabled": bool(schedule.get("enabled")) and not deleted,
            "deleted": deleted,
        }
        await get_command_bus().send(
            daemon_id,
            "schedule.set",
            payload,
            idempotency_key=f"schedule.set:{schedule_id}:{action}",
        )
        sent = True

    await get_audit().write(
        org_id,
        "schedule.set",
        actor=actor,
        resource_type="schedule",
        resource_id=schedule_id,
        detail={
            "agent_id": agent["id"],
            "daemon_id": daemon_id,
            "action": action,
            "delivered": sent,
        },
    )
    return sent


# ── CRUD ────────────────────────────────────────────────────────────────────
@router.post("/agents/{agent_id}/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    agent_id: str,
    body: ScheduleCreate,
    principal: Principal = Depends(require_write),
) -> dict:
    """Create a schedule for an agent and dispatch ``schedule.set``."""
    _validate_kind(body.kind, body.cron_expr, body.interval_seconds, body.run_at)

    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)

    schedule = (
        await db.table("schedules")
        .insert(
            {
                "org_id": principal.org_id,
                "agent_id": agent_id,
                "kind": body.kind,
                "cron_expr": body.cron_expr,
                "interval_seconds": body.interval_seconds,
                "run_at": body.run_at,
                "enabled": body.enabled,
            }
        )
        .execute()
    ).data[0]

    await _emit_schedule_set(
        schedule,
        agent,
        org_id=principal.org_id,
        actor=principal.user_id,
        action="create",
    )
    return schedule


@router.get("/agents/{agent_id}/schedules")
async def list_agent_schedules(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """List an agent's schedules, org-scoped."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    return (
        await db.table("schedules")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .order("created_at")
        .execute()
    ).data or []


@router.get("/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Single schedule detail, org-scoped (404 if not in caller's org)."""
    db = await service_db()
    return await _get_schedule(db, principal.org_id, schedule_id)


@router.patch("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    principal: Principal = Depends(require_write),
) -> dict:
    """Update a schedule (expr/interval/run_at/enabled) + dispatch ``schedule.set``.

    Validates updated fields against the schedule's existing ``kind``.
    """
    db = await service_db()
    schedule = await _get_schedule(db, principal.org_id, schedule_id)

    updates: dict[str, Any] = {}
    if "cron_expr" in body.model_fields_set:
        updates["cron_expr"] = body.cron_expr
    if "interval_seconds" in body.model_fields_set:
        updates["interval_seconds"] = body.interval_seconds
    if "run_at" in body.model_fields_set:
        updates["run_at"] = body.run_at
    if body.enabled is not None:
        updates["enabled"] = body.enabled

    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no mutable fields provided")

    # The kind is immutable; the resulting schedule must still satisfy it.
    merged = {**schedule, **updates}
    kind = merged["kind"]
    if kind == "cron" and not merged.get("cron_expr"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cron kind requires cron_expr")
    if kind == "interval" and merged.get("interval_seconds") is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "interval kind requires interval_seconds"
        )
    if kind == "one_shot" and not merged.get("run_at"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "one_shot kind requires run_at"
        )

    updated = (
        await db.table("schedules")
        .update(updates)
        .eq("org_id", principal.org_id)
        .eq("id", schedule_id)
        .execute()
    ).data[0]

    agent = await _get_agent(db, principal.org_id, updated["agent_id"])
    await _emit_schedule_set(
        updated,
        agent,
        org_id=principal.org_id,
        actor=principal.user_id,
        action="update",
    )
    return updated


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Delete a schedule + dispatch a teardown ``schedule.set`` (deleted=true)."""
    db = await service_db()
    schedule = await _get_schedule(db, principal.org_id, schedule_id)
    agent = await _get_agent(db, principal.org_id, schedule["agent_id"])

    await (
        db.table("schedules")
        .delete()
        .eq("org_id", principal.org_id)
        .eq("id", schedule_id)
        .execute()
    )

    await _emit_schedule_set(
        schedule,
        agent,
        org_id=principal.org_id,
        actor=principal.user_id,
        action="delete",
        deleted=True,
    )
    return {"deleted": True, "id": schedule_id}
