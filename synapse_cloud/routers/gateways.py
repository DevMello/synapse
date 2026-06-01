"""Gateways REST: CRUD over org-scoped gateway definitions.

A *gateway* is a policy-only description of an external channel an agent can use
or be reached through. Four kinds: ``http``, ``queue``, ``mcp``, ``api``. The
``config`` blob holds POLICY ONLY (routing, allow-lists, rate limits, endpoint
shapes) — it MUST NEVER contain credentials; secrets live elsewhere.

Mutations require operator role (``require_write``); reads require any org
member. Every query is scoped by ``principal.org_id`` — the service-role client
bypasses RLS, so org scoping is enforced here.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..db import service_db
from ..deps import Principal, get_principal, require_write

router = APIRouter(prefix="/gateways", tags=["gateways"])

_VALID_KINDS = {"http", "queue", "mcp", "api"}


# ── request models ────────────────────────────────────────────────────────────
class GatewayCreate(BaseModel):
    name: str = Field(min_length=1)
    kind: str = Field(description="gateway kind: http | queue | mcp | api")
    agent_id: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)


class GatewayUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    config: Optional[dict[str, Any]] = None


# ── helpers ─────────────────────────────────────────────────────────────────
def _validate_kind(kind: str) -> None:
    if kind not in _VALID_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"kind must be one of {sorted(_VALID_KINDS)}",
        )


async def _get_gateway(db, org_id: str, gateway_id: str) -> dict:
    rows = (
        await db.table("gateways")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", gateway_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gateway not found")
    return rows[0]


async def _verify_agent(db, org_id: str, agent_id: str) -> None:
    rows = (
        await db.table("agents")
        .select("id")
        .eq("org_id", org_id)
        .eq("id", agent_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")


# ── CRUD ────────────────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_gateway(
    body: GatewayCreate, principal: Principal = Depends(require_write)
) -> dict:
    """Create a gateway (policy-only config; never store credentials)."""
    _validate_kind(body.kind)
    db = await service_db()
    if body.agent_id is not None:
        await _verify_agent(db, principal.org_id, body.agent_id)

    row = (
        await db.table("gateways")
        .insert(
            {
                "org_id": principal.org_id,
                "agent_id": body.agent_id,
                "name": body.name,
                "kind": body.kind,
                "config": body.config or {},
            }
        )
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "gateway.create",
        actor=principal.user_id,
        resource_type="gateway",
        resource_id=row["id"],
        detail={"name": body.name, "kind": body.kind},
    )
    return row


@router.get("")
async def list_gateways(
    principal: Principal = Depends(get_principal),
    agent_id: Optional[str] = Query(default=None),
) -> list[dict]:
    """List the org's gateways, optionally filtered by agent_id."""
    db = await service_db()
    q = db.table("gateways").select("*").eq("org_id", principal.org_id)
    if agent_id is not None:
        q = q.eq("agent_id", agent_id)
    return (await q.order("created_at").execute()).data or []


@router.get("/{gateway_id}")
async def get_gateway(
    gateway_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Single gateway detail, org-scoped (404 if not in caller's org)."""
    db = await service_db()
    return await _get_gateway(db, principal.org_id, gateway_id)


@router.patch("/{gateway_id}")
async def update_gateway(
    gateway_id: str,
    body: GatewayUpdate,
    principal: Principal = Depends(require_write),
) -> dict:
    """Update a gateway's name and/or policy config."""
    db = await service_db()
    await _get_gateway(db, principal.org_id, gateway_id)

    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.config is not None:
        updates["config"] = body.config
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no mutable fields provided")

    updated = (
        await db.table("gateways")
        .update(updates)
        .eq("org_id", principal.org_id)
        .eq("id", gateway_id)
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "gateway.update",
        actor=principal.user_id,
        resource_type="gateway",
        resource_id=gateway_id,
        detail={"name": body.name} if body.name is not None else {},
    )
    return updated


@router.delete("/{gateway_id}")
async def delete_gateway(
    gateway_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Delete a gateway, org-scoped."""
    db = await service_db()
    await _get_gateway(db, principal.org_id, gateway_id)

    await (
        db.table("gateways")
        .delete()
        .eq("org_id", principal.org_id)
        .eq("id", gateway_id)
        .execute()
    )

    await get_audit().write(
        principal.org_id,
        "gateway.delete",
        actor=principal.user_id,
        resource_type="gateway",
        resource_id=gateway_id,
    )
    return {"deleted": True, "id": gateway_id}
