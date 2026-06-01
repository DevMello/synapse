"""Daemon WebSocket routes (autodiscovered by the app factory).

Two endpoints, both delegating to handlers in ``ws_hub.routes``:
  * ``/ws/daemon``            — bidirectional control + HITL
  * ``/ws/daemon/telemetry``  — high-volume telemetry firehose

This module only wires the routes; all logic lives in ``ws_hub``.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket

from ..ws_hub import routes as ws_routes

router = APIRouter(tags=["ws-daemon"])


@router.websocket("/ws/daemon")
async def ws_daemon_control(websocket: WebSocket) -> None:
    await ws_routes.control_endpoint(websocket)


@router.websocket("/ws/daemon/telemetry")
async def ws_daemon_telemetry(websocket: WebSocket) -> None:
    await ws_routes.telemetry_endpoint(websocket)
