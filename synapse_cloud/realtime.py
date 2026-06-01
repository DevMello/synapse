"""Browser fan-out seam: publish events to Supabase Realtime Broadcast channels.

Channels are keyed by tenant + resource, e.g. `org:{id}:agent:{id}` or
`org:{id}:daemon:{id}`. The WebSocket hub and async workers publish here; subscribed
browsers receive via supabase-js. In test mode a fake records published events.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import get_settings


class RealtimePublisher(abc.ABC):
    @abc.abstractmethod
    async def publish(self, channel: str, event: str, payload: dict[str, Any]) -> None:
        ...


@dataclass
class Published:
    channel: str
    event: str
    payload: dict[str, Any]


class FakeRealtimePublisher(RealtimePublisher):
    def __init__(self) -> None:
        self.events: list[Published] = []

    async def publish(self, channel, event, payload):
        self.events.append(Published(channel, event, dict(payload)))


class SupabaseRealtimePublisher(RealtimePublisher):
    """Server-side broadcast via the Realtime REST endpoint (service key)."""

    async def publish(self, channel, event, payload):
        s = get_settings()
        url = f"{s.supabase_url}/realtime/v1/api/broadcast"
        key = s.supabase_service_role_key or s.supabase_anon_key
        body = {"messages": [{"topic": channel, "event": event, "payload": payload}]}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json=body,
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
            )
            resp.raise_for_status()


def org_channel(org_id: str, resource: str, resource_id: str) -> str:
    return f"org:{org_id}:{resource}:{resource_id}"


_publisher: RealtimePublisher | None = None


def get_realtime() -> RealtimePublisher:
    global _publisher
    if _publisher is None:
        _publisher = (
            FakeRealtimePublisher() if get_settings().is_test else SupabaseRealtimePublisher()
        )
    return _publisher


def set_realtime(pub: RealtimePublisher) -> None:
    global _publisher
    _publisher = pub
