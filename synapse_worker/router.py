"""Command dispatch registry: cloud -> daemon (§4.2).

Mirrors the cloud's ``message_registry``. Feature units register handlers without
editing the connection loop or this file:

    from synapse_worker.router import on_command, CommandContext

    @on_command("agent.run")
    async def handle_run(ctx: CommandContext, payload: dict):
        ...

Register handlers in a module under ``synapse_worker/commands/`` — ``app.build_daemon``
auto-imports that package so every handler is wired at startup. Multiple handlers may
register for one command type.

Idempotency: the connection loop calls ``should_process(...)`` (store-backed) BEFORE
dispatch, so a redelivered command with the same key runs at most once.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .logging import get_logger

log = get_logger(__name__)


@dataclass
class CommandContext:
    """Identity + envelope metadata for one inbound command.

    Handlers reach the store/uplink/runtime through their module singletons
    (``get_store()``, ``get_uplink()``, ...), so this stays a thin value object.
    """

    command_type: str
    seq: Optional[int] = None
    idempotency_key: Optional[str] = None
    daemon_id: Optional[str] = None
    org_id: Optional[str] = None


Handler = Callable[[CommandContext, dict[str, Any]], Awaitable[None]]

_handlers: dict[str, list[Handler]] = defaultdict(list)


def on_command(command_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _handlers[command_type].append(fn)
        return fn

    return deco


def register_handler(command_type: str, fn: Handler) -> None:
    _handlers[command_type].append(fn)


def handlers_for(command_type: str) -> list[Handler]:
    return list(_handlers.get(command_type, []))


def known_commands() -> list[str]:
    return sorted(_handlers.keys())


async def dispatch(
    command_type: str, ctx: CommandContext, payload: dict[str, Any]
) -> int:
    """Invoke every handler registered for ``command_type``. Returns the count.

    A handler raising is logged and swallowed so one bad command can't tear down
    the control loop; the command is still acked by the caller.
    """
    fns = _handlers.get(command_type, [])
    if not fns:
        log.warning("no handler for command %s", command_type)
        return 0
    for fn in fns:
        try:
            await fn(ctx, payload)
        except Exception:  # noqa: BLE001 - isolate handler failures
            log.exception("handler for %s failed", command_type)
    return len(fns)


async def should_process(idempotency_key: Optional[str], command_type: str) -> bool:
    """True if this command has not been seen before (store-backed dedupe).

    Falls back to ``True`` (process it) if the store isn't available yet, so dispatch
    still works in lightweight unit tests that don't open a store.
    """
    if not idempotency_key:
        return True
    try:
        from .store import get_store

        return await get_store().mark_seen(idempotency_key, command_type)
    except RuntimeError:
        return True


def clear_handlers() -> None:  # test helper
    _handlers.clear()
