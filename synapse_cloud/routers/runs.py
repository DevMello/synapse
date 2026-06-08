"""Runs REST + tool_calls + inbound run.finished handler.

A *run* is one execution of an agent. The lifecycle:

  1. ``POST /agents/{agent_id}/runs`` creates a `runs` row (status 'pending')
     and pushes an ``agent.run`` command to the agent's owning daemon over the
     command bus. An optional ``idempotency_key`` makes the create idempotent
     per org: if a run with that key already exists, it is returned instead of
     creating a duplicate.
  2. The daemon executes and eventually reports back with an inbound
     ``run.finished`` message; the handler below finalizes the row (status,
     ended_at, cost/tokens, exit_code).
  3. ``POST /runs/{id}/cancel`` pushes an ``agent.cancel`` command and marks the
     run 'cancelled'.

`tool_calls` are the individual tool invocations within a run. They are written
by the inbound message path (via `record_tool_calls`) and read via
``GET /runs/{id}/tool_calls``.

Every query is scoped by `principal.org_id` — the service-role client bypasses
RLS, so org scoping is enforced here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import RUN_FINISHED, MessageContext, on_daemon_message
from ..notifications.base import get_notifier

router = APIRouter(tags=["runs"])

# run_status values the daemon may report as terminal via run.finished.
_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "interrupted"}


class RunCreate(BaseModel):
    """Body for starting a run."""

    trigger: str = Field(default="manual")
    idempotency_key: Optional[str] = Field(default=None, min_length=1)
    input: Optional[dict[str, Any]] = None


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


async def _get_run(db, org_id: str, run_id: str) -> dict:
    rows = (
        await db.table("runs")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", run_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return rows[0]


@router.post("/agents/{agent_id}/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    agent_id: str,
    body: RunCreate,
    principal: Principal = Depends(require_write),
) -> dict:
    """Start a run for an agent: create the row + dispatch ``agent.run``."""
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)

    # Idempotency: a prior run with the same key for this org wins.
    if body.idempotency_key:
        existing = (
            await db.table("runs")
            .select("*")
            .eq("org_id", principal.org_id)
            .eq("idempotency_key", body.idempotency_key)
            .execute()
        ).data or []
        if existing:
            return existing[0]

    daemon_id = agent.get("daemon_id")
    insert: dict[str, Any] = {
        "org_id": principal.org_id,
        "agent_id": agent_id,
        "trigger": body.trigger,
        "status": "pending",
    }
    if agent.get("version") is not None:
        insert["agent_version"] = agent["version"]
    if daemon_id is not None:
        insert["daemon_id"] = daemon_id
    if body.idempotency_key:
        insert["idempotency_key"] = body.idempotency_key

    try:
        run = (await db.table("runs").insert(insert).execute()).data[0]
    except APIError as exc:
        # Lost a check-then-insert race against the unique
        # (org_id, idempotency_key) index — return the winner instead of 500.
        if body.idempotency_key and getattr(exc, "code", None) == "23505":
            winner = (
                await db.table("runs")
                .select("*")
                .eq("org_id", principal.org_id)
                .eq("idempotency_key", body.idempotency_key)
                .execute()
            ).data or []
            if winner:
                return winner[0]
        raise
    run_id = run["id"]

    if daemon_id is not None:
        await get_command_bus().send(
            daemon_id,
            "agent.run",
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "trigger": body.trigger,
                "input": body.input or {},
            },
            idempotency_key=body.idempotency_key or run_id,
        )

    await get_audit().write(
        principal.org_id,
        "agent.run",
        actor=principal.user_id,
        resource_type="run",
        resource_id=run_id,
        run_id=run_id,
        detail={"agent_id": agent_id, "trigger": body.trigger},
    )
    return run


@router.get("/runs")
async def list_runs(
    principal: Principal = Depends(get_principal),
    agent_id: Optional[str] = Query(default=None),
    run_status: Optional[str] = Query(default=None, alias="status"),
) -> list[dict]:
    """List the org's runs, optionally filtered by agent_id and/or status."""
    db = await service_db()
    q = db.table("runs").select("*").eq("org_id", principal.org_id)
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    if run_status is not None:
        q = q.eq("status", run_status)
    return (await q.order("created_at", desc=True).execute()).data or []


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Single run detail, org-scoped (404 if not in caller's org)."""
    db = await service_db()
    return await _get_run(db, principal.org_id, run_id)


@router.get("/agents/{agent_id}/runs")
async def list_agent_runs(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """Run history for a single agent, org-scoped."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    return (
        await db.table("runs")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Cancel a run: dispatch ``agent.cancel`` + mark the run 'cancelled'."""
    db = await service_db()
    run = await _get_run(db, principal.org_id, run_id)

    if run.get("status") in _TERMINAL_STATUSES:
        # Already finished; nothing to cancel.
        return run

    daemon_id = run.get("daemon_id")
    if daemon_id is not None:
        await get_command_bus().send(
            daemon_id,
            "agent.cancel",
            {"run_id": run_id, "agent_id": run.get("agent_id")},
            idempotency_key=f"cancel:{run_id}",
        )

    updated = (
        await db.table("runs")
        .update({"status": "cancelled", "ended_at": _now_iso()})
        .eq("org_id", principal.org_id)
        .eq("id", run_id)
        .execute()
    ).data
    cancelled = updated[0] if updated else {**run, "status": "cancelled"}

    await get_audit().write(
        principal.org_id,
        "agent.cancel",
        actor=principal.user_id,
        resource_type="run",
        resource_id=run_id,
        run_id=run_id,
    )
    return cancelled


@router.get("/runs/{run_id}/tool_calls")
async def list_tool_calls(
    run_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """List tool_calls recorded for a run, org-scoped."""
    db = await service_db()
    await _get_run(db, principal.org_id, run_id)
    return (
        await db.table("tool_calls")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("run_id", run_id)
        .order("created_at")
        .execute()
    ).data or []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def record_tool_calls(
    org_id: str, run_id: str, calls: list[dict[str, Any]]
) -> list[dict]:
    """Persist tool_calls rows for a run. Used by the inbound message path.

    Each entry may carry: name, args_redacted, result_redacted, latency_ms,
    cost_usd. Unknown keys are ignored; org_id/run_id are always stamped here.
    """
    if not calls:
        return []
    db = await service_db()
    rows: list[dict[str, Any]] = []
    for call in calls:
        row: dict[str, Any] = {"org_id": org_id, "run_id": run_id}
        if "name" in call:
            row["name"] = call["name"]
        if "args_redacted" in call:
            row["args_redacted"] = call["args_redacted"]
        if "result_redacted" in call:
            row["result_redacted"] = call["result_redacted"]
        if "latency_ms" in call:
            row["latency_ms"] = call["latency_ms"]
        # cost_usd is NOT NULL with a default; batched inserts unify columns
        # across rows, so stamp an explicit 0 when omitted to avoid null.
        row["cost_usd"] = call.get("cost_usd", 0)
        rows.append(row)
    return (await db.table("tool_calls").insert(rows).execute()).data or []


@on_daemon_message(RUN_FINISHED)
async def handle_run_finished(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Finalize a run when its daemon reports completion.

    Sets status (succeeded/failed/...), ended_at, cost_usd, token counts, and
    exit_code from the payload. Scoped strictly by ``ctx.org_id`` so a daemon
    can only finalize its own org's runs. Any ``tool_calls`` in the payload are
    persisted as well.
    """
    run_id = ctx.run_id or payload.get("run_id")
    if not run_id:
        return

    updates: dict[str, Any] = {
        "status": payload.get("status", "succeeded"),
        "ended_at": payload.get("ended_at") or _now_iso(),
    }
    if "cost_usd" in payload:
        updates["cost_usd"] = payload["cost_usd"]
    if "tokens_in" in payload:
        updates["tokens_in"] = payload["tokens_in"]
    if "tokens_out" in payload:
        updates["tokens_out"] = payload["tokens_out"]
    if "exit_code" in payload:
        updates["exit_code"] = payload["exit_code"]
    if "redaction_summary" in payload:
        updates["redaction_summary"] = payload["redaction_summary"]

    db = await service_db()
    updated = (
        await db.table("runs")
        .update(updates)
        .eq("org_id", ctx.org_id)
        .eq("id", run_id)
        .execute()
    ).data or []

    tool_calls = payload.get("tool_calls")
    if tool_calls:
        await record_tool_calls(ctx.org_id, run_id, tool_calls)

    # Reactive notification: a failed/interrupted run fans out to the org's channels
    # (Slack/Discord/Email) inline, best-effort. Routing rules can target "run.failed".
    if updates["status"] in ("failed", "interrupted"):
        row = updated[0] if updated else {}
        try:
            await get_notifier().notify(
                ctx.org_id,
                "run.failed",
                {
                    "run_id": run_id,
                    "agent_id": row.get("agent_id") or payload.get("agent_id"),
                    "status": updates["status"],
                    "exit_code": payload.get("exit_code"),
                    "error": payload.get("error"),
                },
            )
        except Exception:  # noqa: BLE001 - notification is best-effort; never block finalization
            pass
