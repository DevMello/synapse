"""Two-tier capability model: provision per-daemon, then select per-agent.

Capabilities (MCP servers / plugins / system tools) are NEVER installed straight
onto an agent. They flow through two tiers:

  1. **Daemon tier** — provisioning the venv/process on a host. A
     ``daemon_capabilities`` row + a ``plugin.install`` (or ``mcp.configure`` for
     ``kind='mcp'``) command. This makes a capability *available* on the daemon
     but grants no agent any access. ``plugin.remove`` tears it down AND detaches
     it from every agent.

  2. **Agent tier** — toggling which of a daemon's available capabilities each
     agent may use. An ``agent_capabilities`` row + a ``capability.attach`` /
     ``capability.detach`` command. Instant, no re-install.

The daemon reports install progress back via the ``capability.status`` inbound
message, which flips ``daemon_capabilities.install_status`` to ready/failed.

Every query is org-scoped (service-role bypasses RLS) and we verify the
daemon/agent belongs to the caller's org before acting. Mutations require
operator+ (``require_write``).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import CAPABILITY_STATUS, MessageContext, on_daemon_message

router = APIRouter(tags=["capabilities"])

# capability_kind enum: mcp | script | workspace | composite
_VALID_KINDS = {"mcp", "script", "workspace", "composite"}


# ── request models ────────────────────────────────────────────────────────────
class CapabilityProvision(BaseModel):
    kind: str = Field(description="capability kind: mcp | script | workspace | composite")
    plugin_id: Optional[str] = None
    plugin_version: Optional[str] = None
    exposed_tools: list[str] = Field(default_factory=list)
    endpoint: Optional[str] = None
    args: dict[str, Any] = Field(default_factory=dict)


class CapabilityAttach(BaseModel):
    daemon_capability_id: str


# ── helpers ───────────────────────────────────────────────────────────────────
async def _verify_daemon(db, org_id: str, daemon_id: str) -> None:
    rows = (
        await db.table("daemons")
        .select("id")
        .eq("org_id", org_id)
        .eq("id", daemon_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "daemon not found")


async def _get_agent(db, org_id: str, agent_id: str) -> dict:
    rows = (
        await db.table("agents")
        .select("id, daemon_id")
        .eq("org_id", org_id)
        .eq("id", agent_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    return rows[0]


async def _get_daemon_capability(db, org_id: str, cap_id: str) -> dict:
    rows = (
        await db.table("daemon_capabilities")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", cap_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "capability not found")
    return rows[0]


# ── daemon tier ─────────────────────────────────────────────────────────────
@router.get("/daemons/{daemon_id}/capabilities")
async def list_daemon_capabilities(
    daemon_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """List the capabilities provisioned on a daemon (org-scoped)."""
    db = await service_db()
    await _verify_daemon(db, principal.org_id, daemon_id)
    return (
        await db.table("daemon_capabilities")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("daemon_id", daemon_id)
        .order("created_at")
        .execute()
    ).data or []


@router.post("/daemons/{daemon_id}/capabilities", status_code=status.HTTP_201_CREATED)
async def provision_daemon_capability(
    daemon_id: str,
    body: CapabilityProvision,
    principal: Principal = Depends(require_write),
) -> dict:
    """Provision a capability on a daemon (install_status='installing').

    Sends ``mcp.configure`` for ``kind='mcp'`` else ``plugin.install``; the
    daemon reports completion via the ``capability.status`` inbound message.
    """
    if body.kind not in _VALID_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"kind must be one of {sorted(_VALID_KINDS)}",
        )
    db = await service_db()
    await _verify_daemon(db, principal.org_id, daemon_id)

    cap = (
        await db.table("daemon_capabilities")
        .insert(
            {
                "org_id": principal.org_id,
                "daemon_id": daemon_id,
                "plugin_id": body.plugin_id,
                "plugin_version": body.plugin_version,
                "kind": body.kind,
                "install_status": "installing",
                "exposed_tools": body.exposed_tools or [],
                "endpoint": body.endpoint,
                "args": body.args or {},
            }
        )
        .execute()
    ).data[0]

    command_type = "mcp.configure" if body.kind == "mcp" else "plugin.install"
    await get_command_bus().send(
        daemon_id,
        command_type,
        {
            "daemon_capability_id": cap["id"],
            "kind": body.kind,
            "plugin_id": body.plugin_id,
            "plugin_version": body.plugin_version,
            "exposed_tools": body.exposed_tools or [],
            "endpoint": body.endpoint,
            "args": body.args or {},
        },
        idempotency_key=f"{command_type}:{cap['id']}",
    )

    await get_audit().write(
        principal.org_id,
        command_type,
        actor=principal.user_id,
        resource_type="daemon_capabilities",
        resource_id=cap["id"],
        detail={"daemon_id": daemon_id, "kind": body.kind},
    )
    return cap


@router.delete("/daemons/{daemon_id}/capabilities/{cap_id}")
async def remove_daemon_capability(
    daemon_id: str,
    cap_id: str,
    principal: Principal = Depends(require_write),
) -> dict:
    """Tear a capability down on the daemon AND detach it from every agent."""
    db = await service_db()
    await _verify_daemon(db, principal.org_id, daemon_id)
    cap = await _get_daemon_capability(db, principal.org_id, cap_id)
    if cap["daemon_id"] != daemon_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "capability not found")

    await get_command_bus().send(
        daemon_id,
        "plugin.remove",
        {"daemon_capability_id": cap_id},
        idempotency_key=f"plugin.remove:{cap_id}",
    )

    # Detach from ALL agents first (FK + the contract), then drop the daemon row.
    await db.table("agent_capabilities").delete().eq(
        "org_id", principal.org_id
    ).eq("daemon_capability_id", cap_id).execute()
    await db.table("daemon_capabilities").delete().eq(
        "org_id", principal.org_id
    ).eq("id", cap_id).execute()

    await get_audit().write(
        principal.org_id,
        "plugin.remove",
        actor=principal.user_id,
        resource_type="daemon_capabilities",
        resource_id=cap_id,
        detail={"daemon_id": daemon_id},
    )
    return {"deleted": True, "id": cap_id}


# ── agent tier ────────────────────────────────────────────────────────────────
@router.get("/agents/{agent_id}/capabilities")
async def list_agent_capabilities(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """List the capabilities attached to an agent (org-scoped)."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    return (
        await db.table("agent_capabilities")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .order("attached_at")
        .execute()
    ).data or []


