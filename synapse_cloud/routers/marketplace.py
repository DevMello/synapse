"""Marketplace REST: a global catalog of installable artifacts + per-org installs.

`marketplace_listings` is a GLOBAL catalog (no ``org_id``) — any authenticated
principal may browse it. Listing kinds (``listing_kind`` enum): ``agent`` |
``skill`` | ``plugin``.

Installing a listing records a ``marketplace_installs`` row scoped to the
caller's org (``org_id`` + ``installed_by``). An install may target an agent
and/or a daemon (both optional). Installing does NOT itself provision a
capability on a host — that is the capabilities router's two-tier concern; this
just records the catalog selection.

Reads require any org member; the install mutation requires operator+
(``require_write``). The install query is org-scoped because the service-role
client bypasses RLS.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..audit import get_audit
from ..db import service_db
from ..deps import Principal, get_principal, require_write

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


# ── request models ────────────────────────────────────────────────────────────
class InstallRequest(BaseModel):
    agent_id: Optional[str] = None
    daemon_id: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────────
async def _get_listing(db, listing_id: str) -> dict:
    """Fetch a single global listing (no org scope) or 404."""
    rows = (
        await db.table("marketplace_listings")
        .select("*")
        .eq("id", listing_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "listing not found")
    return rows[0]


# ── listings (global catalog) ──────────────────────────────────────────────────
@router.get("/listings")
async def list_listings(
    principal: Principal = Depends(get_principal),
    kind: Optional[str] = Query(default=None, description="filter by listing kind"),
    platform: Optional[str] = Query(default=None, description="filter by platform"),
) -> list[dict]:
    """Browse the global catalog. Readable to any authenticated principal."""
    db = await service_db()
    q = db.table("marketplace_listings").select("*")
    if kind is not None:
        q = q.eq("kind", kind)
    if platform is not None:
        # platforms is a text[] — match listings whose array contains `platform`.
        q = q.contains("platforms", [platform])
    return (await q.order("created_at").execute()).data or []


@router.get("/listings/{listing_id}")
async def get_listing(
    listing_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """A single global listing (404 if absent)."""
    db = await service_db()
    return await _get_listing(db, listing_id)


@router.post("/listings/{listing_id}/install", status_code=status.HTTP_201_CREATED)
async def install_listing(
    listing_id: str,
    body: InstallRequest,
    principal: Principal = Depends(require_write),
) -> dict:
    """Record an install of a catalog listing for the caller's org."""
    db = await service_db()
    await _get_listing(db, listing_id)  # 404 if the listing does not exist

    row = (
        await db.table("marketplace_installs")
        .insert(
            {
                "org_id": principal.org_id,
                "listing_id": listing_id,
                "agent_id": body.agent_id,
                "daemon_id": body.daemon_id,
                "installed_by": principal.user_id,
            }
        )
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "marketplace.install",
        actor=principal.user_id,
        resource_type="marketplace_installs",
        resource_id=row["id"],
        detail={
            "listing_id": listing_id,
            "agent_id": body.agent_id,
            "daemon_id": body.daemon_id,
        },
    )
    return row


@router.get("/installs")
async def list_installs(
    principal: Principal = Depends(get_principal),
) -> list[dict]:
    """List this org's recorded installs (org-scoped)."""
    db = await service_db()
    return (
        await db.table("marketplace_installs")
        .select("*")
        .eq("org_id", principal.org_id)
        .order("created_at")
        .execute()
    ).data or []
