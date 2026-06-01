"""Outbound command bus: cloud → daemon.

Feature units push commands (agent.deploy, agent.run, env.set, hitl.resolve, ...)
by calling `get_command_bus().send(...)`. They depend only on this interface.

The real implementation is provided by the gRPC hub (unit 2), which registers
itself via `set_command_bus()` at hub startup. Until then (and in tests) the
default `InMemoryCommandBus` records sent commands so handlers and tests work
standalone.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CommandResult:
    delivered: bool
    queued: bool = False
    error: Optional[str] = None


class DaemonCommandBus(abc.ABC):
    @abc.abstractmethod
    async def send(
        self,
        daemon_id: str,
        command_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
    ) -> CommandResult:
        """Deliver a command to a daemon's Connect stream (at-least-once)."""

    @abc.abstractmethod
    def is_connected(self, daemon_id: str) -> bool:
        ...

    async def close_stream(self, daemon_id: str, reason: str) -> None:
        """Tear down a daemon's stream (e.g. on revocation). Optional."""
        return None


@dataclass
class SentCommand:
    daemon_id: str
    command_type: str
    payload: dict[str, Any]
    idempotency_key: Optional[str] = None


class InMemoryCommandBus(DaemonCommandBus):
    """Default/test bus — records commands; pretends all daemons are reachable."""

    def __init__(self) -> None:
        self.sent: list[SentCommand] = []
        self._connected: set[str] = set()
        self.closed: list[tuple[str, str]] = []

    async def send(self, daemon_id, command_type, payload, *, idempotency_key=None):
        self.sent.append(SentCommand(daemon_id, command_type, dict(payload), idempotency_key))
        return CommandResult(delivered=True)

    def is_connected(self, daemon_id: str) -> bool:
        return True

    def mark_connected(self, daemon_id: str) -> None:
        self._connected.add(daemon_id)

    async def close_stream(self, daemon_id: str, reason: str) -> None:
        self.closed.append((daemon_id, reason))


_bus: DaemonCommandBus = InMemoryCommandBus()


def get_command_bus() -> DaemonCommandBus:
    return _bus


def set_command_bus(bus: DaemonCommandBus) -> None:
    """Install the real (gRPC-backed) bus. Called by the hub at startup."""
    global _bus
    _bus = bus
