"""Agent-orchestration grants (possible-features §2).

An operator mints an **attenuated, signed grant** authorizing one agent to
orchestrate other agents **on its own daemon** (D1). The cloud signs the grant
(ed25519), stores it, and **pushes it to the daemon** which verifies + enforces it
locally; the cloud keeps revoke + the kill switch and ingests async audit/lineage.

Endpoints (operator+ to write):
  POST /agents/{agent_id}/orchestration-grants     mint + sign + push to daemon
  GET  /agents/{agent_id}/orchestration-grants     list (members)
  POST /orchestration-grants/{grant_id}/revoke     revoke + halt the tree

Inbound: `agent.orchestrate` (daemon → cloud) records audit + the child-run lineage.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import MessageContext, on_daemon_message
from ..orchestration_crypto import grant_core, grant_public_key_b64, sign_core

router = APIRouter(tags=["orchestration"])

_VALID_VERBS = {"run", "create", "edit"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GrantCreate(BaseModel):
    verbs: list[str] = Field(default_factory=lambda: ["run"])
    target_allow: list[str] = Field(default_factory=list)
    max_depth: int = 3
    max_fan_out: int = 5
    tree_budget_usd: float = 10.0
    protected_fields: list[str] = Field(
        default_factory=lambda: ["rulesets", "blockers", "env", "capabilities", "grants"]
    )
    expires_in_seconds: int = 86_400


async def _get_agent(db, org_id: str, agent_id: str) -> dict:
    rows = (
        await db.table("agents")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", agent_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    return rows[0]


@router.post("/agents/{agent_id}/orchestration-grants", status_code=status.HTTP_201_CREATED)
async def mint_grant(
    agent_id: str, body: GrantCreate, principal: Principal = Depends(require_write)
) -> dict:
    """Mint + sign an orchestration grant and push it to the agent's daemon."""
    verbs = sorted(set(body.verbs))
    bad = set(verbs) - _VALID_VERBS
    if bad:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid verbs: {sorted(bad)}"
        )
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)
    daemon_id = agent.get("daemon_id")
    if not daemon_id:
        # D1: orchestration is daemon-local; an agent with no daemon has nothing to orchestrate.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "agent has no daemon; cannot grant orchestration"
        )

    expires_at = (_now() + timedelta(seconds=int(body.expires_in_seconds))).isoformat()
    grant_fields = {
        "org_id": principal.org_id,
        "agent_id": agent_id,
        "daemon_id": daemon_id,
        "verbs": verbs,
        "target_allow": body.target_allow,
        "max_depth": body.max_depth,
        "max_fan_out": body.max_fan_out,
        "tree_budget_usd": body.tree_budget_usd,
        "protected_fields": body.protected_fields,
        "expires_at": expires_at,
        "key_id": None,
    }
    core = grant_core(grant_fields)
    signature = sign_core(core)

    row = (
        await db.table("agent_orchestration_grants")
        .insert(
            {
                "org_id": principal.org_id,
                "agent_id": agent_id,
                "daemon_id": daemon_id,
                "granted_by": principal.user_id,
                "verbs": verbs,
                "target_allow": body.target_allow,
                "max_depth": body.max_depth,
                "max_fan_out": body.max_fan_out,
                "tree_budget_usd": body.tree_budget_usd,
                "protected_fields": body.protected_fields,
                "key_id": core["key_id"],
                "signature": signature,
                "expires_at": expires_at,
            }
        )
        .execute()
    ).data[0]

    # Push the signed grant to the daemon (it verifies + caches; enforces offline).
    await get_command_bus().send(
        daemon_id,
        "orchestration.grant",
        {
            "grant_id": row["id"],
            "core": core,
            "signature": signature,
            "public_key": grant_public_key_b64(),
        },
        idempotency_key=f"orchestration.grant:{row['id']}",
    )
    await get_audit().write(
        principal.org_id,
        "grant.mint",
        actor=principal.user_id,
        resource_type="agent",
        resource_id=agent_id,
        detail={"grant_id": row["id"], "daemon_id": daemon_id, "verbs": verbs},
    )
    return row


@router.get("/agents/{agent_id}/orchestration-grants")
async def list_grants(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """List an agent's orchestration grants (newest first)."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    return (
        await db.table("agent_orchestration_grants")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []


@router.post("/orchestration-grants/{grant_id}/revoke")
async def revoke_grant(
    grant_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Revoke a grant and halt its orchestration tree on the daemon."""
    db = await service_db()
    rows = (
        await db.table("agent_orchestration_grants")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("id", grant_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "grant not found")
    grant = rows[0]

    updated = (
        await db.table("agent_orchestration_grants")
        .update({"revoked_at": _now().isoformat()})
        .eq("org_id", principal.org_id)
        .eq("id", grant_id)
        .execute()
    ).data[0]

    daemon_id = grant["daemon_id"]
    await get_command_bus().send(
        daemon_id, "grant.revoke", {"grant_id": grant_id},
        idempotency_key=f"grant.revoke:{grant_id}",
    )
    await get_command_bus().send(
        daemon_id, "orchestration.halt", {"grant_id": grant_id, "reason": "revoked"},
        idempotency_key=f"orchestration.halt:{grant_id}",
    )
    await get_audit().write(
        principal.org_id,
        "grant.revoke",
        actor=principal.user_id,
        resource_type="agent",
        resource_id=grant["agent_id"],
        detail={"grant_id": grant_id, "daemon_id": daemon_id},
    )
    return updated


# ── inbound: agent.orchestrate (audit + child-run lineage) ──────────────────────
@on_daemon_message("agent.orchestrate")
async def handle_agent_orchestrate(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Record an agent-initiated orchestration: append audit + the child-run lineage.

    Enforcement happened on the daemon (local); this is audit/lineage only (§2.7).
    """
    child_run_id = payload.get("child_run_id")
    target_agent_id = payload.get("target_agent_id")

    await get_audit().write(
        ctx.org_id,
        "agent.orchestrate",
        actor=f"agent:{payload.get('initiator_agent_id')}",
        resource_type="agent",
        resource_id=target_agent_id,
        run_id=child_run_id,
        detail={
            "verb": payload.get("verb"),
            "grant_id": payload.get("grant_id"),
            "parent_run_id": payload.get("parent_run_id"),
            "root_run_id": payload.get("root_run_id"),
            "depth": payload.get("depth"),
        },
    )

    if child_run_id and target_agent_id:
        db = await service_db()
        await (
            db.table("runs")
            .upsert(
                {
                    "id": child_run_id,
                    "org_id": ctx.org_id,
                    "agent_id": target_agent_id,
                    "daemon_id": ctx.daemon_id,
                    "trigger": "manual",
                    "status": "running",
                    "initiator": "agent",
                    "initiator_agent_id": payload.get("initiator_agent_id"),
                    "root_run_id": payload.get("root_run_id"),
                    "parent_run_id": payload.get("parent_run_id"),
                    "depth": int(payload.get("depth", 1)),
                },
                on_conflict="id",
            )
            .execute()
        )
