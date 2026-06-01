"""Env-var relay — zero-knowledge for VALUES.

The cloud never sees env-var values. The browser fetches the owning daemon's
X25519 public key (`daemons.e2e_public_key`), encrypts each value client-side
with a libsodium sealed box, and POSTs only opaque base64 ciphertext. The cloud
RELAYS that ciphertext to the daemon via an `env.set` command and stores ONLY
the variable NAME + metadata in `env_var_refs` (never the value, never the
ciphertext). Decryption happens on the daemon, which holds the private key.

Locally-set vars (`synapse env set` on the host) are reported by the daemon via
the `env.local` inbound message and recorded as `origin='local'` refs — again,
name only.

All queries are scoped by `principal.org_id` (service-role client bypasses RLS).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import ENV_VAR_LOCAL, MessageContext, on_daemon_message

router = APIRouter(prefix="/agents", tags=["env"])

# Metadata-only projection — explicitly excludes any value/ciphertext (there is
# no such column; this also documents the contract).
_REF_FIELDS = "name, scope, origin, updated_by, updated_at"


# ── request models ──────────────────────────────────────────────────────────
class EnvVarSet(BaseModel):
    name: str = Field(min_length=1)
    ciphertext: str = Field(
        min_length=1,
        description="base64 libsodium sealed box, encrypted to the daemon's pubkey",
    )


# ── helpers ───────────────────────────────────────────────────────────────────
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


# ── inbound handler: daemon → cloud (locally-set var) ──────────────────────────
@on_daemon_message(ENV_VAR_LOCAL)
async def handle_env_local(ctx: MessageContext, payload: dict) -> None:
    """Record a var the daemon set locally on the host. Name only — origin='local'."""
    name = payload.get("name")
    if not name:
        return
    db = await service_db()
    await db.table("env_var_refs").upsert(
        {
            "org_id": ctx.org_id,
            "agent_id": ctx.agent_id,
            "daemon_id": ctx.daemon_id,
            "name": name,
            "origin": "local",
            "updated_by": ctx.daemon_id,
            "updated_at": "now()",
        },
        on_conflict="agent_id,name",
    ).execute()


# ── REST ──────────────────────────────────────────────────────────────────────
@router.get("/{agent_id}/env/public-key")
async def get_env_public_key(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Return the owning daemon's X25519 public key so the browser can encrypt.

    409 if the agent has no daemon; 404 if the daemon has not registered a key.
    """
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)
    daemon_id = agent.get("daemon_id")
    if not daemon_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "agent has no owning daemon")

    rows = (
        await db.table("daemons")
        .select("e2e_public_key")
        .eq("org_id", principal.org_id)
        .eq("id", daemon_id)
        .execute()
    ).data or []
    public_key = rows[0].get("e2e_public_key") if rows else None
    if not public_key:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "daemon has no e2e public key yet"
        )
    return {"daemon_id": daemon_id, "e2e_public_key": public_key}


@router.get("/{agent_id}/env")
async def list_env(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """List env-var refs for the agent — NAMES + metadata only, never values."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    return (
        await db.table("env_var_refs")
        .select(_REF_FIELDS)
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .order("name")
        .execute()
    ).data or []


@router.post("/{agent_id}/env", status_code=status.HTTP_201_CREATED)
async def set_env(
    agent_id: str, body: EnvVarSet, principal: Principal = Depends(require_write)
) -> dict:
    """Relay encrypted value to the daemon and persist NAME-only metadata.

    The ciphertext is sent on the command bus but NEVER written to the DB or
    audit log. 409 if the agent has no owning daemon to relay to.
    """
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)
    daemon_id = agent.get("daemon_id")
    if not daemon_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "agent has no owning daemon")

    # Relay opaque ciphertext to the daemon — not persisted anywhere.
    await get_command_bus().send(
        daemon_id,
        "env.set",
        {"name": body.name, "ciphertext": body.ciphertext},
        idempotency_key=f"env.set:{agent_id}:{body.name}",
    )

    ref = (
        await db.table("env_var_refs")
        .upsert(
            {
                "org_id": principal.org_id,
                "agent_id": agent_id,
                "daemon_id": daemon_id,
                "name": body.name,
                "origin": "ui",
                "updated_by": principal.user_id,
                "updated_at": "now()",
            },
            on_conflict="agent_id,name",
        )
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "env.set",
        actor=principal.user_id,
        resource_type="env_var",
        resource_id=body.name,
        detail={"name": body.name},
    )
    return {
        "name": ref["name"],
        "scope": ref.get("scope"),
        "origin": ref.get("origin"),
        "updated_by": ref.get("updated_by"),
        "updated_at": ref.get("updated_at"),
    }


@router.delete("/{agent_id}/env/{name}")
async def delete_env(
    agent_id: str, name: str, principal: Principal = Depends(require_write)
) -> dict:
    """Command the daemon to unset the var and drop the ref row."""
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)
    daemon_id = agent.get("daemon_id")

    rows = (
        await db.table("env_var_refs")
        .select("id")
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .eq("name", name)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "env var not found")

    if daemon_id:
        await get_command_bus().send(
            daemon_id,
            "env.delete",
            {"name": name},
            idempotency_key=f"env.delete:{agent_id}:{name}",
        )

    await db.table("env_var_refs").delete().eq("org_id", principal.org_id).eq(
        "agent_id", agent_id
    ).eq("name", name).execute()

    await get_audit().write(
        principal.org_id,
        "env.delete",
        actor=principal.user_id,
        resource_type="env_var",
        resource_id=name,
        detail={"name": name},
    )
    return {"deleted": True, "name": name}
