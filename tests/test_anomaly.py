"""Tests for analytics rollups + anomaly detectors + the analytics router.

Detectors/rollups are called directly (no Redis). Each seeds rows into the real
Supabase project under a fresh isolated org, runs the function, then asserts on
the `anomaly_events` / `metric_rollups` tables AND the in-memory FakeNotifier
seam (`get_notifier().sent`).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from synapse_cloud.db import service_db
from synapse_cloud.notifications.base import get_notifier
from synapse_cloud.workers import anomaly, rollups


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _await_row_count(db, table: str, org_id: str, expected: int) -> None:
    """Wait until `expected` rows for the org are visible in `table`.

    Tests run against real Supabase and conftest rebinds the cached client per
    test (Windows event-loop quirk); a just-inserted row can briefly lag the
    worker's read. Poll the same client the worker uses before rolling up.
    """
    for _ in range(20):
        rows = (
            await db.table(table).select("id").eq("org_id", org_id).execute()
        ).data or []
        if len(rows) >= expected:
            return
        await asyncio.sleep(0.1)


async def _make_agent(db, org_id: str, name: str = "a") -> str:
    row = (
        await db.table("agents")
        .insert({"org_id": org_id, "name": name, "type": "cli"})
        .execute()
    ).data[0]
    return row["id"]


def _events_for(org_id: str):
    return [n for n in get_notifier().sent if n.org_id == org_id and n.event == "anomaly"]


# ── Rollups ───────────────────────────────────────────────────────────────────
async def test_metric_rollups_aggregate(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    samples = [10.0, 20.0, 30.0, 40.0]
    rows = [
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "name": "latency_ms",
            "value": v,
            "created_at": _iso(now - timedelta(seconds=10)),
        }
        for v in samples
    ]
    await db.table("metrics").insert(rows).execute()
    await _await_row_count(db, "metrics", org.org_id, len(samples))

    written = await rollups.compute_metric_rollups(None, org_id=org.org_id, bucket="1m")
    assert written >= 1

    got = (
        await db.table("metric_rollups")
        .select("*")
        .eq("org_id", org.org_id)
        .eq("metric", "latency_ms")
        .execute()
    ).data
    assert got
    r = got[0]
    assert r["count"] == 4
    assert r["sum"] == pytest.approx(100.0)
    assert r["min"] == pytest.approx(10.0)
    assert r["max"] == pytest.approx(40.0)
    assert r["avg"] == pytest.approx(25.0)
    assert r["p95"] >= 30.0


async def test_metric_rollups_idempotent(make_test_org):
    org = await make_test_org()
    db = await service_db()
    now = _now()
    await db.table("metrics").insert(
        [
            {
                "org_id": org.org_id,
                "name": "m1",
                "value": 5.0,
                "created_at": _iso(now - timedelta(seconds=5)),
            }
        ]
    ).execute()
    await _await_row_count(db, "metrics", org.org_id, 1)
    await rollups.compute_metric_rollups(None, org_id=org.org_id, bucket="1m")
    await rollups.compute_metric_rollups(None, org_id=org.org_id, bucket="1m")
    got = (
        await db.table("metric_rollups")
        .select("id")
        .eq("org_id", org.org_id)
        .eq("metric", "m1")
        .execute()
    ).data
    assert len(got) == 1  # re-run does not duplicate


async def test_cost_rollups(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    await db.table("runs").insert(
        [
            {
                "org_id": org.org_id,
                "agent_id": agent_id,
                "status": "succeeded",
                "cost_usd": 1.5,
                "ended_at": _iso(now - timedelta(minutes=5)),
            },
            {
                "org_id": org.org_id,
                "agent_id": agent_id,
                "status": "succeeded",
                "cost_usd": 2.5,
                "ended_at": _iso(now - timedelta(minutes=5)),
            },
        ]
    ).execute()
    await _await_row_count(db, "runs", org.org_id, 2)
    written = await rollups.compute_cost_rollups(None, org_id=org.org_id, bucket="1h")
    assert written >= 1
    got = (
        await db.table("metric_rollups")
        .select("*")
        .eq("org_id", org.org_id)
        .eq("metric", "run.cost_usd")
        .execute()
    ).data
    assert got
    assert got[0]["sum"] == pytest.approx(4.0)


# ── Detectors that fire ─────────────────────────────────────────────────────────
async def test_cost_spike_fires(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    # Baseline with small realistic variance, then a huge spike as newest run.
    baseline_costs = [0.8, 1.2, 0.9, 1.1, 1.0, 0.95, 1.05, 1.0]
    baseline = [
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "status": "succeeded",
            "cost_usd": c,
            "created_at": _iso(now - timedelta(minutes=30 - i)),
        }
        for i, c in enumerate(baseline_costs)
    ]
    await db.table("runs").insert(baseline).execute()
    await db.table("runs").insert(
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "status": "succeeded",
            "cost_usd": 50.0,
            "created_at": _iso(now),
        }
    ).execute()

    event = await anomaly.detect_cost_spike(None, org_id=org.org_id)
    assert event is not None
    rows = (
        await db.table("anomaly_events")
        .select("*")
        .eq("org_id", org.org_id)
        .eq("detector", "cost_spike")
        .execute()
    ).data
    assert rows
    assert float(rows[0]["observed"]) == pytest.approx(50.0)
    sent = _events_for(org.org_id)
    assert any(n.payload.get("detector") == "cost_spike" for n in sent)


async def test_cost_spike_no_fire_on_stable(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    rows = [
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "status": "succeeded",
            "cost_usd": 1.0,
            "created_at": _iso(now - timedelta(minutes=i)),
        }
        for i in range(10)
    ]
    await db.table("runs").insert(rows).execute()
    event = await anomaly.detect_cost_spike(None, org_id=org.org_id)
    assert event is None
    assert not _events_for(org.org_id)


async def test_latency_regression_fires(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    # Baseline ~100ms an hour ago; recent ~600ms.
    base = [
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "name": "latency_ms",
            "value": 100.0,
            "created_at": _iso(now - timedelta(minutes=60)),
        }
        for _ in range(10)
    ]
    recent = [
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "name": "latency_ms",
            "value": 600.0,
            "created_at": _iso(now - timedelta(seconds=30)),
        }
        for _ in range(6)
    ]
    await db.table("metrics").insert(base + recent).execute()
    await _await_row_count(db, "metrics", org.org_id, len(base) + len(recent))

    event = await anomaly.detect_latency_regression(None, org_id=org.org_id, agent_id=agent_id)
    assert event is not None
    assert float(event["observed"]) >= 3 * float(event["baseline"])
    assert any(n.payload.get("detector") == "latency_regression" for n in _events_for(org.org_id))


async def test_error_rate_spike_fires(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    rows = []
    for i in range(6):
        rows.append(
            {
                "org_id": org.org_id,
                "agent_id": agent_id,
                "status": "failed" if i < 5 else "succeeded",
                "created_at": _iso(now - timedelta(minutes=i)),
            }
        )
    await db.table("runs").insert(rows).execute()
    event = await anomaly.detect_error_rate_spike(None, org_id=org.org_id)
    assert event is not None
    assert float(event["observed"]) > 0.5
    assert any(n.payload.get("detector") == "error_rate_spike" for n in _events_for(org.org_id))


async def test_error_rate_no_fire_when_healthy(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    rows = [
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "status": "succeeded",
            "created_at": _iso(now - timedelta(minutes=i)),
        }
        for i in range(6)
    ]
    await db.table("runs").insert(rows).execute()
    assert await anomaly.detect_error_rate_spike(None, org_id=org.org_id) is None


async def test_token_blowup_fires(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    base = [
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "status": "succeeded",
            "tokens_in": 100,
            "tokens_out": 100,
            "created_at": _iso(now - timedelta(minutes=10 - i)),
        }
        for i in range(8)
    ]
    await db.table("runs").insert(base).execute()
    await db.table("runs").insert(
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "status": "succeeded",
            "tokens_in": 5000,
            "tokens_out": 5000,
            "created_at": _iso(now),
        }
    ).execute()
    event = await anomaly.detect_token_blowup(None, org_id=org.org_id)
    assert event is not None
    assert any(n.payload.get("detector") == "token_blowup" for n in _events_for(org.org_id))


async def test_silence_fires_with_history(make_test_org):
    org = await make_test_org()
    db = await service_db()
    now = _now()
    # Old telemetry only, nothing recent.
    await db.table("metrics").insert(
        {
            "org_id": org.org_id,
            "name": "heartbeat",
            "value": 1.0,
            "created_at": _iso(now - timedelta(hours=2)),
        }
    ).execute()
    event = await anomaly.detect_silence(None, org_id=org.org_id, window_seconds=900)
    assert event is not None
    assert any(n.payload.get("detector") == "silence" for n in _events_for(org.org_id))


async def test_silence_no_fire_when_recent(make_test_org):
    org = await make_test_org()
    db = await service_db()
    now = _now()
    await db.table("metrics").insert(
        {
            "org_id": org.org_id,
            "name": "heartbeat",
            "value": 1.0,
            "created_at": _iso(now - timedelta(seconds=10)),
        }
    ).execute()
    await _await_row_count(db, "metrics", org.org_id, 1)
    assert await anomaly.detect_silence(None, org_id=org.org_id, window_seconds=900) is None


async def _await_daemon_count(db, org_id: str, expected: int) -> None:
    for _ in range(20):
        rows = (
            await db.table("daemons").select("id").eq("org_id", org_id).execute()
        ).data or []
        if len(rows) >= expected:
            return
        await asyncio.sleep(0.1)


async def test_daemon_offline_fires(make_test_org):
    org = await make_test_org()
    await org.make_daemon()  # registered daemon, no presence row -> offline
    db = await service_db()
    await _await_daemon_count(db, org.org_id, 1)
    event = await anomaly.detect_daemon_offline(None, org_id=org.org_id)
    assert event is not None
    assert event["detector"] == "daemon_offline"
    assert any(n.payload.get("detector") == "daemon_offline" for n in _events_for(org.org_id))


async def test_daemon_offline_no_fire_when_present(make_test_org):
    org = await make_test_org()
    daemon_id, _ = await org.make_daemon()
    db = await service_db()
    await db.table("daemon_presence").insert(
        {
            "daemon_id": daemon_id,
            "org_id": org.org_id,
            "expires_at": _iso(_now() + timedelta(minutes=5)),
        }
    ).execute()
    # Ensure the presence row is visible to the detector's client before asserting.
    for _ in range(20):
        pres = (
            await db.table("daemon_presence")
            .select("daemon_id")
            .eq("org_id", org.org_id)
            .execute()
        ).data or []
        if pres:
            break
        await asyncio.sleep(0.1)
    assert await anomaly.detect_daemon_offline(None, org_id=org.org_id) is None


async def test_injection_spike_fires(make_test_org):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    rows = [
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "name": "injection",
            "value": 1.0,
            "created_at": _iso(now - timedelta(seconds=30)),
        }
        for _ in range(4)
    ]
    await db.table("metrics").insert(rows).execute()
    event = await anomaly.detect_injection_spike(None, org_id=org.org_id)
    assert event is not None
    assert any(n.payload.get("detector") == "injection_spike" for n in _events_for(org.org_id))


async def test_run_all_detectors_isolated_to_org(make_test_org):
    org = await make_test_org()
    await org.make_daemon()  # guarantees at least daemon_offline fires
    db = await service_db()
    await _await_daemon_count(db, org.org_id, 1)
    emitted = await anomaly.run_all_detectors(None, org_id=org.org_id)
    assert emitted >= 1


# ── Router ──────────────────────────────────────────────────────────────────────
async def test_router_anomalies_and_rollups(make_test_org, client):
    org = await make_test_org()
    db = await service_db()
    agent_id = await _make_agent(db, org.org_id)
    now = _now()
    # Seed a rollup row directly so the router test is independent of worker
    # read-after-write timing (worker behaviour is covered by the rollup tests).
    await db.table("metric_rollups").insert(
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "metric": "latency_ms",
            "bucket": "1m",
            "bucket_start": _iso(now.replace(second=0, microsecond=0)),
            "count": 1,
            "sum": 42.0,
            "min": 42.0,
            "max": 42.0,
            "avg": 42.0,
            "p95": 42.0,
            "ewma": 42.0,
        }
    ).execute()
    await db.table("anomaly_events").insert(
        {
            "org_id": org.org_id,
            "agent_id": agent_id,
            "detector": "cost_spike",
            "severity": "critical",
            "metric": "run.cost_usd",
            "baseline": 1.0,
            "observed": 9.0,
        }
    ).execute()

    r = await client.get("/analytics/rollups", params={"metric": "latency_ms"}, headers=org.auth_headers())
    assert r.status_code == 200
    assert any(row["metric"] == "latency_ms" for row in r.json())

    r = await client.get("/analytics/anomalies", params={"severity": "critical"}, headers=org.auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body and all(row["severity"] == "critical" for row in body)

    r = await client.get("/analytics/summary", headers=org.auth_headers())
    assert r.status_code == 200
    assert "error_rate" in r.json()


async def test_router_requires_auth(client):
    r = await client.get("/analytics/anomalies")
    assert r.status_code == 401
