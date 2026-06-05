"""Daemons REST: list/get registered daemons + derived live status/uptime.

Daemons are devices registered to an org. Their stored `status` column is a
hint; the *live* status is derived from the `daemon_presence` table at read
time: a daemon is `online` when a presence row exists whose `expires_at` is
still in the future, otherwise `offline`. A daemon stamped with `revoked_at` is
always `revoked` regardless of presence.

This unit only READS auth/identity/status fields. Mutation is limited to the
operator-facing `name`/`tags`. Revocation lives in a sibling unit (daemon auth);
there is intentionally no revoke route here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import MessageContext, on_daemon_message

router = APIRouter(prefix="/daemons", tags=["daemons"])

# Inbound daemon→cloud message: the daemon reports its self-configured identity on
# (re)connect (integration.md §2.3).
DAEMON_REGISTER = "daemon.register"


class DaemonUpdate(BaseModel):
    """Mutable daemon fields. Only `name`/`tags` may be changed by callers."""

    name: Optional[str] = Field(default=None, min_length=1)
    tags: Optional[list[str]] = None


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse a Postgres/ISO timestamp string into an aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value)
        # Postgres returns e.g. "2026-06-01T12:00:00+00:00" or with "Z".
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _shape(daemon: dict, presence: Optional[dict]) -> dict:
    """Build the API representation of a daemon with derived live status."""
    now = datetime.now(timezone.utc)

    if daemon.get("revoked_at") is not None:
        live_status = "revoked"
    else:
        expires = _parse_ts(presence.get("expires_at")) if presence else None
        live_status = "online" if (expires is not None and expires > now) else "offline"

    last_heartbeat = presence.get("last_heartbeat") if presence else None
    hb = _parse_ts(last_heartbeat)
    uptime_seconds = int((now - hb).total_seconds()) if hb is not None else None

    return {
        "id": daemon["id"],
        "org_id": daemon["org_id"],
        "name": daemon.get("name"),
        "tags": daemon.get("tags") or [],
        "platform": daemon.get("platform"),
        "version": daemon.get("version"),
        "status": live_status,
        "stored_status": daemon.get("status"),
        "hostname": daemon.get("hostname"),
        "os_version": daemon.get("os_version"),
        "last_ip": daemon.get("last_ip"),
        "last_seen": daemon.get("last_seen"),
        "revoked_at": daemon.get("revoked_at"),
        "created_at": daemon.get("created_at"),
        "last_heartbeat": last_heartbeat,
        "hub_node": presence.get("hub_node") if presence else None,
        "presence_expires_at": presence.get("expires_at") if presence else None,
        "uptime_seconds": uptime_seconds,
    }


async def _presence_by_daemon(db, org_id: str, daemon_ids: list[str]) -> dict[str, dict]:
    if not daemon_ids:
        return {}
    rows = (
        await db.table("daemon_presence")
        .select("*")
        .eq("org_id", org_id)
        .in_("daemon_id", daemon_ids)
        .execute()
    ).data or []
    return {r["daemon_id"]: r for r in rows}


@router.get("")
async def list_daemons(principal: Principal = Depends(get_principal)) -> list[dict]:
    """List the calling org's daemons with derived live status/uptime."""
    db = await service_db()
    daemons = (
        await db.table("daemons")
        .select("*")
        .eq("org_id", principal.org_id)
        .order("created_at")
        .execute()
    ).data or []
    presence = await _presence_by_daemon(
        db, principal.org_id, [d["id"] for d in daemons]
    )
    return [_shape(d, presence.get(d["id"])) for d in daemons]


@router.get("/{daemon_id}")
async def get_daemon(
    daemon_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Single daemon detail, org-scoped (404 if not in caller's org)."""
    db = await service_db()
    rows = (
        await db.table("daemons")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("id", daemon_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "daemon not found")
    presence = await _presence_by_daemon(db, principal.org_id, [daemon_id])
    return _shape(rows[0], presence.get(daemon_id))


@router.patch("/{daemon_id}")
async def update_daemon(
    daemon_id: str,
    body: DaemonUpdate,
    principal: Principal = Depends(require_write),
) -> dict:
    """Update mutable fields (`name`, `tags`) on an org-scoped daemon."""
    db = await service_db()
    existing = (
        await db.table("daemons")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("id", daemon_id)
        .execute()
    ).data or []
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "daemon not found")

    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.tags is not None:
        updates["tags"] = body.tags
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no mutable fields provided")

    updated = (
        await db.table("daemons")
        .update(updates)
        .eq("org_id", principal.org_id)
        .eq("id", daemon_id)
        .execute()
    ).data
    daemon = updated[0] if updated else existing[0]

    await get_audit().write(
        principal.org_id,
        "daemon.update",
        actor=principal.user_id,
        resource_type="daemon",
        resource_id=daemon_id,
        detail=updates,
    )

    presence = await _presence_by_daemon(db, principal.org_id, [daemon_id])
    return _shape(daemon, presence.get(daemon_id))


# ── Inbound daemon message: self-registration on connect (§2.3) ───────────────
@on_daemon_message(DAEMON_REGISTER)
async def handle_daemon_register(ctx: MessageContext, payload: dict) -> None:
    """Apply a daemon's self-reported identity (name/tags/platform/version).

    The daemon emits this on every (re)connect so the `daemons` row reflects its
    current config and packaged version (e.g. after a self-update). Strictly scoped
    to the connecting daemon's own row via ``ctx.daemon_id`` + ``ctx.org_id``. Only
    fields actually present are written, so a partial frame never blanks a column.
    """
    update: dict[str, Any] = {}

    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        update["name"] = name.strip()

    tags = payload.get("tags")
    if isinstance(tags, list):
        update["tags"] = [str(t) for t in tags]

    platform = payload.get("platform")
    if isinstance(platform, str) and platform.strip():
        update["platform"] = platform.strip()

    version = payload.get("version")
    if isinstance(version, str) and version.strip():
        update["version"] = version.strip()

    # X25519 public key the Web UI seals env-var values to (§4.6). Without this the
    # env-var public-key endpoint 404s and no value can ever be encrypted to the daemon.
    e2e_public_key = payload.get("e2e_public_key")
    if isinstance(e2e_public_key, str) and e2e_public_key.strip():
        update["e2e_public_key"] = e2e_public_key.strip()

    if not update:
        return

    db = await service_db()
    await (
        db.table("daemons")
        .update(update)
        .eq("id", ctx.daemon_id)
        .eq("org_id", ctx.org_id)
        .execute()
    )
