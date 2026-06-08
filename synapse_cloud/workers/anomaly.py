"""Anomaly detection worker (Arq tasks + cron).

Each detector is a plain ``async def detect_*(ctx, *, org_id, ...)`` that reads
recent rows for one org (optionally narrowed to an agent), decides whether the
recent window is anomalous versus a baseline, and on a hit:

  1. inserts an `anomaly_events` row, and
  2. fans out via ``get_notifier().notify(org_id, "anomaly", {...}, channels=None)``.

Detectors are pure of request context (workers run outside a Principal), so org
scoping is passed in and applied with ``.eq("org_id", org_id)``. They return the
inserted event row (or ``None`` when nothing tripped) so tests can assert on the
result as well as on the DB / notifier seam.

Autodiscovery: module-level ``tasks`` / ``cron_jobs`` are aggregated by
`synapse_cloud.workers.__init__`. Tests call the detectors directly with
``ctx=None`` — no running Redis required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..scheduler import PeriodicJob

from ..db import service_db
from ..notifications.base import get_notifier

# ── Thresholds (pragmatic, documented; no speculative ML) ─────────────────────
_COST_Z_THRESHOLD = 3.0          # cost spike: z-score over historical run cost
_COST_MIN_HISTORY = 5            # need a baseline before judging a spike
_LATENCY_REGRESSION_FACTOR = 3.0  # p95 latency >= 3x baseline p95
_ERROR_RATE_THRESHOLD = 0.5      # >50% of recent runs failed
_ERROR_MIN_RUNS = 4              # need enough runs for a meaningful rate
_TOKEN_BLOWUP_FACTOR = 5.0       # tokens >= 5x baseline average
_TOKEN_MIN_HISTORY = 5
_INJECTION_SPIKE_COUNT = 3       # >=3 injection findings in the window
_LATENCY_METRIC = "latency_ms"
_TOKEN_METRIC_NAMES = ("tokens_total", "tokens", "token_count")
_INJECTION_METRIC_NAMES = ("injection", "prompt_injection", "injection_finding")


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


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stddev(xs: list[float], mean: float) -> float:
    if len(xs) < 2:
        return 0.0
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return var ** 0.5


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = pct * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


async def _emit(
    db,
    *,
    org_id: str,
    detector: str,
    severity: str,
    metric: Optional[str],
    baseline: Optional[float],
    observed: Optional[float],
    detail: dict[str, Any],
    agent_id: Optional[str] = None,
    daemon_id: Optional[str] = None,
) -> dict[str, Any]:
    """Insert an `anomaly_events` row and notify the org."""
    row: dict[str, Any] = {
        "org_id": org_id,
        "detector": detector,
        "severity": severity,
        "detail": detail,
    }
    if agent_id is not None:
        row["agent_id"] = agent_id
    if daemon_id is not None:
        row["daemon_id"] = daemon_id
    if metric is not None:
        row["metric"] = metric
    if baseline is not None:
        row["baseline"] = baseline
    if observed is not None:
        row["observed"] = observed

    inserted = (await db.table("anomaly_events").insert(row).execute()).data
    event = inserted[0] if inserted else row

    await get_notifier().notify(
        org_id,
        "anomaly",
        {
            "detector": detector,
            "severity": severity,
            "metric": metric,
            "baseline": baseline,
            "observed": observed,
            "agent_id": agent_id,
            "daemon_id": daemon_id,
            **detail,
        },
        channels=None,
    )
    return event


# ── Detectors ─────────────────────────────────────────────────────────────────
async def detect_cost_spike(
    ctx: Optional[dict],
    *,
    org_id: str,
    agent_id: Optional[str] = None,
    window_seconds: int = 3600,
) -> Optional[dict[str, Any]]:
    """Flag when the most recent run's cost is a z-score outlier vs history."""
    db = await service_db()
    q = (
        db.table("runs")
        .select("id, agent_id, daemon_id, cost_usd, created_at")
        .eq("org_id", org_id)
    )
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    rows = (await q.order("created_at", desc=True).limit(100).execute()).data or []
    if len(rows) <= _COST_MIN_HISTORY:
        return None

    latest = rows[0]
    history = [float(r.get("cost_usd") or 0) for r in rows[1:]]
    observed = float(latest.get("cost_usd") or 0)
    mean = _mean(history)
    sd = _stddev(history, mean)
    if sd == 0:
        return None
    z = (observed - mean) / sd
    if z < _COST_Z_THRESHOLD:
        return None

    return await _emit(
        db,
        org_id=org_id,
        detector="cost_spike",
        severity="critical" if z >= 2 * _COST_Z_THRESHOLD else "warning",
        metric="run.cost_usd",
        baseline=mean,
        observed=observed,
        detail={"z_score": round(z, 3), "run_id": latest.get("id")},
        agent_id=latest.get("agent_id"),
        daemon_id=latest.get("daemon_id"),
    )


