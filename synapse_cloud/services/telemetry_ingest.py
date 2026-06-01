"""Inbound telemetry-frame handlers: persist + fan out to browsers.

Daemons stream telemetry over the WebSocket telemetry channel
(`/ws/daemon/telemetry`, owned by unit 2). The hub dispatches every inbound
frame through the message registry:

    await dispatch(frame["type"], ctx, frame["payload"])

This module registers handlers for the telemetry frame types and:
  1. Persists each frame to its partitioned table (`logs`, `metrics`,
     `reasoning_traces`) — service-role, so `org_id` is stamped from `ctx`.
  2. For large reasoning-trace content (or an explicit `blob` field) it offloads
     to the `traces` Storage bucket and stores the returned ref in `blob_ref`
     instead of the inline content.
  3. Republishes to Supabase Realtime so subscribed browsers see live telemetry
     on the run channel (`org:{org}:run:{run}`).

The `telemetry.batch` frame carries `{"items": [{type, ...}, ...]}` and fans
each item to the matching handler.

Registered here so the autodiscovered `routers.telemetry` import pulls these
handlers in at app startup.
"""
from __future__ import annotations

import base64
import uuid
from typing import Any, Optional

from ..db import service_db
from ..message_registry import MessageContext, dispatch, on_daemon_message
from ..realtime import get_realtime, org_channel
from ..storage import TRACES, get_storage

# Inbound telemetry frame-type strings. This unit owns these constants — no
# foundation constant exists for them.
TELEMETRY_LOG = "telemetry.log"
TELEMETRY_METRIC = "telemetry.metric"
TELEMETRY_TRACE = "telemetry.trace"
TELEMETRY_BATCH = "telemetry.batch"

# Reasoning-trace content above this byte threshold is offloaded to Storage.
_TRACE_INLINE_LIMIT = 8 * 1024


async def _publish(org_id: str, run_id: Optional[str], event: str, payload: dict[str, Any]) -> None:
    """Fan a persisted telemetry event out to the run's Realtime channel.

    No-op when `run_id` is None (telemetry not tied to a run).
    """
    if not run_id:
        return
    await get_realtime().publish(org_channel(org_id, "run", run_id), event, payload)


@on_daemon_message(TELEMETRY_LOG)
async def handle_log(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Persist a log line and republish it to the run channel."""
    run_id = ctx.run_id or payload.get("run_id")
    agent_id = ctx.agent_id or payload.get("agent_id")
    row: dict[str, Any] = {
        "org_id": ctx.org_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "daemon_id": ctx.daemon_id,
        "level": payload.get("level", "info"),
        "message": payload.get("message", ""),
        "fields": payload.get("fields") or {},
    }
    db = await service_db()
    inserted = (await db.table("logs").insert(row).execute()).data or [row]
    await _publish(ctx.org_id, run_id, "log", inserted[0])


@on_daemon_message(TELEMETRY_METRIC)
async def handle_metric(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Persist a metric sample and republish it to the run channel."""
    run_id = ctx.run_id or payload.get("run_id")
    agent_id = ctx.agent_id or payload.get("agent_id")
    row: dict[str, Any] = {
        "org_id": ctx.org_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "daemon_id": ctx.daemon_id,
        "name": payload.get("name", ""),
        "value": payload.get("value"),
        "labels": payload.get("labels") or {},
    }
    db = await service_db()
    inserted = (await db.table("metrics").insert(row).execute()).data or [row]
    await _publish(ctx.org_id, run_id, "metric", inserted[0])


def _decode_blob(blob: Any) -> Optional[bytes]:
    """Coerce an inbound `blob` field (base64 str or raw bytes) to bytes."""
    if blob is None:
        return None
    if isinstance(blob, (bytes, bytearray)):
        return bytes(blob)
    if isinstance(blob, str):
        try:
            return base64.b64decode(blob)
        except Exception:  # noqa: BLE001 - fall back to raw utf-8 bytes
            return blob.encode("utf-8")
    return None


@on_daemon_message(TELEMETRY_TRACE)
async def handle_trace(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Persist a reasoning trace, offloading large content/blobs to Storage."""
    run_id = ctx.run_id or payload.get("run_id")
    agent_id = ctx.agent_id or payload.get("agent_id")
    seq = ctx.seq if ctx.seq is not None else payload.get("seq")
    content = payload.get("content_redacted")
    if content is None:
        content = payload.get("content")

    row: dict[str, Any] = {
        "org_id": ctx.org_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "seq": seq,
        "role": payload.get("role"),
    }

    blob_bytes = _decode_blob(payload.get("blob"))
    content_bytes = content.encode("utf-8") if isinstance(content, str) else None
    too_large = content_bytes is not None and len(content_bytes) > _TRACE_INLINE_LIMIT

    if blob_bytes is not None or too_large:
        data = blob_bytes if blob_bytes is not None else content_bytes
        content_type = "application/octet-stream" if blob_bytes is not None else "text/plain"
        key = f"{ctx.org_id}/{run_id or 'none'}/{uuid.uuid4().hex}"
        ref = await get_storage().put(TRACES, key, data, content_type)
        row["blob_ref"] = ref
    else:
        row["content_redacted"] = content

    db = await service_db()
    inserted = (await db.table("reasoning_traces").insert(row).execute()).data or [row]
    await _publish(ctx.org_id, run_id, "trace", inserted[0])


# Maps batch item types to their handlers.
_ITEM_HANDLERS = {
    TELEMETRY_LOG: handle_log,
    TELEMETRY_METRIC: handle_metric,
    TELEMETRY_TRACE: handle_trace,
}


@on_daemon_message(TELEMETRY_BATCH)
async def handle_batch(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Fan each item in a batch frame to the matching telemetry handler.

    Each item is `{"type": "telemetry.log"|..., ...rest}`. Unknown item types
    are re-dispatched through the registry so any other unit's handler still
    fires; the `type` key is stripped from the item payload.
    """
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        item_payload = {k: v for k, v in item.items() if k != "type"}
        handler = _ITEM_HANDLERS.get(item_type)
        if handler is not None:
            await handler(ctx, item_payload)
        elif item_type:
            await dispatch(item_type, ctx, item_payload)
