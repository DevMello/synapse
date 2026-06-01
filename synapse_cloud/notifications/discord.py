"""Discord notification adapter.

Posts a message to a Discord webhook URL (from the channel's
`config["webhook_url"]`) via httpx. Discord webhooks accept `{"content": ...}`.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("synapse.notify.discord")


def render_text(event: str, payload: dict[str, Any]) -> str:
    """Render an event + payload into a short Discord message body."""
    parts = [f"**{event}**"]
    for key, value in payload.items():
        parts.append(f"- {key}: {value}")
    return "\n".join(parts)


async def send(config: dict[str, Any], event: str, payload: dict[str, Any]) -> bool:
    """Deliver an event to a Discord webhook. Returns True on success.

    No-op (returns False) when the channel has no webhook_url configured.
    """
    webhook_url = (config or {}).get("webhook_url")
    if not webhook_url:
        log.warning("discord channel missing webhook_url; skipping event=%s", event)
        return False

    body = {"content": render_text(event, payload)}
    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.post(webhook_url, json=body)
        resp.raise_for_status()
    return True
