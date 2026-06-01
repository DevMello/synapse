"""Analytics rollup worker (Arq tasks + cron).

Buckets recent raw `metrics` samples and per-run cost into `metric_rollups`
rows, one aggregate per (metric, agent_id, daemon_id, bucket, bucket_start).
Each row carries count/sum/min/max/avg/p95/ewma so the Web UI and the anomaly
detectors can read cheap pre-aggregated series instead of scanning raw
partitions.

Autodiscovery: this module exposes module-level ``tasks`` / ``cron_jobs`` lists
which `synapse_cloud.workers.__init__` aggregates into ``WorkerSettings``. The
task functions are plain ``async def fn(ctx, ...)`` so tests can call them
directly with ``ctx=None`` (no running Redis required).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from arq.cron import cron

from ..db import service_db

# Supported bucket granularities -> their width.
_BUCKET_WIDTHS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "1h": timedelta(hours=1),
}

# EWMA smoothing factor applied across ordered samples within a bucket.
_EWMA_ALPHA = 0.3

# Sentinel used by the metric_rollups unique index for NULL agent/daemon.
_NIL_UUID = "00000000-0000-0000-0000-000000000000"

# Synthetic metric name used to roll up per-run cost from the `runs` table.
_COST_METRIC = "run.cost_usd"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _bucket_start(ts: datetime, bucket: str) -> datetime:
    if bucket == "1m":
        return ts.replace(second=0, microsecond=0)
    if bucket == "1h":
        return ts.replace(minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported bucket {bucket!r}")


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile (pct in [0,1]) over a pre-sorted list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = pct * (len(sorted_values) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def _ewma(values: Iterable[float], alpha: float = _EWMA_ALPHA) -> float:
    acc: Optional[float] = None
    for v in values:
        acc = v if acc is None else alpha * v + (1 - alpha) * acc
    return acc or 0.0


def _aggregate(samples: list[tuple[datetime, float]]) -> dict[str, float]:
    """Compute the rollup stats for one (metric, agent, daemon, bucket) group.

    `samples` is a list of (created_at, value) ordered chronologically for a
    stable EWMA.
    """
    samples = sorted(samples, key=lambda s: s[0])
    values = [v for _, v in samples]
    ordered_for_ewma = values
    svals = sorted(values)
    count = len(values)
    total = sum(values)
    return {
        "count": count,
        "sum": total,
        "min": svals[0],
        "max": svals[-1],
        "avg": total / count,
        "p95": _percentile(svals, 0.95),
        "ewma": _ewma(ordered_for_ewma),
    }


async def _upsert_rollups(db, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    # The unique index keys on coalesce(agent_id/daemon_id, NIL). Postgres
    # on_conflict can't target a coalesce expression by column list, so we
    # delete-then-insert each group's bucket to stay idempotent across re-runs.
    for row in rows:
        q = (
            db.table("metric_rollups")
            .delete()
            .eq("org_id", row["org_id"])
            .eq("metric", row["metric"])
            .eq("bucket", row["bucket"])
            .eq("bucket_start", row["bucket_start"])
        )
        q = q.eq("agent_id", row["agent_id"]) if row["agent_id"] else q.is_("agent_id", "null")
        q = q.eq("daemon_id", row["daemon_id"]) if row["daemon_id"] else q.is_("daemon_id", "null")
        await q.execute()
    await db.table("metric_rollups").insert(rows).execute()


async def compute_metric_rollups(
    ctx: Optional[dict],
    *,
    org_id: Optional[str] = None,
    bucket: str = "1m",
    window_seconds: Optional[int] = None,
) -> int:
    """Roll up recent raw `metrics` samples into `metric_rollups`.

    Groups by (metric name, agent_id, daemon_id, bucket_start) over a recent
    window and writes one aggregate row per group. Returns the number of
    rollup rows written. Scoped to `org_id` when given (always set in tests /
    per-org cron fan-out); otherwise rolls up across all orgs.
    """
    if bucket not in _BUCKET_WIDTHS:
        raise ValueError(f"unsupported bucket {bucket!r}")
    db = await service_db()
    width = _BUCKET_WIDTHS[bucket]
    window = timedelta(seconds=window_seconds) if window_seconds else width * 5
    since = (_now() - window).isoformat()

    q = (
        db.table("metrics")
        .select("org_id, agent_id, daemon_id, name, value, created_at")
        .gte("created_at", since)
    )
    if org_id is not None:
        q = q.eq("org_id", org_id)
    rows = (await q.order("created_at").limit(50000).execute()).data or []

    # key -> list[(ts, value)]
    groups: dict[tuple, list[tuple[datetime, float]]] = defaultdict(list)
    meta: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        ts = _parse_ts(r.get("created_at"))
        if ts is None or r.get("value") is None:
            continue
        bstart = _bucket_start(ts, bucket)
        key = (
            r["org_id"],
            r.get("agent_id"),
            r.get("daemon_id"),
            r["name"],
            bstart,
        )
        groups[key].append((ts, float(r["value"])))
        meta[key] = {
            "org_id": r["org_id"],
            "agent_id": r.get("agent_id"),
            "daemon_id": r.get("daemon_id"),
            "metric": r["name"],
            "bucket_start": bstart.isoformat(),
        }

    out: list[dict[str, Any]] = []
    for key, samples in groups.items():
        stats = _aggregate(samples)
        out.append({**meta[key], "bucket": bucket, **stats})

    await _upsert_rollups(db, out)
    return len(out)


async def compute_cost_rollups(
    ctx: Optional[dict],
    *,
    org_id: Optional[str] = None,
    bucket: str = "1h",
    window_seconds: Optional[int] = None,
) -> int:
    """Roll up per-run cost (`runs.cost_usd`) into `metric_rollups`.

    Emits the synthetic metric ``run.cost_usd`` bucketed by run completion
    time, grouped by agent/daemon. Returns the number of rollup rows written.
    """
    if bucket not in _BUCKET_WIDTHS:
        raise ValueError(f"unsupported bucket {bucket!r}")
    db = await service_db()
    width = _BUCKET_WIDTHS[bucket]
    window = timedelta(seconds=window_seconds) if window_seconds else width * 24
    since = (_now() - window).isoformat()

    q = (
        db.table("runs")
        .select("org_id, agent_id, daemon_id, cost_usd, ended_at, created_at")
        .gte("created_at", since)
    )
    if org_id is not None:
        q = q.eq("org_id", org_id)
    rows = (await q.order("created_at").limit(50000).execute()).data or []

    groups: dict[tuple, list[tuple[datetime, float]]] = defaultdict(list)
    meta: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        ts = _parse_ts(r.get("ended_at")) or _parse_ts(r.get("created_at"))
        if ts is None:
            continue
        cost = float(r.get("cost_usd") or 0)
        bstart = _bucket_start(ts, bucket)
        key = (r["org_id"], r.get("agent_id"), r.get("daemon_id"), bstart)
        groups[key].append((ts, cost))
        meta[key] = {
            "org_id": r["org_id"],
            "agent_id": r.get("agent_id"),
            "daemon_id": r.get("daemon_id"),
            "metric": _COST_METRIC,
            "bucket_start": bstart.isoformat(),
        }

    out: list[dict[str, Any]] = []
    for key, samples in groups.items():
        stats = _aggregate(samples)
        out.append({**meta[key], "bucket": bucket, **stats})

    await _upsert_rollups(db, out)
    return len(out)


# ── Autodiscovery hooks ──────────────────────────────────────────────────────
tasks = [compute_metric_rollups, compute_cost_rollups]

cron_jobs = [
    # Minute-grain metric rollups every minute; hourly cost rollups on the hour.
    cron(compute_metric_rollups, minute=set(range(60)), run_at_startup=False),
    cron(compute_cost_rollups, minute={0}, run_at_startup=False),
]
