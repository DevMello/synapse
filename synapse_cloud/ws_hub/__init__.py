"""WebSocket daemon hub (unit 2).

Owns the daemon control link: the ``/ws/daemon`` (control + HITL) and
``/ws/daemon/telemetry`` channels, device-token handshake auth, the connection
registry (with at-least-once command delivery + presence persistence), and the
real ``DaemonCommandBus`` installed via ``set_command_bus``.

``startup`` instantiates a singleton ConnectionRegistry + WebSocketCommandBus,
installs the bus, and starts the presence-reaper. ``shutdown`` cancels the reaper,
closes live sockets, and restores the default in-memory bus.

CRITICAL: everything here is inert until a real daemon connects — construction
does no I/O and the reaper only runs once started, so the foundation tests in
``SYNAPSE_ENV=test`` (which never open a daemon socket) touch no Redis/server and
behave exactly as before.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ..command_bus import InMemoryCommandBus, set_command_bus
from .connection import ConnectionRegistry, presence_reaper

# Hub singletons, created on startup. Read by the routes + command bus.
_registry: Optional[ConnectionRegistry] = None
_reaper_task: Optional[asyncio.Task] = None
_command_bus = None  # type: ignore[assignment]


def get_registry() -> Optional[ConnectionRegistry]:
    return _registry


def get_command_bus():  # -> Optional[WebSocketCommandBus]
    return _command_bus


async def startup(app=None) -> None:
    """Start the WebSocket hub: install the real bus + start the presence reaper."""
    global _registry, _reaper_task, _command_bus
    # Imported here so the foundation can import ws_hub without pulling the bus.
    from ..command_bus_ws import WebSocketCommandBus

    _registry = ConnectionRegistry()
    _command_bus = WebSocketCommandBus(_registry)
    set_command_bus(_command_bus)
    # The reaper only does DB I/O on its first sweep (after REAPER_INTERVAL),
    # so installing it here stays inert until then.
    _reaper_task = asyncio.create_task(presence_reaper(_registry))


async def shutdown(app=None) -> None:
    """Stop the hub: cancel the reaper, close sockets, restore the default bus."""
    global _registry, _reaper_task, _command_bus
    if _reaper_task is not None:
        _reaper_task.cancel()
        try:
            await _reaper_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _reaper_task = None
    if _registry is not None:
        await _registry.close_all()
        _registry = None
    _command_bus = None
    # Restore the standalone default so post-shutdown callers/tests still work.
    set_command_bus(InMemoryCommandBus())