async def detect_latency_regression(
    ctx: Optional[dict],
    *,
    org_id: str,
    agent_id: Optional[str] = None,
    window_seconds: int = 600,
    baseline_seconds: int = 86400,
) -> Optional[dict[str, Any]]:
    """Flag when recent p95 latency is >= 3x the longer-window baseline p95."""
    db = await service_db()
    now = _now()
    win_since = (now - timedelta(seconds=window_seconds)).isoformat()
    base_since = (now - timedelta(seconds=baseline_seconds)).isoformat()

    def _q(since: str):
        q = (
            db.table("metrics")
            .select("agent_id, daemon_id, value, created_at")
            .eq("org_id", org_id)
            .eq("name", _LATENCY_METRIC)
            .gte("created_at", since)
        )
        if agent_id is not None:
            q = q.eq("agent_id", agent_id)
        return q

    recent = (await _q(win_since).limit(10000).execute()).data or []
    if not recent:
        return None
    baseline_rows = (await _q(base_since).limit(50000).execute()).data or []
    # Baseline excludes the recent window so a regression doesn't poison it.
    win_cut = _parse_ts(win_since)
    base_vals = [
        float(r["value"])
        for r in baseline_rows
        if r.get("value") is not None
        and (_parse_ts(r.get("created_at")) or now) < win_cut
    ]
    if len(base_vals) < 5:
        return None

    recent_p95 = _percentile([float(r["value"]) for r in recent if r.get("value") is not None], 0.95)
    base_p95 = _percentile(base_vals, 0.95)
    if base_p95 <= 0 or recent_p95 < _LATENCY_REGRESSION_FACTOR * base_p95:
        return None

    return await _emit(
        db,
        org_id=org_id,
        detector="latency_regression",
        severity="warning",
        metric=_LATENCY_METRIC,
        baseline=base_p95,
        observed=recent_p95,
        detail={"factor": round(recent_p95 / base_p95, 3), "samples": len(recent)},
        agent_id=agent_id,
    )


async def detect_error_rate_spike(
    ctx: Optional[dict],
    *,
    org_id: str,
    agent_id: Optional[str] = None,
    window_seconds: int = 3600,
) -> Optional[dict[str, Any]]:
    """Flag when the failed-run fraction over a recent window exceeds threshold."""
    db = await service_db()
    since = (_now() - timedelta(seconds=window_seconds)).isoformat()
    q = (
        db.table("runs")
        .select("status, agent_id")
        .eq("org_id", org_id)
        .gte("created_at", since)
    )
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    rows = (await q.limit(10000).execute()).data or []
    total = len(rows)
    if total < _ERROR_MIN_RUNS:
        return None
    failed = sum(1 for r in rows if r.get("status") in ("failed", "interrupted"))
    rate = failed / total
    if rate < _ERROR_RATE_THRESHOLD:
        return None

    return await _emit(
        db,
        org_id=org_id,
        detector="error_rate_spike",
        severity="critical" if rate >= 0.8 else "warning",
        metric="run.error_rate",
        baseline=_ERROR_RATE_THRESHOLD,
        observed=rate,
        detail={"failed": failed, "total": total},
        agent_id=agent_id,
    )


