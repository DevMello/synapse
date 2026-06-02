"""Daemon assembly + lifecycle.

``build_daemon()`` wires the foundation together and auto-imports every handler module
under ``synapse_worker.commands`` (pkgutil discovery, like the cloud's router
autodiscovery), so feature units register without anyone editing this file. It is
synchronous and side-effect-light (imports + object construction) so the wiring smoke
test ``python -c "from synapse_worker.app import build_daemon; build_daemon()"`` stays
fast and offline.

``run_daemon()`` is the async entrypoint the service runs: it opens the local store,
ensures the on-disk layout, starts the connection (if installed), and blocks until
cancelled.
"""
from __future__ import annotations

import asyncio
import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Optional

from . import commands as _commands_pkg
from .config import Settings, get_settings
from .logging import configure_logging, get_logger
from .paths import WorkerPaths, paths_for
from .services import service_factories
from .store import LocalStore, set_store

log = get_logger(__name__)


def discover_commands() -> list[str]:
    """Import every ``synapse_worker.commands.*`` module so handlers self-register.

    Import failures (e.g. an optional dep missing for one unit) are logged and skipped
    so a single broken module never prevents the daemon from assembling.
    """
    imported: list[str] = []
    for mod in pkgutil.iter_modules(_commands_pkg.__path__):
        name = f"{_commands_pkg.__name__}.{mod.name}"
        try:
            importlib.import_module(name)
            imported.append(name)
        except Exception:  # noqa: BLE001 - one bad unit shouldn't break assembly
            log.exception("failed to import command module %s", name)
    return imported


@dataclass
class Daemon:
    settings: Settings
    paths: WorkerPaths
    store: LocalStore
    commands: list[str] = field(default_factory=list)
    services: dict[str, Any] = field(default_factory=dict)

    def register_service(self, name: str, obj: Any) -> None:
        """Slot for feature units to expose a long-running service to run_daemon."""
        self.services[name] = obj


def build_daemon(settings: Optional[Settings] = None) -> Daemon:
    s = settings or get_settings()
    configure_logging()
    paths = paths_for(s)
    # In test mode the db path is already isolated under $SYNAPSE_HOME (tmp).
    store = LocalStore(paths.db_path)
    set_store(store)
    commands = discover_commands()
    log.debug("daemon assembled with %d command modules", len(commands))
    return Daemon(settings=s, paths=paths, store=store, commands=commands)


async def run_daemon(settings: Optional[Settings] = None) -> None:
    """Open durable state and run until cancelled.

    The Connection Manager unit registers a ``connection`` service (an awaitable run
    loop); if it isn't installed yet the daemon still boots and idles, which keeps the
    foundation runnable on its own.
    """
    daemon = build_daemon(settings)
    daemon.paths.ensure_layout()
    await daemon.store.connect()
    log.info("synapse-worker started (home=%s)", daemon.paths.home)

    # Instantiate every registered long-running service (connection, scheduler,
    # heartbeat, ...) now that the store is open, and gather their run loops.
    runners = []
    for name, factory in service_factories().items():
        try:
            svc = factory(daemon)
        except Exception:  # noqa: BLE001 - a broken service shouldn't sink the daemon
            log.exception("failed to construct service %s", name)
            continue
        daemon.register_service(name, svc)
        run = getattr(svc, "run", None)
        if callable(run):
            runners.append(run())

    try:
        if runners:
            await asyncio.gather(*runners)
        else:
            # No service units installed: idle until cancelled.
            await asyncio.Event().wait()
    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        log.info("synapse-worker shutting down")
        raise
    finally:
        for svc in daemon.services.values():
            stop = getattr(svc, "stop", None)
            if callable(stop):
                try:
                    await stop()
                except Exception:  # noqa: BLE001
                    log.exception("service stop failed")
        await daemon.store.close()
