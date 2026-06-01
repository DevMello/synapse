"""Notification channels REST + the real fan-out notifier.

CRUD over `notification_channels` (slack/discord/email/in_app). Mutations require
admin. The `CompositeNotifier` looks up an org's enabled channels, applies each
channel's `routing_rules`, and dispatches the event to the matching adapter
(Slack/Discord/Email; in_app is persisted/logged). It is installed via
`set_notifier()` at import time — but ONLY when not in test mode, so other units'
tests keep asserting against the in-memory `FakeNotifier`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import service_db
from ..deps import Principal, get_principal, require_admin
from ..notifications import discord as discord_adapter
from ..notifications import email as email_adapter
from ..notifications import slack as slack_adapter
from ..notifications.base import Notifier, set_notifier

log = logging.getLogger("synapse.notify.composite")

router = APIRouter(prefix="/notifications", tags=["notifications"])

_VALID_KINDS = {"slack", "discord", "email", "in_app"}


# ── request models ────────────────────────────────────────────────────────────
class ChannelCreate(BaseModel):
    kind: str = Field(description="notification_channel_kind: slack/discord/email/in_app")
    config: dict[str, Any] = Field(default_factory=dict)
    routing_rules: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ChannelUpdate(BaseModel):
    config: Optional[dict[str, Any]] = None
    routing_rules: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None


# ── helpers ─────────────────────────────────────────────────────────────────
async def _get_channel(db, org_id: str, channel_id: str) -> dict:
    rows = (
        await db.table("notification_channels")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", channel_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    return rows[0]


# ── CRUD ────────────────────────────────────────────────────────────────────
@router.post("/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate, principal: Principal = Depends(require_admin)
) -> dict:
    """Create a notification channel for the calling org (admin only)."""
    if body.kind not in _VALID_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"kind must be one of {sorted(_VALID_KINDS)}",
        )
    db = await service_db()
    return (
        await db.table("notification_channels")
        .insert(
            {
                "org_id": principal.org_id,
                "kind": body.kind,
                "config": body.config or {},
                "routing_rules": body.routing_rules or {},
                "enabled": body.enabled,
            }
        )
        .execute()
    ).data[0]


@router.get("/channels")
async def list_channels(principal: Principal = Depends(get_principal)) -> list[dict]:
    """List the calling org's notification channels."""
    db = await service_db()
    return (
        await db.table("notification_channels")
        .select("*")
        .eq("org_id", principal.org_id)
        .order("created_at")
        .execute()
    ).data or []


@router.get("/channels/{channel_id}")
async def get_channel(
    channel_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Single channel detail, org-scoped (404 if not in caller's org)."""
    db = await service_db()
    return await _get_channel(db, principal.org_id, channel_id)


@router.patch("/channels/{channel_id}")
async def update_channel(
    channel_id: str, body: ChannelUpdate, principal: Principal = Depends(require_admin)
) -> dict:
    """Update a channel's config/routing_rules/enabled (admin only)."""
    db = await service_db()
    await _get_channel(db, principal.org_id, channel_id)

    updates: dict[str, Any] = {}
    if body.config is not None:
        updates["config"] = body.config
    if body.routing_rules is not None:
        updates["routing_rules"] = body.routing_rules
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no mutable fields provided")

    return (
        await db.table("notification_channels")
        .update(updates)
        .eq("org_id", principal.org_id)
        .eq("id", channel_id)
        .execute()
    ).data[0]


@router.delete("/channels/{channel_id}")
async def delete_channel(
    channel_id: str, principal: Principal = Depends(require_admin)
) -> dict:
    """Delete a notification channel (admin only)."""
    db = await service_db()
    await _get_channel(db, principal.org_id, channel_id)
    await (
        db.table("notification_channels")
        .delete()
        .eq("org_id", principal.org_id)
        .eq("id", channel_id)
        .execute()
    )
    return {"deleted": True, "id": channel_id}


# ── real fan-out notifier ─────────────────────────────────────────────────────
def _channel_matches(channel: dict, event: str, requested: Optional[list[str]]) -> bool:
    """Decide whether a channel should receive `event`.

    `routing_rules` may carry an `events` allow-list (exact names or prefixes
    ending in `.*`). Absent/empty rules => receive everything. When the caller
    pins explicit `channels` (kinds), only those kinds are considered.
    """
    if requested is not None and channel["kind"] not in requested:
        return False

    rules = channel.get("routing_rules") or {}
    events = rules.get("events")
    if not events:
        return True
    for pattern in events:
        if pattern == event:
            return True
        if pattern.endswith(".*") and event.startswith(pattern[:-1]):
            return True
        if pattern == "*":
            return True
    return False


_ADAPTERS = {
    "slack": slack_adapter.send,
    "discord": discord_adapter.send,
    "email": email_adapter.send,
}


class CompositeNotifier(Notifier):
    """Fans an event out to an org's enabled channels via per-kind adapters."""

    async def notify(self, org_id, event, payload, *, channels=None):
        db = await service_db()
        rows = (
            await db.table("notification_channels")
            .select("*")
            .eq("org_id", org_id)
            .eq("enabled", True)
            .execute()
        ).data or []

        for channel in rows:
            if not _channel_matches(channel, event, channels):
                continue
            kind = channel["kind"]
            if kind == "in_app":
                # In-app delivery is the persisted channel itself; nothing to push.
                log.info("in_app notify org=%s event=%s", org_id, event)
                continue
            adapter = _ADAPTERS.get(kind)
            if adapter is None:
                continue
            try:
                await adapter(channel.get("config") or {}, event, payload)
            except Exception as exc:  # noqa: BLE001 - one bad channel must not block others
                log.warning(
                    "notify failed org=%s kind=%s event=%s err=%s",
                    org_id,
                    kind,
                    event,
                    exc,
                )


# Install the real notifier — but NEVER in test mode (tests assert on FakeNotifier).
if not get_settings().is_test:
    set_notifier(CompositeNotifier())