async def detect_token_blowup(
    ctx: Optional[dict],
    *,
    org_id: str,
    agent_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Flag when the latest run's total tokens >= 5x the historical average."""
    db = await service_db()
    q = (
        db.table("runs")
        .select("id, agent_id, daemon_id, tokens_in, tokens_out, created_at")
        .eq("org_id", org_id)
    )
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    rows = (await q.order("created_at", desc=True).limit(100).execute()).data or []
    if len(rows) <= _TOKEN_MIN_HISTORY:
        return None

    def _tokens(r: dict) -> float:
        return float(r.get("tokens_in") or 0) + float(r.get("tokens_out") or 0)

    latest = rows[0]
    history = [_tokens(r) for r in rows[1:]]
    observed = _tokens(latest)
    mean = _mean(history)
    if mean <= 0 or observed < _TOKEN_BLOWUP_FACTOR * mean:
        return None

    return await _emit(
        db,
        org_id=org_id,
        detector="token_blowup",
        severity="warning",
        metric="run.tokens_total",
        baseline=mean,
        observed=observed,
        detail={"factor": round(observed / mean, 3), "run_id": latest.get("id")},
        agent_id=latest.get("agent_id"),
        daemon_id=latest.get("daemon_id"),
    )


async def detect_silence(
    ctx: Optional[dict],
    *,
    org_id: str,
    agent_id: Optional[str] = None,
    window_seconds: int = 900,
) -> Optional[dict[str, Any]]:
    """Flag when no telemetry (metrics) has arrived within the window.

    Only fires for orgs that have telemetry history (so a brand-new org with no
    data ever isn't flagged). Silence = had data before, none in the window.
    """
    db = await service_db()
    since = (_now() - timedelta(seconds=window_seconds)).isoformat()

    def _q():
        q = db.table("metrics").select("id, created_at").eq("org_id", org_id)
        if agent_id is not None:
            q = q.eq("agent_id", agent_id)
        return q

    recent = (await _q().gte("created_at", since).limit(1).execute()).data or []
    if recent:
        return None
    ever = (await _q().order("created_at", desc=True).limit(1).execute()).data or []
    if not ever:
        return None  # never sent telemetry — not "silence"

    last_ts = _parse_ts(ever[0].get("created_at"))
    return await _emit(
        db,
        org_id=org_id,
        detector="silence",
        severity="warning",
        metric=None,
        baseline=None,
        observed=None,
        detail={
            "window_seconds": window_seconds,
            "last_seen": last_ts.isoformat() if last_ts else None,
        },
        agent_id=agent_id,
    )


async def detect_daemon_offline(
    ctx: Optional[dict],
    *,
    org_id: str,
) -> Optional[dict[str, Any]]:
    """Flag daemons registered for the org that have no live presence.

    A daemon is offline when it has no `daemon_presence` row, or its presence
    has expired. Emits one event per offline daemon and returns the last one.
    """
    db = await service_db()
    daemons = (
        await db.table("daemons").select("id, name").eq("org_id", org_id).execute()
    ).data or []
    if not daemons:
        return None
    presence = (
        await db.table("daemon_presence")
        .select("daemon_id, expires_at")
        .eq("org_id", org_id)
        .execute()
    ).data or []
    now = _now()
    live: set[str] = set()
    for p in presence:
        exp = _parse_ts(p.get("expires_at"))
        if exp is not None and exp > now:
            live.add(p["daemon_id"])

    last_event: Optional[dict[str, Any]] = None
    for d in daemons:
        if d["id"] in live:
            continue
        last_event = await _emit(
            db,
            org_id=org_id,
            detector="daemon_offline",
            severity="critical",
            metric=None,
            baseline=None,
            observed=None,
            detail={"daemon_name": d.get("name")},
            daemon_id=d["id"],
        )
    return last_event


async def detect_injection_spike(
    ctx: Optional[dict],
    *,
    org_id: str,
    agent_id: Optional[str] = None,
    window_seconds: int = 3600,
) -> Optional[dict[str, Any]]:
    """Flag when injection findings (a metric) spike within the window.

    Injection findings surface as `metrics` rows named one of
    ``injection`` / ``prompt_injection`` / ``injection_finding``. We sum their
    values (each finding contributes >=1) over the window and fire past a count
    threshold.
    """
    db = await service_db()
    since = (_now() - timedelta(seconds=window_seconds)).isoformat()
    q = (
        db.table("metrics")
        .select("agent_id, daemon_id, name, value")
        .eq("org_id", org_id)
        .in_("name", list(_INJECTION_METRIC_NAMES))
        .gte("created_at", since)
    )
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    rows = (await q.limit(10000).execute()).data or []
    if not rows:
        return None
    count = sum(float(r.get("value") or 1) for r in rows)
    if count < _INJECTION_SPIKE_COUNT:
        return None

    return await _emit(
        db,
        org_id=org_id,
        detector="injection_spike",
        severity="critical",
        metric="injection",
        baseline=float(_INJECTION_SPIKE_COUNT),
        observed=count,
        detail={"findings": len(rows)},
        agent_id=agent_id,
    )


async def run_all_detectors(
    ctx: Optional[dict],
    *,
    org_id: Optional[str] = None,
) -> int:
    """Cron entrypoint: run every detector for every org (or one org).

    Returns the number of anomaly events emitted across all detectors.
    """
    db = await service_db()
    if org_id is not None:
        org_ids = [org_id]
    else:
        orgs = (await db.table("organizations").select("id").execute()).data or []
        org_ids = [o["id"] for o in orgs]

    detectors = [
        detect_cost_spike,
        detect_latency_regression,
        detect_error_rate_spike,
        detect_token_blowup,
        detect_silence,
        detect_daemon_offline,
        detect_injection_spike,
    ]
    emitted = 0
    for oid in org_ids:
        for detector in detectors:
            try:
                if await detector(ctx, org_id=oid):
                    emitted += 1
            except Exception:  # noqa: BLE001 - one detector must not kill the sweep
                continue
    return emitted


# ── Autodiscovery hooks ──────────────────────────────────────────────────────
tasks = [
    detect_cost_spike,
    detect_latency_regression,
    detect_error_rate_spike,
    detect_token_blowup,
    detect_silence,
    detect_daemon_offline,
    detect_injection_spike,
    run_all_detectors,
]

periodic_jobs = [
    # Sweep all detectors across all orgs every 5 minutes.
    PeriodicJob("anomaly.run_all_detectors", run_all_detectors, 300),
]
