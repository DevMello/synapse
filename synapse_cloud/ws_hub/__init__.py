"""WebSocket daemon hub package (unit 2 owns this package).

The foundation provides no-op `startup`/`shutdown` coroutines so the FastAPI
lifespan can call them unconditionally (e.g. to spin up the in-process
connection registry and a presence-reaper task). Unit 2 implements the daemon
WebSocket routes (`/ws/daemon` control channel + `/ws/daemon/telemetry`), the
device-token auth dependency, the connection registry, and the real
`DaemonCommandBus`, then rewrites these hooks accordingly.
"""
from __future__ import annotations


async def startup(app=None) -> None:  # pragma: no cover - overridden by unit 2
    """Start the WebSocket hub. No-op until unit 2 implements it."""
    return None


async def shutdown(app=None) -> None:  # pragma: no cover - overridden by unit 2
    """Stop the WebSocket hub. No-op until unit 2 implements it."""
    return None
