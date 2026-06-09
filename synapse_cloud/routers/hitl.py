"""Human-in-the-loop (HITL) REST + inbound request handler.

A daemon pauses an agent run and asks an operator to approve/deny an action by
sending a `hitl.request` control message. We persist it as a `hitl_requests`
row (status 'pending') and fan out a `hitl.request` notification. Operators list
pending requests and resolve them; resolving sends a `hitl.resolve` command back
to the originating daemon and records the decision. Requests that pass their
`expires_at` are swept to 'expired' (default-deny) by the worker cron.

All queries are scoped by `principal.org_id` (service-role client bypasses RLS).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..command_auth import verify_and_sign_command_auth
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import HITL_REQUEST, MessageContext, on_daemon_message
from ..notifications.base import get_notifier

router = APIRouter(prefix="/hitl", tags=["hitl"])

_VALID_STATUSES = {"pending", "approved", "denied", "expired"}
_VALID_DECISIONS = {"approved", "denied"}


# ── request models ────────────────────────────────────────────────────────────
class HITLResolve(BaseModel):
    decision: str = Field(description="'approved' or 'denied'")
    reason: Optional[str] = None
    command_auth_token: Optional[dict[str, Any]] = None  # {envelope, user_sig} from browser


# ── inbound handler: daemon → cloud ───────────────────────────────────────────
@on_daemon_message(HITL_REQUEST)
async def handle_hitl_request(ctx: MessageContext, payload: dict) -> None:
    """Persist a pending HITL request and notify operators."""
    db = await service_db()
    row = (
        await db.table("hitl_requests")
        .insert(
            {
                "org_id": ctx.org_id,
                "daemon_id": ctx.daemon_id,
                "run_id": payload.get("run_id") or ctx.run_id,
                "agent_id": payload.get("agent_id") or ctx.agent_id,
                "action": payload.get("action"),
                "context": payload.get("context") or {},
                "status": "pending",
                "expires_at": payload.get("expires_at"),
            }
        )
        .execute()
    ).data[0]

    await get_notifier().notify(
        ctx.org_id,
        "hitl.request",
        {
            "hitl_id": row["id"],
            "action": row.get("action"),
            "run_id": row.get("run_id"),
            "agent_id": row.get("agent_id"),
            "daemon_id": row.get("daemon_id"),
        },
    )


# ── REST ──────────────────────────────────────────────────────────────────────
@router.get("")
async def list_hitl(
    principal: Principal = Depends(get_principal),
    status_filter: Optional[str] = Query(default=None, alias="status"),
) -> list[dict]:
    """List the org's HITL requests, optionally filtered by status."""
    if status_filter is not None and status_filter not in _VALID_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"status must be one of {sorted(_VALID_STATUSES)}",
        )
    db = await service_db()
    q = (
        db.table("hitl_requests")
        .select("*")
        .eq("org_id", principal.org_id)
    )
    if status_filter is not None:
        q = q.eq("status", status_filter)
    return (await q.order("created_at", desc=True).execute()).data or []


@router.get("/{hitl_id}")
async def get_hitl(
    hitl_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Single HITL request detail, org-scoped (404 if not in caller's org)."""
    db = await service_db()
    rows = (
        await db.table("hitl_requests")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("id", hitl_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hitl request not found")
    return rows[0]


@router.post("/{hitl_id}/resolve")
async def resolve_hitl(
    hitl_id: str, body: HITLResolve, principal: Principal = Depends(require_write)
) -> dict:
    """Approve/deny a pending HITL request and command the daemon.

    Rejects (409) a request that is already resolved or expired.
    """
    if body.decision not in _VALID_DECISIONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"decision must be one of {sorted(_VALID_DECISIONS)}",
        )
    db = await service_db()
    rows = (
        await db.table("hitl_requests")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("id", hitl_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hitl request not found")
    request = rows[0]
    if request["status"] != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"request already {request['status']}",
        )

    updated = (
        await db.table("hitl_requests")
        .update(
            {
                "status": body.decision,
                "resolved_by": principal.user_id,
                "resolution_reason": body.reason,
                "resolved_at": "now()",
            }
        )
        .eq("org_id", principal.org_id)
        .eq("id", hitl_id)
        .eq("status", "pending")
        .execute()
    ).data or []
    if not updated:
        # Lost a race: another resolver/sweeper got here first.
        raise HTTPException(status.HTTP_409_CONFLICT, "request already resolved")
    row = updated[0]

    resolve_payload: dict[str, Any] = {
        "hitl_id": row["id"],
        "run_id": row.get("run_id"),
        "agent_id": row.get("agent_id"),
        "action": row.get("action"),
        "decision": body.decision,
        "reason": body.reason,
    }
    command_auth: Optional[dict[str, Any]] = None
    if body.command_auth_token is not None:
        token = body.command_auth_token
        command_auth = await verify_and_sign_command_auth(
            token.get("envelope") or {},
            token.get("user_sig", ""),
            resolve_payload,
            principal,
            db,
        )
    await get_command_bus().send(
        row["daemon_id"],
        "hitl.resolve",
        resolve_payload,
        idempotency_key=f"hitl.resolve:{row['id']}",
        command_auth=command_auth,
    )
    return row
