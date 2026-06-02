"""Connection unit wiring (§4.1).

``app.build_daemon`` auto-imports every ``synapse_worker.commands.*`` module, so simply
importing this registers the ``connection`` service factory. ``run_daemon`` then
instantiates it (after the store is open) and gathers its ``run()`` loop.

There are no ``@on_command`` handlers here — the Connection Manager is transport, not a
command target; cloud commands are handled by the feature units that register for them.
"""
from __future__ import annotations

from ..connection.manager import ConnectionManager
from ..services import register_service


@register_service("connection")
def make_connection(daemon):  # (Daemon) -> service with async run()/stop()
    return ConnectionManager(daemon)
