"""WebSocket-backed implementation of the outbound command bus.

Feature units call ``get_command_bus().send(...)``; the hub installs this bus at
startup via ``set_command_bus(...)``. It is backed by the ConnectionRegistry:

  * ``send`` looks up the daemon's live control connection and pushes a CloudMessage
    command frame (with idempotency_key), buffered for at-least-once redelivery.
    If the daemon isn't connected, the command is buffered offline and delivered on
    the next reconnect — returning ``CommandResult(delivered=False, queued=True)``.
  * ``is_connected`` reflects whether a live control socket exists.
  * ``close_stream`` tears down a daemon's socket with close code 4401 (e.g. on
    revocation, per cloud-backend.md §5).
"""
from __future__ import annotations

from typing import Any, Optional

from .command_bus import CommandResult, DaemonCommandBus
from .ws_hub.auth import WS_UNAUTHORIZED
from .ws_hub.connection import ConnectionRegistry


class WebSocketCommandBus(DaemonCommandBus):
    def __init__(self, registry: ConnectionRegistry) -> None:
        self._registry = registry

    async def send(
        self,
        daemon_id: str,
        command_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
    ) -> CommandResult:
        conn = self._registry.get(daemon_id)
        if conn is None:
            # Daemon offline: queue for redelivery on reconnect (at-least-once).
            self._registry.buffer_offline_command(
                daemon_id,
                command_type,
                dict(payload),
                idempotency_key=idempotency_key,
            )
            return CommandResult(delivered=False, queued=True)
        try:
            await conn.send_command(
                command_type, dict(payload), idempotency_key=idempotency_key
            )
        except Exception as exc:  # noqa: BLE001 - socket died mid-send
            # Treat as offline: buffer and report it wasn't delivered.
            self._registry.buffer_offline_command(
                daemon_id,
                command_type,
                dict(payload),
                idempotency_key=idempotency_key,
            )
            return CommandResult(delivered=False, queued=True, error=str(exc))
        return CommandResult(delivered=True)

    def is_connected(self, daemon_id: str) -> bool:
        return self._registry.is_connected(daemon_id)

    async def close_stream(self, daemon_id: str, reason: str) -> None:
        conn = self._registry.get(daemon_id)
        if conn is None:
            return
        try:
            await conn.websocket.close(code=WS_UNAUTHORIZED, reason=reason)
        except Exception:  # noqa: BLE001 - best effort
            pass
        await self._registry.disconnect(daemon_id)
