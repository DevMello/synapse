"""Inbound daemon-message handler registry: daemon → cloud.

The gRPC hub (unit 2) receives `Envelope` frames on the Connect stream and
`TelemetryFrame`s on IngestTelemetry, then calls `dispatch(type, ctx, payload)`.
Feature units register handlers without editing the hub:

    from synapse_cloud.message_registry import on_daemon_message

    @on_daemon_message("memory.delta")
    async def handle_memory_delta(ctx: MessageContext, payload: dict):
        ...

Register handlers in a module that your router imports, so router autodiscovery
pulls them in at app startup. Multiple handlers may register for one type.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

# Known inbound message types (daemon → cloud). Units may register others.
HITL_REQUEST = "hitl.request"
MEMORY_DELTA = "memory.delta"
CHECKPOINT = "run.checkpoint"
RUN_RECONCILE = "run.reconcile"
RUN_FINISHED = "run.finished"
CAPABILITY_STATUS = "capability.status"
ENV_VAR_LOCAL = "env.local"


@dataclass
class MessageContext:
    daemon_id: str
    org_id: str
    run_id: str | None = None
    agent_id: str | None = None
    seq: int | None = None


Handler = Callable[[MessageContext, dict[str, Any]], Awaitable[None]]

_handlers: dict[str, list[Handler]] = defaultdict(list)


def on_daemon_message(msg_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _handlers[msg_type].append(fn)
        return fn
    return deco


def register_handler(msg_type: str, fn: Handler) -> None:
    _handlers[msg_type].append(fn)


def handlers_for(msg_type: str) -> list[Handler]:
    return list(_handlers.get(msg_type, []))


async def dispatch(msg_type: str, ctx: MessageContext, payload: dict[str, Any]) -> int:
    """Invoke all handlers for `msg_type`. Returns the number invoked."""
    fns = _handlers.get(msg_type, [])
    for fn in fns:
        await fn(ctx, payload)
    return len(fns)


def clear_handlers() -> None:  # test helper
    _handlers.clear()
