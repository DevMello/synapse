"""Connection Manager (§4.1): dual-channel outbound WebSocket client + real Uplink.

The daemon always *initiates* both sockets (outbound-only; it never listens), so no
inbound port is ever opened. Two channels keep the high-volume telemetry firehose off
the control/HITL path. The public surface:

  * :class:`~synapse_worker.connection.manager.ConnectionManager` — the long-running
    service (``run()`` / ``stop()``) registered via ``commands/connection.py``.
  * :class:`~synapse_worker.connection.uplink_ws.WebSocketUplink` — the real outbound
    uplink (durable-enqueue-then-flush), installed by the manager at startup.
"""
from __future__ import annotations

from .manager import ConnectionManager
from .uplink_ws import WebSocketUplink

__all__ = ["ConnectionManager", "WebSocketUplink"]
