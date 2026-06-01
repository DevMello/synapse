"""Analytics query REST: rollups, anomalies, summary.

Read-only, org-scoped endpoints over the pre-aggregated `metric_rollups` and
`anomaly_events` tables (written by the rollup/anomaly workers), plus a small
windowed `summary` computed live from `runs`.

The service-role client bypasses RLS, so every query is scoped by
``principal.org_id`` here. Results are newest-first and bounded by limits.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..db import service_db
from ..deps import Principal, get_principal

router = APIRouter(tags=["analytics"])

_DEFAULT_LIMIT = 200
_MAX_LIMIT = 2000


@router.get("/analytics/rollups")
async def list_rollups(
    principal: Principal = Depends(get_principal),
    metric: Optional[str] = Query(default=None),
    agent_id: Optional[str] = Query(default=None),
    bucket: Optional[str] = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Pre-aggregated metric rollups, newest bucket first."""
    db = await service_db()
    q = db.table("metric_rollups").select("*").eq("org_id", principal.org_id)
    if metric is not None:
        q = q.eq("metric", metric)
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    if bucket is not None:
        q = q.eq("bucket", bucket)
    return (
        await q.order("bucket_start", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    ).data or []


@router.get("/analytics/anomalies")
async def list_anomalies(
    principal: Principal = Depends(get_principal),
    severity: Optional[str] = Query(default=None),
    agent_id: Optional[str] = Query(default=None),
    detector: Optional[str] = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Anomaly events for the org, newest-first, filterable."""
    db = await service_db()
    q = db.table("anomaly_events").select("*").eq("org_id", principal.org_id)
    if severity is not None:
        q = q.eq("severity", severity)
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    if detector is not None:
        q = q.eq("detector", detector)
    return (
        await q.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    ).data or []


@router.get("/analytics/summary")
async def analytics_summary(
    principal: Principal = Depends(get_principal),
    agent_id: Optional[str] = Query(default=None),
    window_seconds: int = Query(default=86400, ge=60, le=30 * 86400),
) -> dict:
    """Run counts, total cost, and error rate over a recent window."""
    db = await service_db()
    since = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat()
    q = (
        db.table("runs")
        .select("status, cost_usd, tokens_in, tokens_out")
        .eq("org_id", principal.org_id)
        .gte("created_at", since)
    )
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    rows = (await q.limit(_MAX_LIMIT * 10).execute()).data or []

    total = len(rows)
    failed = sum(1 for r in rows if r.get("status") in ("failed", "interrupted"))
    succeeded = sum(1 for r in rows if r.get("status") == "succeeded")
    total_cost = sum(float(r.get("cost_usd") or 0) for r in rows)
    total_tokens = sum(
        float(r.get("tokens_in") or 0) + float(r.get("tokens_out") or 0) for r in rows
    )

    return {
        "window_seconds": window_seconds,
        "runs": total,
        "succeeded": succeeded,
        "failed": failed,
        "error_rate": (failed / total) if total else 0.0,
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
    }
