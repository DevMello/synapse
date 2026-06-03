"""Tests for telemetry persist + fan-out (unit 7).

Inbound handlers are driven via the message registry `dispatch`; query endpoints
are exercised through the ASGI client. Realtime/Storage are in-memory fakes in
test mode — assert against their recorded state.
"""
from __future__ import annotations

import base64

from synapse_cloud.db import service_db
from synapse_cloud.message_registry import MessageContext, dispatch
from synapse_cloud.realtime import get_realtime
from synapse_cloud.services import telemetry_ingest
from synapse_cloud.storage import get_storage


async def _make_run(org_id: str) -> tuple[str, str]:
    """Insert an agent + run for an org; return (agent_id, run_id)."""
    db = await service_db()
    agent = (
        await db.table("agents")
        .insert({"org_id": org_id, "name": "tele-agent", "type": "api", "status": "active"})
        .execute()
    ).data[0]
    run = (
        await db.table("runs")
        .insert({"org_id": org_id, "agent_id": agent["id"], "status": "running"})
        .execute()
    ).data[0]
    return agent["id"], run["id"]


def _ctx(daemon_id, org_id, run_id=None, agent_id=None, seq=1) -> MessageContext:
    return MessageContext(
        daemon_id=daemon_id, org_id=org_id, run_id=run_id, agent_id=agent_id, seq=seq
    )


