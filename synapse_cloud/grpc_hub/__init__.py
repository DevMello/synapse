"""gRPC daemon hub package (unit 2 owns this package).

The foundation provides no-op `startup`/`shutdown` coroutines so the FastAPI
lifespan can call them unconditionally. Unit 2 implements `server.py`,
`daemon_link.py`, `interceptors.py`, the real `DaemonCommandBus`, and rewrites
these hooks to actually serve gRPC and install the command bus.
"""
from __future__ import annotations


async def startup(app=None) -> None:  # pragma: no cover - overridden by unit 2
    """Start the gRPC hub. No-op until unit 2 implements it."""
    return None


async def shutdown(app=None) -> None:  # pragma: no cover - overridden by unit 2
    """Stop the gRPC hub. No-op until unit 2 implements it."""
    return None
