"""Telemetry query REST: logs / metrics / reasoning traces.

Read-only, org-scoped endpoints for the Web UI to page through the telemetry a
daemon streamed in (persisted by `services.telemetry_ingest`). Importing that
module here registers its inbound handlers at app startup via router
autodiscovery.

Every query is scoped by `principal.org_id` — the service-role client bypasses
RLS, so org scoping is enforced in this module. Results are newest-first and
bounded by `limit`/`offset`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..db import service_db
from ..deps import Principal, get_principal

# Importing the service registers the inbound telemetry handlers (side effect).
from ..services import telemetry_ingest  # noqa: F401

router = APIRouter(tags=["telemetry"])

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000


@router.get("/runs/{run_id}/logs")
async def list_run_logs(
    run_id: str,
    principal: Principal = Depends(get_principal),
    level: Optional[str] = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Logs for a run, newest-first, optionally filtered by level."""
    db = await service_db()
    q = (
        db.table("logs")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("run_id", run_id)
    )
    if level is not None:
        q = q.eq("level", level)
    return (
        await q.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    ).data or []


@router.get("/runs/{run_id}/metrics")
async def list_run_metrics(
    run_id: str,
    principal: Principal = Depends(get_principal),
    name: Optional[str] = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Metric samples for a run, newest-first, optionally filtered by name."""
    db = await service_db()
    q = (
        db.table("metrics")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("run_id", run_id)
    )
    if name is not None:
        q = q.eq("name", name)
    return (
        await q.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    ).data or []


@router.get("/runs/{run_id}/traces")
async def list_run_traces(
    run_id: str,
    principal: Principal = Depends(get_principal),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Reasoning traces for a run, newest-first."""
    db = await service_db()
    return (
        await db.table("reasoning_traces")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("run_id", run_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    ).data or []


@router.get("/telemetry/logs")
async def query_logs(
    principal: Principal = Depends(get_principal),
    agent_id: Optional[str] = Query(default=None),
    level: Optional[str] = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Org-wide log query, newest-first, filterable by agent_id and/or level."""
    db = await service_db()
    q = db.table("logs").select("*").eq("org_id", principal.org_id)
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    if level is not None:
        q = q.eq("level", level)
    return (
        await q.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    ).data or []
