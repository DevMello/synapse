"""Handlers for the daemon WebSocket channels.

Two channels per daemon (cloud-backend.md §3.1):

  * ``/ws/daemon`` — bidirectional CONTROL channel. Cloud pushes ``CloudMessage``
    command frames down; the daemon pushes ``DaemonMessage`` frames up (acks,
    hitl.request, run.reconcile, ...). At-least-once delivery + idempotency keys +
    seq/acks all live in the JSON envelope (the socket won't redeliver across a
    reconnect).
  * ``/ws/daemon/telemetry`` — a separate high-volume firehose so telemetry can't
    head-of-line-block control/HITL. Inbound frames are dispatched the same way but
    no command delivery rides this channel.

Wire format (JSON):
  cloud -> daemon:  {"type":"command","seq",command_type","payload","idempotency_key"}
  daemon -> cloud:  {"type", "ack"(seq), "seq", "payload"}  — an ack frame carries
                    the seq it acknowledges; any other type is an inbound message
                    that is dispatched to the message_registry, then acked.

The registry/bus singletons are created by ``ws_hub.startup`` and read from there,
so these handlers stay decoupled from construction order.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from .. import message_registry
from ..message_registry import MessageContext
from . import auth
from .connection import ConnectionRegistry


def _get_registry() -> ConnectionRegistry:
    from . import get_registry  # local import to avoid cycles at module load

    registry = get_registry()
    if registry is None:  # pragma: no cover - startup always installs one
        raise RuntimeError("connection registry not initialised; hub not started")
    return registry


def _make_context(principal, payload: dict[str, Any], seq: Any) -> MessageContext:
    payload = payload if isinstance(payload, dict) else {}
    return MessageContext(
        daemon_id=principal.daemon_id,
        org_id=principal.org_id,
        run_id=payload.get("run_id"),
        agent_id=payload.get("agent_id"),
        seq=seq if isinstance(seq, int) else None,
    )


async def _send_ack(ws: WebSocket, seq: Any) -> None:
    """Cloud->daemon ack of an inbound daemon frame (so the daemon can clear its buffer)."""
    if isinstance(seq, int):
        await ws.send_text(json.dumps({"type": "ack", "ack": seq}))


async def _handle_inbound(
    registry: ConnectionRegistry,
    conn,
    principal,
    ws: WebSocket,
    frame: dict[str, Any],
    *,
    is_control: bool,
) -> None:
    """Route one parsed daemon->cloud frame.

    Ack frames clear our pending command buffer (control channel only). Heartbeat/
    ping frames refresh presence. Anything else is dispatched to registered
    handlers, then acked back to the daemon.
    """
    msg_type = frame.get("type")

    # Daemon acking a command we sent (clears at-least-once buffer).
    if msg_type == "ack":
        if is_control and conn is not None:
            ack_seq = frame.get("ack")
            if isinstance(ack_seq, int):
                conn.ack(ack_seq)
        return

    # Transport/health frames refresh the presence TTL.
    if msg_type in ("heartbeat", "ping"):
        await registry.heartbeat(principal.daemon_id, principal.org_id)
        # Reply to an explicit ping so the daemon can measure liveness.
        if msg_type == "ping":
            await ws.send_text(json.dumps({"type": "pong"}))
        return

    if not msg_type:
        return

    # An inbound message (hitl.request, run.reconcile, memory.delta, ...): dispatch
    # to the other units' handlers, then ack so the daemon clears its send buffer.
    payload = frame.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    ctx = _make_context(principal, payload, frame.get("seq"))
    await message_registry.dispatch(msg_type, ctx, payload)
    await _send_ack(ws, frame.get("seq"))


async def _serve(ws: WebSocket, *, is_control: bool) -> None:
    """Shared accept/auth/receive loop for both channels."""
    await ws.accept()
    principal = await auth.authenticate(ws)
    if principal is None:
        return  # auth already closed the socket with 4401

    registry = _get_registry()
    conn = None
    if is_control:
        conn = await registry.connect(principal.daemon_id, principal.org_id, ws)
    else:
        # Telemetry connect still refreshes presence so the daemon shows online.
        await registry.heartbeat(principal.daemon_id, principal.org_id)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except (ValueError, TypeError):
                continue  # ignore malformed frames; don't tear down the link
            if not isinstance(frame, dict):
                continue
            await _handle_inbound(
                registry, conn, principal, ws, frame, is_control=is_control
            )
    except WebSocketDisconnect:
        pass
    finally:
        if is_control:
            await registry.disconnect(principal.daemon_id, conn)


async def control_endpoint(ws: WebSocket) -> None:
    """Handler for ``/ws/daemon`` (bidirectional control + HITL)."""
    await _serve(ws, is_control=True)


async def telemetry_endpoint(ws: WebSocket) -> None:
    """Handler for ``/ws/daemon/telemetry`` (high-volume firehose, off control path)."""
    await _serve(ws, is_control=False)
