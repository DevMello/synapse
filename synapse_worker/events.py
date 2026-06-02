"""In-process async event bus (fan-out to local subscribers).

The Agent Runtime publishes trace/log/status events here; the Textual TUI subscribes to
render the live pane without coupling to the runtime. This is purely local — distinct
from the :mod:`uplink`, which ships frames to the cloud.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Event:
    kind: str                      # e.g. "trace", "log", "run.status", "hitl"
    data: dict[str, Any] = field(default_factory=dict)
    run_id: Optional[str] = None
    agent_id: Optional[str] = None


class EventBus:
    """Multi-subscriber broadcast. Each subscriber gets its own bounded queue."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def publish(self, event: Event) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer: drop the oldest, then enqueue the newest.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


_bus: EventBus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


def reset_event_bus() -> None:  # test helper
    global _bus
    _bus = EventBus()
