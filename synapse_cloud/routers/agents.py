"""Agents REST: CRUD + immutable prompt/config versioning.

An agent is an org-scoped definition (api or cli) optionally owned by a daemon.
Its prompt/config live in append-only `agent_versions` snapshots; `agents`
holds mutable operator fields (name/status/limits/daemon_id) plus a pointer to
the live `current_version`.

Versioning is immutable: creating a version, rolling back, never mutate an
existing snapshot — each change appends a new row with a per-agent monotonic
`version`. Deploys and prompt updates push an `agent.deploy` /
`agent.update_prompt` command to the agent's owning daemon (skipped when the
agent has no `daemon_id`).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..services import versioning

router = APIRouter(prefix="/agents", tags=["agents"])

_VALID_TYPES = {"api", "cli"}
_VALID_STATUSES = {"active", "paused", "archived"}


# ── request models ────────────────────────────────────────────────────────────
class AgentCreate(BaseModel):
    name: str = Field(min_length=1)
    type: str = Field(description="agent_type: 'api' or 'cli'")
    platform: Optional[str] = None
    daemon_id: Optional[str] = None
    limits: dict[str, Any] = Field(default_factory=dict)
    # Optional initial version content.
    prompt: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
    deploy: bool = False


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    status: Optional[str] = None
    daemon_id: Optional[str] = None
    limits: Optional[dict[str, Any]] = None


class VersionCreate(BaseModel):
    prompt: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    deploy: bool = False


class VersionPatch(BaseModel):
    """Only tags may be patched on a version; prompt/config are immutable."""

    tags: list[str]


class Rollback(BaseModel):
    version: int


# ── helpers ─────────────────────────────────────────────────────────────────
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


async def _emit_command(
    agent: dict,
    command_type: str,
    version_row: dict,
    *,
    org_id: str,
    actor: Optional[str],
) -> bool:
    """Send agent.deploy / agent.update_prompt to the owning daemon.

    No-op (returns False) when the agent has no owning daemon. Always audits.
    """
    agent_id = agent["id"]
    daemon_id = agent.get("daemon_id")
    version = version_row["version"]

    sent = False
    if daemon_id:
        payload = {
            "agent_id": agent_id,
            "version": version,
            "prompt": version_row.get("prompt"),
            "config": version_row.get("config") or {},
        }
        await get_command_bus().send(
            daemon_id,
            command_type,
            payload,
            idempotency_key=f"{command_type}:{agent_id}:{version}",
        )
        sent = True

    await get_audit().write(
        org_id,
        command_type,
        actor=actor,
        resource_type="agent",
        resource_id=agent_id,
        detail={"version": version, "daemon_id": daemon_id, "delivered": sent},
    )
    return sent


# ── agents CRUD ───────────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate, principal: Principal = Depends(require_write)
) -> dict:
    """Create an agent and its initial (v1) version snapshot."""
    if body.type not in _VALID_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"type must be one of {sorted(_VALID_TYPES)}",
        )
    db = await service_db()

    if body.daemon_id is not None:
        daemon = (
            await db.table("daemons")
            .select("id")
            .eq("org_id", principal.org_id)
            .eq("id", body.daemon_id)
            .execute()
        ).data or []
        if not daemon:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "daemon not found")

    agent = (
        await db.table("agents")
        .insert(
            {
                "org_id": principal.org_id,
                "daemon_id": body.daemon_id,
                "name": body.name,
                "type": body.type,
                "platform": body.platform,
                "limits": body.limits or {},
                "status": "active",
            }
        )
        .execute()
    ).data[0]

    version_row = await versioning.create_version(
        db,
        org_id=principal.org_id,
        agent_id=agent["id"],
        prompt=body.prompt,
        config=body.config,
        author_user_id=principal.user_id,
        message=body.message or "initial version",
    )
    agent["current_version"] = version_row["version"]

    await get_audit().write(
        principal.org_id,
        "agent.create",
        actor=principal.user_id,
        resource_type="agent",
        resource_id=agent["id"],
        detail={"name": body.name, "type": body.type},
    )

    if body.deploy:
        await _emit_command(
            agent,
            "agent.deploy",
            version_row,
            org_id=principal.org_id,
            actor=principal.user_id,
        )

    return agent


@router.get("")
async def list_agents(principal: Principal = Depends(get_principal)) -> list[dict]:
    """List the calling org's agents."""
    db = await service_db()
    return (
        await db.table("agents")
        .select("*")
        .eq("org_id", principal.org_id)
        .order("created_at")
        .execute()
    ).data or []


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Single agent detail, org-scoped (404 if not in caller's org)."""
    db = await service_db()
    return await _get_agent(db, principal.org_id, agent_id)


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: str, body: AgentUpdate, principal: Principal = Depends(require_write)
) -> dict:
    """Update mutable agent fields (name/status/limits/daemon_id).

    Setting `status='archived'` archives the agent. Does not touch versions.
    """
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)

    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"status must be one of {sorted(_VALID_STATUSES)}",
            )
        updates["status"] = body.status
    if body.limits is not None:
        updates["limits"] = body.limits
    if "daemon_id" in body.model_fields_set:
        if body.daemon_id is not None:
            daemon = (
                await db.table("daemons")
                .select("id")
                .eq("org_id", principal.org_id)
                .eq("id", body.daemon_id)
                .execute()
            ).data or []
            if not daemon:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "daemon not found")
        updates["daemon_id"] = body.daemon_id

    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no mutable fields provided")

    updated = (
        await db.table("agents")
        .update(updates)
        .eq("org_id", principal.org_id)
        .eq("id", agent_id)
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "agent.update",
        actor=principal.user_id,
        resource_type="agent",
        resource_id=agent_id,
        detail=updates,
    )
    return updated


