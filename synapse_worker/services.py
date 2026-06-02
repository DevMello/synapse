"""Long-running service registry (the background-task seam).

Some feature units need a coroutine that runs for the daemon's whole lifetime — the
connection loop (§4.1), the scheduler (§4.4), the heartbeat emitter (§6), plugin MCP
supervisors (§4.11). They register a factory here so ``run_daemon`` starts them, without
anyone editing ``app.py``:

    from synapse_worker.services import register_service

    @register_service("connection")
    def make_connection(daemon):
        return ConnectionManager(daemon)   # must expose `async def run(self)`

Register from a module that gets auto-imported (e.g. your ``commands/<unit>.py``), so the
factory is present by the time the daemon assembles. ``run_daemon`` instantiates each
factory after the store is open and gathers every service's ``run()``. A service may also
expose ``async def stop(self)`` for graceful shutdown.
"""
from __future__ import annotations

from typing import Any, Callable

ServiceFactory = Callable[[Any], Any]  # (Daemon) -> service object with async run()

_factories: dict[str, ServiceFactory] = {}


def register_service(name: str) -> Callable[[ServiceFactory], ServiceFactory]:
    def deco(factory: ServiceFactory) -> ServiceFactory:
        _factories[name] = factory
        return factory

    return deco


def service_factories() -> dict[str, ServiceFactory]:
    return dict(_factories)


def clear_services() -> None:  # test helper
    _factories.clear()