@router.post("/agents/{agent_id}/capabilities", status_code=status.HTTP_201_CREATED)
async def attach_agent_capability(
    agent_id: str,
    body: CapabilityAttach,
    principal: Principal = Depends(require_write),
) -> dict:
    """Attach one of the daemon's available capabilities to the agent.

    Upserts the ``agent_capabilities`` row (enabled, user-attached) and sends
    ``capability.attach`` to the agent's owning daemon.
    """
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)
    # The capability must be a real, org-owned daemon capability.
    cap = await _get_daemon_capability(db, principal.org_id, body.daemon_capability_id)

    row = (
        await db.table("agent_capabilities")
        .upsert(
            {
                "org_id": principal.org_id,
                "agent_id": agent_id,
                "daemon_capability_id": body.daemon_capability_id,
                "enabled": True,
                "auto_attached": False,
                "attached_by": principal.user_id,
                "attached_at": "now()",
            },
            on_conflict="agent_id,daemon_capability_id",
        )
        .execute()
    ).data[0]

    # Relay to the agent's owning daemon (fall back to the capability's daemon).
    target_daemon = agent.get("daemon_id") or cap["daemon_id"]
    if target_daemon:
        await get_command_bus().send(
            target_daemon,
            "capability.attach",
            {
                "agent_id": agent_id,
                "daemon_capability_id": body.daemon_capability_id,
            },
            idempotency_key=f"capability.attach:{agent_id}:{body.daemon_capability_id}",
        )

    await get_audit().write(
        principal.org_id,
        "capability.attach",
        actor=principal.user_id,
        resource_type="agent_capabilities",
        resource_id=row["id"],
        detail={
            "agent_id": agent_id,
            "daemon_capability_id": body.daemon_capability_id,
        },
    )
    return row


@router.delete("/agents/{agent_id}/capabilities/{daemon_capability_id}")
async def detach_agent_capability(
    agent_id: str,
    daemon_capability_id: str,
    principal: Principal = Depends(require_write),
) -> dict:
    """Detach a capability from the agent and send ``capability.detach``."""
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)

    rows = (
        await db.table("agent_capabilities")
        .select("id, daemon_capability_id")
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .eq("daemon_capability_id", daemon_capability_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "capability not attached")

    await db.table("agent_capabilities").delete().eq(
        "org_id", principal.org_id
    ).eq("agent_id", agent_id).eq(
        "daemon_capability_id", daemon_capability_id
    ).execute()

    target_daemon = agent.get("daemon_id")
    if not target_daemon:
        cap = (
            await db.table("daemon_capabilities")
            .select("daemon_id")
            .eq("org_id", principal.org_id)
            .eq("id", daemon_capability_id)
            .execute()
        ).data or []
        target_daemon = cap[0]["daemon_id"] if cap else None
    if target_daemon:
        await get_command_bus().send(
            target_daemon,
            "capability.detach",
            {
                "agent_id": agent_id,
                "daemon_capability_id": daemon_capability_id,
            },
            idempotency_key=f"capability.detach:{agent_id}:{daemon_capability_id}",
        )

    await get_audit().write(
        principal.org_id,
        "capability.detach",
        actor=principal.user_id,
        resource_type="agent_capabilities",
        resource_id=daemon_capability_id,
        detail={"agent_id": agent_id},
    )
    return {"detached": True, "daemon_capability_id": daemon_capability_id}


# ── inbound: daemon reports install progress ────────────────────────────────────
@on_daemon_message(CAPABILITY_STATUS)
async def handle_capability_status(ctx: MessageContext, payload: dict) -> None:
    """The daemon reports install progress; flip install_status (org-scoped).

    Payload: ``{"daemon_capability_id": ..., "status": "ready"|"failed",
    "exposed_tools": [...]}``.
    """
    cap_id = payload.get("daemon_capability_id")
    new_status = payload.get("status")
    if not cap_id or new_status not in ("ready", "failed", "installing"):
        return

    updates: dict[str, Any] = {"install_status": new_status, "updated_at": "now()"}
    if "exposed_tools" in payload and payload["exposed_tools"] is not None:
        updates["exposed_tools"] = payload["exposed_tools"]

    db = await service_db()
    await db.table("daemon_capabilities").update(updates).eq(
        "org_id", ctx.org_id
    ).eq("id", cap_id).execute()