async def test_log_persists_and_republishes(test_org):
    agent_id, run_id = await _make_run(test_org.org_id)
    daemon_id, _ = await test_org.make_daemon()
    before = len(get_realtime().events)

    n = await dispatch(
        telemetry_ingest.TELEMETRY_LOG,
        _ctx(daemon_id, test_org.org_id, run_id, agent_id),
        {"level": "error", "message": "boom", "fields": {"k": "v"}},
    )
    assert n >= 1

    db = await service_db()
    rows = (
        await db.table("logs")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert len(rows) == 1
    assert rows[0]["level"] == "error"
    assert rows[0]["message"] == "boom"
    assert rows[0]["fields"] == {"k": "v"}
    assert rows[0]["daemon_id"] == daemon_id

    events = get_realtime().events[before:]
    assert any(
        e.event == "log" and e.channel == f"org:{test_org.org_id}:run:{run_id}"
        for e in events
    )


async def test_metric_persists(test_org):
    agent_id, run_id = await _make_run(test_org.org_id)
    daemon_id, _ = await test_org.make_daemon()

    await dispatch(
        telemetry_ingest.TELEMETRY_METRIC,
        _ctx(daemon_id, test_org.org_id, run_id, agent_id),
        {"name": "latency_ms", "value": 42.5, "labels": {"phase": "infer"}},
    )

    db = await service_db()
    rows = (
        await db.table("metrics")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert len(rows) == 1
    assert rows[0]["name"] == "latency_ms"
    assert rows[0]["value"] == 42.5
    assert rows[0]["labels"] == {"phase": "infer"}


async def test_trace_inline_persists(test_org):
    agent_id, run_id = await _make_run(test_org.org_id)
    daemon_id, _ = await test_org.make_daemon()

    await dispatch(
        telemetry_ingest.TELEMETRY_TRACE,
        _ctx(daemon_id, test_org.org_id, run_id, agent_id, seq=3),
        {"role": "assistant", "content_redacted": "short thought"},
    )

    db = await service_db()
    rows = (
        await db.table("reasoning_traces")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert len(rows) == 1
    assert rows[0]["content_redacted"] == "short thought"
    assert rows[0]["blob_ref"] is None
    assert rows[0]["seq"] == 3
    assert rows[0]["role"] == "assistant"


async def test_large_trace_goes_to_storage(test_org):
    agent_id, run_id = await _make_run(test_org.org_id)
    daemon_id, _ = await test_org.make_daemon()

    big = "x" * (9 * 1024)
    await dispatch(
        telemetry_ingest.TELEMETRY_TRACE,
        _ctx(daemon_id, test_org.org_id, run_id, agent_id, seq=4),
        {"role": "assistant", "content_redacted": big},
    )

    db = await service_db()
    rows = (
        await db.table("reasoning_traces")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert len(rows) == 1
    ref = rows[0]["blob_ref"]
    assert ref is not None
    assert rows[0]["content_redacted"] is None
    # The fake store keeps blobs keyed by "bucket/key".
    assert ref in get_storage().blobs
    assert get_storage().blobs[ref].decode("utf-8") == big


async def test_trace_blob_field_goes_to_storage(test_org):
    agent_id, run_id = await _make_run(test_org.org_id)
    daemon_id, _ = await test_org.make_daemon()

    raw = b"\x00\x01binary-blob\xff"
    await dispatch(
        telemetry_ingest.TELEMETRY_TRACE,
        _ctx(daemon_id, test_org.org_id, run_id, agent_id, seq=5),
        {"role": "tool", "blob": base64.b64encode(raw).decode("ascii")},
    )

    db = await service_db()
    rows = (
        await db.table("reasoning_traces")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert len(rows) == 1
    ref = rows[0]["blob_ref"]
    assert ref is not None
    assert get_storage().blobs[ref] == raw


async def test_batch_fans_out(test_org):
    agent_id, run_id = await _make_run(test_org.org_id)
    daemon_id, _ = await test_org.make_daemon()

    await dispatch(
        telemetry_ingest.TELEMETRY_BATCH,
        _ctx(daemon_id, test_org.org_id, run_id, agent_id),
        {
            "items": [
                {"type": "telemetry.log", "level": "info", "message": "a"},
                {"type": "telemetry.log", "level": "warn", "message": "b"},
                {"type": "telemetry.metric", "name": "n", "value": 1.0},
            ]
        },
    )

    db = await service_db()
    logs = (
        await db.table("logs")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    metrics = (
        await db.table("metrics")
        .select("*")
        .eq("org_id", test_org.org_id)
        .eq("run_id", run_id)
        .execute()
    ).data
    assert len(logs) == 2
    assert len(metrics) == 1


async def test_no_run_id_skips_realtime(test_org):
    daemon_id, _ = await test_org.make_daemon()
    before = len(get_realtime().events)

    await dispatch(
        telemetry_ingest.TELEMETRY_LOG,
        _ctx(daemon_id, test_org.org_id),  # no run_id
        {"level": "info", "message": "orphan"},
    )

    assert len(get_realtime().events) == before


async def test_query_logs_endpoint(client, test_org):
    agent_id, run_id = await _make_run(test_org.org_id)
    daemon_id, _ = await test_org.make_daemon()

    for i in range(3):
        await dispatch(
            telemetry_ingest.TELEMETRY_LOG,
            _ctx(daemon_id, test_org.org_id, run_id, agent_id),
            {"level": "info" if i < 2 else "error", "message": f"m{i}"},
        )

    resp = await client.get(
        f"/runs/{run_id}/logs", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    # level filter
    resp = await client.get(
        f"/runs/{run_id}/logs?level=error", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["level"] == "error"

    # org-wide telemetry/logs filter by agent_id
    resp = await client.get(
        f"/telemetry/logs?agent_id={agent_id}", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_query_metrics_and_traces_endpoints(client, test_org):
    agent_id, run_id = await _make_run(test_org.org_id)
    daemon_id, _ = await test_org.make_daemon()

    await dispatch(
        telemetry_ingest.TELEMETRY_METRIC,
        _ctx(daemon_id, test_org.org_id, run_id, agent_id),
        {"name": "tokens", "value": 7.0},
    )
    await dispatch(
        telemetry_ingest.TELEMETRY_TRACE,
        _ctx(daemon_id, test_org.org_id, run_id, agent_id, seq=1),
        {"role": "assistant", "content_redacted": "hi"},
    )

    resp = await client.get(
        f"/runs/{run_id}/metrics", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = await client.get(
        f"/runs/{run_id}/traces", headers=test_org.auth_headers()
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_query_is_org_scoped(client, make_test_org):
    org_a = await make_test_org()
    org_b = await make_test_org()
    agent_id, run_id = await _make_run(org_a.org_id)
    daemon_id, _ = await org_a.make_daemon()

    await dispatch(
        telemetry_ingest.TELEMETRY_LOG,
        _ctx(daemon_id, org_a.org_id, run_id, agent_id),
        {"level": "info", "message": "secret"},
    )

    # org B cannot see org A's run logs.
    resp = await client.get(
        f"/runs/{run_id}/logs", headers=org_b.auth_headers()
    )
    assert resp.status_code == 200
    assert resp.json() == []
