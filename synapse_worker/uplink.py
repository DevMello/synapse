"""Outbound uplink: daemon -> cloud (the send seam).

Feature units emit upstream frames (run.finished, hitl.request, memory.delta,
capability.status, run.checkpoint, ...) by calling ``get_uplink().send(...)``. They
depend only on this interface.

The real implementation is installed by the Connection Manager unit via
``set_uplink()`` at startup; it durably enqueues into the SQLite outbound queue and
flushes over the WebSocket, replaying in order on reconnect. Until then (and in tests)
the default :class:`InMemoryUplink` just records frames so handlers/tests run
standalone. Mirrors the cloud's ``command_bus`` seam.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Optional

from .wire import CHANNEL_CONTROL, CHANNEL_TELEMETRY

__all__ = [
    "Uplink",
    "InMemoryUplink",
    "SentFrame",
    "get_uplink",
    "set_uplink",
    "reset_uplink",
    "CHANNEL_CONTROL",
    "CHANNEL_TELEMETRY",
]


class Uplink(abc.ABC):
    @abc.abstractmethod
    async def send(
        self,
        msg_type: str,
        payload: dict[str, Any],
        *,
        channel: str = CHANNEL_CONTROL,
        idempotency_key: Optional[str] = None,
    ) -> None:
        """Queue+ship a daemon->cloud frame (durable, at-least-once)."""

    def is_connected(self) -> bool:
        return False


@dataclass
class SentFrame:
    msg_type: str
    payload: dict[str, Any]
    channel: str
    idempotency_key: Optional[str] = None


class InMemoryUplink(Uplink):
    """Default/test uplink — records frames; pretends nothing is connected."""

    def __init__(self) -> None:
        self.sent: list[SentFrame] = []

    async def send(
        self,
        msg_type: str,
        payload: dict[str, Any],
        *,
        channel: str = CHANNEL_CONTROL,
        idempotency_key: Optional[str] = None,
    ) -> None:
        self.sent.append(SentFrame(msg_type, dict(payload), channel, idempotency_key))

    def of_type(self, msg_type: str) -> list[SentFrame]:
        return [f for f in self.sent if f.msg_type == msg_type]


_uplink: Uplink = InMemoryUplink()


def get_uplink() -> Uplink:
    return _uplink


def set_uplink(uplink: Uplink) -> None:
    global _uplink
    _uplink = uplink


def reset_uplink() -> None:  # test helper
    global _uplink
    _uplink = InMemoryUplink()
