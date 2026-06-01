"""Email notification adapter.

Sends a plaintext email via SMTP using the channel's `config`:
  host, port, username, password, use_tls, from_addr, to (str or list).

Keeps dependencies light — uses the stdlib `smtplib`/`email` modules, run in a
thread so the event loop is not blocked. When no SMTP host is configured the
adapter logs and skips gracefully (returns False) rather than raising.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

log = logging.getLogger("synapse.notify.email")


def render_body(event: str, payload: dict[str, Any]) -> str:
    lines = [f"Event: {event}", ""]
    for key, value in payload.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _recipients(config: dict[str, Any]) -> list[str]:
    to = config.get("to")
    if isinstance(to, str):
        return [to]
    if isinstance(to, (list, tuple)):
        return [str(x) for x in to]
    return []


def _send_sync(config: dict[str, Any], event: str, payload: dict[str, Any]) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"[Synapse] {event}"
    msg["From"] = config.get("from_addr", "synapse@localhost")
    msg["To"] = ", ".join(_recipients(config))
    msg.set_content(render_body(event, payload))

    host = config["host"]
    port = int(config.get("port", 587))
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if config.get("use_tls", True):
            smtp.starttls()
        username = config.get("username")
        password = config.get("password")
        if username and password:
            smtp.login(username, password)
        smtp.send_message(msg)


async def send(config: dict[str, Any], event: str, payload: dict[str, Any]) -> bool:
    """Deliver an event via SMTP. Returns True on success.

    Skips gracefully (returns False) when no SMTP host or no recipients are
    configured, keeping the dependency footprint light for dev/test setups.
    """
    config = config or {}
    if not config.get("host"):
        log.info("email channel has no SMTP host configured; skipping event=%s", event)
        return False
    if not _recipients(config):
        log.warning("email channel has no recipients; skipping event=%s", event)
        return False

    await asyncio.to_thread(_send_sync, config, event, payload)
    return True
