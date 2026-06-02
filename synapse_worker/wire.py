"""The JSON wire envelope — single source of truth for the daemon<->cloud link.

This MUST match the cloud hub exactly (``synapse_cloud/ws_hub/routes.py`` +
``ws_hub/connection.py``). Frame shapes:

  cloud -> daemon (command):
      {"type":"command","seq":N,"command_type":"agent.run",
       "payload":{...},"idempotency_key":"..."}
  daemon -> cloud (ack of a command we received):
      {"type":"ack","ack":N}
  daemon -> cloud (an upstream message: hitl.request, run.reconcile, memory.delta, ...):
      {"type":"<msg>","seq":M,"payload":{...}}
  cloud -> daemon (ack of our upstream message):
      {"type":"ack","ack":M}
  liveness:
      {"type":"heartbeat"} (app-level presence), {"type":"ping"} -> {"type":"pong"}

A WebSocket gives ordered delivery *within* a connection but no redelivery across a
reconnect, so the ``seq`` + ack handshake here (not the transport) is the at-least-once
source of truth.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# Frame "type" values
TYPE_COMMAND = "command"
TYPE_ACK = "ack"
TYPE_HEARTBEAT = "heartbeat"
TYPE_PING = "ping"
TYPE_PONG = "pong"

# Channels
CHANNEL_CONTROL = "control"
CHANNEL_TELEMETRY = "telemetry"


@dataclass
class CloudCommand:
    """A parsed cloud->daemon command frame."""

    seq: Optional[int]
    command_type: str
    payload: dict[str, Any]
    idempotency_key: Optional[str] = None


def parse_frame(raw: str) -> Optional[dict[str, Any]]:
    """Parse one text frame to a dict, or None if it's malformed/non-object."""
    try:
        frame = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return frame if isinstance(frame, dict) else None


def parse_command(frame: dict[str, Any]) -> Optional[CloudCommand]:
    """Extract a CloudCommand from a frame whose type is ``command``."""
    if frame.get("type") != TYPE_COMMAND:
        return None
    payload = frame.get("payload")
    return CloudCommand(
        seq=frame.get("seq") if isinstance(frame.get("seq"), int) else None,
        command_type=str(frame.get("command_type") or ""),
        payload=payload if isinstance(payload, dict) else {},
        idempotency_key=frame.get("idempotency_key"),
    )


def build_ack(seq: int) -> dict[str, Any]:
    return {"type": TYPE_ACK, "ack": seq}


def build_message(msg_type: str, payload: dict[str, Any], seq: int) -> dict[str, Any]:
    """An upstream daemon->cloud message frame (acked by the cloud via its seq)."""
    return {"type": msg_type, "seq": seq, "payload": payload}


def build_heartbeat() -> dict[str, Any]:
    return {"type": TYPE_HEARTBEAT}


def build_ping() -> dict[str, Any]:
    return {"type": TYPE_PING}


def dumps(frame: dict[str, Any]) -> str:
    return json.dumps(frame, separators=(",", ":"))


@dataclass
class SeqCounter:
    """A monotonic per-connection outbound sequence generator (starts at 1)."""

    _counter: "itertools.count" = field(
        default_factory=lambda: itertools.count(1)
    )

    def next(self) -> int:
        return next(self._counter)