# ── versions ──────────────────────────────────────────────────────────────────
@router.get("/{agent_id}/versions")
async def list_agent_versions(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """List an agent's version snapshots, newest first."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    return await versioning.list_versions(db, principal.org_id, agent_id)


@router.post("/{agent_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_agent_version(
    agent_id: str,
    body: VersionCreate,
    principal: Principal = Depends(require_write),
) -> dict:
    """Append a new immutable version (prompt/config/message/tags).

    Emits `agent.update_prompt` to the owning daemon (or `agent.deploy` when
    `deploy=True`); skipped if the agent has no `daemon_id`.
    """
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)

    version_row = await versioning.create_version(
        db,
        org_id=principal.org_id,
        agent_id=agent_id,
        prompt=body.prompt,
        config=body.config,
        author_user_id=principal.user_id,
        message=body.message,
        tags=body.tags,
    )
    agent["current_version"] = version_row["version"]

    command_type = "agent.deploy" if body.deploy else "agent.update_prompt"
    await _emit_command(
        agent,
        command_type,
        version_row,
        org_id=principal.org_id,
        actor=principal.user_id,
    )
    return version_row


@router.get("/{agent_id}/versions/{version}")
async def get_agent_version(
    agent_id: str, version: int, principal: Principal = Depends(get_principal)
) -> dict:
    """Fetch one version snapshot."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    row = await versioning.get_version(db, principal.org_id, agent_id, version)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    return row


@router.patch("/{agent_id}/versions/{version}")
async def patch_agent_version(
    agent_id: str,
    version: int,
    body: VersionPatch,
    principal: Principal = Depends(require_write),
) -> dict:
    """Set/clear tags on a version (e.g. 'known-good', 'production').

    Tags are the only mutable field; prompt/config remain immutable.
    """
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    updated = await versioning.set_version_tags(
        db, principal.org_id, agent_id, version, body.tags
    )
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")

    await get_audit().write(
        principal.org_id,
        "agent.version.tags",
        actor=principal.user_id,
        resource_type="agent",
        resource_id=agent_id,
        detail={"version": version, "tags": body.tags},
    )
    return updated


@router.get("/{agent_id}/versions/{a}/diff/{b}")
async def diff_agent_versions(
    agent_id: str, a: int, b: int, principal: Principal = Depends(get_principal)
) -> dict:
    """Diff prompt/config between two versions (a -> b)."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    va = await versioning.get_version(db, principal.org_id, agent_id, a)
    vb = await versioning.get_version(db, principal.org_id, agent_id, b)
    if va is None or vb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    return versioning.diff_versions(va, vb)


@router.post("/{agent_id}/rollback", status_code=status.HTTP_201_CREATED)
async def rollback_agent(
    agent_id: str, body: Rollback, principal: Principal = Depends(require_write)
) -> dict:
    """One-click rollback: append a NEW version copying the target's
    prompt/config (history stays append-only), bump current_version, and emit
    `agent.update_prompt`."""
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)

    target = await versioning.get_version(db, principal.org_id, agent_id, body.version)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")

    version_row = await versioning.create_version(
        db,
        org_id=principal.org_id,
        agent_id=agent_id,
        prompt=target.get("prompt"),
        config=target.get("config") or {},
        author_user_id=principal.user_id,
        message=f"rollback to v{body.version}",
    )
    agent["current_version"] = version_row["version"]

    await get_audit().write(
        principal.org_id,
        "agent.rollback",
        actor=principal.user_id,
        resource_type="agent",
        resource_id=agent_id,
        detail={"to_version": body.version, "new_version": version_row["version"]},
    )

    await _emit_command(
        agent,
        "agent.update_prompt",
        version_row,
        org_id=principal.org_id,
        actor=principal.user_id,
    )
    return version_row
