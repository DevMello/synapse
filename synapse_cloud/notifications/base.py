"""Notification fan-out seam (spec §7).

Anomaly events, run completion/failure, daemon-offline, HITL requests, and
budget thresholds are delivered to Slack/Discord/Email/in-app via routing rules.
The foundation ships a console/fake notifier; unit 10 provides the real adapters
and installs them via `set_notifier()`.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("synapse.notify")


class Notifier(abc.ABC):
    @abc.abstractmethod
    async def notify(
        self,
        org_id: str,
        event: str,
        payload: dict[str, Any],
        *,
        channels: Optional[list[str]] = None,
    ) -> None:
        """Route an event to the org's configured channels (or `channels`)."""


class ConsoleNotifier(Notifier):
    async def notify(self, org_id, event, payload, *, channels=None):
        log.info("notify org=%s event=%s payload=%s channels=%s", org_id, event, payload, channels)


@dataclass
class SentNotification:
    org_id: str
    event: str
    payload: dict[str, Any]
    channels: Optional[list[str]] = None


class FakeNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[SentNotification] = []

    async def notify(self, org_id, event, payload, *, channels=None):
        self.sent.append(SentNotification(org_id, event, dict(payload), channels))


_notifier: Optional[Notifier] = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        from ..config import get_settings

        _notifier = FakeNotifier() if get_settings().is_test else ConsoleNotifier()
    return _notifier


def set_notifier(n: Notifier) -> None:
    global _notifier
    _notifier = n
