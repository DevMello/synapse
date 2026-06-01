"""Agent-memory sync + editor REST (spec unit #13).

The cloud stores a **redacted plaintext** snapshot of each agent's memory under
RLS. Unlike env-vars (zero-knowledge) this subsystem is deliberately NOT
E2E-encrypted: the Web UI must be able to read and edit memory, so the daemon
redacts secrets locally and pushes plaintext-minus-secrets up. Serving that
redacted content back to the UI is the intended behavior.

Flow:
  * The daemon's local store is the source of truth. It pushes redacted deltas up
    via the `memory.delta` inbound message (updated_by='daemon').
  * The UI edits/pre-loads entries through this router (updated_by='ui'). Each
    mutation is persisted AND pushed back to the owning daemon via the
    `memory.sync` command so the daemon applies it to its local store. If the
    agent has no owning daemon, the command is skipped (snapshot-only).

All queries are scoped by `principal.org_id` (the service-role client bypasses
RLS) and verify the agent belongs to the org before touching its memory.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import MEMORY_DELTA, MessageContext, on_daemon_message
from ..services import memory_sync

router = APIRouter(prefix="/agents", tags=["memory"])

# Redacted content IS served to the UI (intended) — full row projection.
_ENTRY_FIELDS = (
    "id, namespace, key, value_redacted, text_redacted, tags, embedding_ref, "
    "version, bytes, updated_by, updated_at"
)


# ── request models ──────────────────────────────────────────────────────────
class MemoryUpsert(BaseModel):
    namespace: str = Field(min_length=1)
    key: str = Field(min_length=1)
    value: Optional[Any] = None
    text: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


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


# ── inbound handler: daemon → cloud (redacted delta) ────────────────────────────
@on_daemon_message(MEMORY_DELTA)
async def handle_memory_delta(ctx: MessageContext, payload: dict) -> None:
    """Absorb a redacted memory delta pushed up by the daemon.

    Payload shape::

        {
          "entries": [
            {"namespace": str, "key": str, "value": json|null,
             "text": str|null, "tags": [str], "bytes": int(optional)}
          ],
          "deletes": [{"namespace": str, "key": str}]
        }

    Upserts each entry (updated_by='daemon', version auto-bumped) and removes any
    listed deletes. Scoped to `ctx.org_id` / `ctx.agent_id`; ignored if either is
    missing.
    """
    if not ctx.org_id or not ctx.agent_id:
        return
    db = await service_db()

    for entry in payload.get("entries") or []:
        namespace = entry.get("namespace")
        key = entry.get("key")
        if not namespace or not key:
            continue
        await memory_sync.upsert_entry(
            db,
            org_id=ctx.org_id,
            agent_id=ctx.agent_id,
            namespace=namespace,
            key=key,
            value=entry.get("value"),
            text=entry.get("text"),
            tags=entry.get("tags") or [],
            updated_by="daemon",
            bytes_override=entry.get("bytes"),
        )

    for d in payload.get("deletes") or []:
        namespace = d.get("namespace")
        key = d.get("key")
        if not namespace or not key:
            continue
        await db.table("agent_memory").delete().eq("org_id", ctx.org_id).eq(
            "agent_id", ctx.agent_id
        ).eq("namespace", namespace).eq("key", key).execute()


# ── REST ──────────────────────────────────────────────────────────────────────
@router.get("/{agent_id}/memory")
async def list_memory(
    agent_id: str,
    principal: Principal = Depends(get_principal),
    namespace: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
) -> list[dict]:
    """List the agent's memory entries (redacted content + metadata).

    Optional `namespace` and `tag` filters. Ordered by updated_at desc.
    """
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)

    q = (
        db.table("agent_memory")
        .select(_ENTRY_FIELDS)
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
    )
    if namespace is not None:
        q = q.eq("namespace", namespace)
    if tag is not None:
        q = q.contains("tags", [tag])
    return (await q.order("updated_at", desc=True).execute()).data or []


@router.get("/{agent_id}/memory/{entry_id}")
async def get_memory_entry(
    agent_id: str, entry_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Fetch a single memory entry (404 if not in caller's org/agent)."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    rows = (
        await db.table("agent_memory")
        .select(_ENTRY_FIELDS)
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .eq("id", entry_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory entry not found")
    return rows[0]


@router.post("/{agent_id}/memory", status_code=status.HTTP_201_CREATED)
async def upsert_memory(
    agent_id: str, body: MemoryUpsert, principal: Principal = Depends(require_write)
) -> dict:
    """Upsert one redacted memory entry (UI edit / knowledge pre-load).

    Persists with updated_by='ui', bumps version, computes bytes, and pushes the
    change to the owning daemon via `memory.sync` (skipped when the agent has no
    daemon).
    """
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)

    row = await memory_sync.upsert_entry(
        db,
        org_id=principal.org_id,
        agent_id=agent_id,
        namespace=body.namespace,
        key=body.key,
        value=body.value,
        text=body.text,
        tags=body.tags,
        updated_by="ui",
    )

    daemon_id = agent.get("daemon_id")
    if daemon_id:
        await get_command_bus().send(
            daemon_id,
            memory_sync.MEMORY_SYNC_COMMAND,
            memory_sync.build_sync_payload(
                agent_id=agent_id,
                namespace=body.namespace,
                key=body.key,
                op="upsert",
                value=body.value,
                text=body.text,
                tags=body.tags,
                version=row["version"],
            ),
            idempotency_key=memory_sync.sync_idempotency_key(
                agent_id, body.namespace, body.key, "upsert"
            ),
        )

    await get_audit().write(
        principal.org_id,
        "memory.upsert",
        actor=principal.user_id,
        resource_type="agent_memory",
        resource_id=row["id"],
        detail={
            "namespace": body.namespace,
            "key": body.key,
            "version": row["version"],
        },
    )
    return row


@router.delete("/{agent_id}/memory/{entry_id}")
async def delete_memory(
    agent_id: str, entry_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Delete a memory entry and push a `memory.sync` delete op to the daemon."""
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)

    rows = (
        await db.table("agent_memory")
        .select("id, namespace, key")
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .eq("id", entry_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory entry not found")
    entry = rows[0]

    await db.table("agent_memory").delete().eq("org_id", principal.org_id).eq(
        "agent_id", agent_id
    ).eq("id", entry_id).execute()

    daemon_id = agent.get("daemon_id")
    if daemon_id:
        await get_command_bus().send(
            daemon_id,
            memory_sync.MEMORY_SYNC_COMMAND,
            memory_sync.build_sync_payload(
                agent_id=agent_id,
                namespace=entry["namespace"],
                key=entry["key"],
                op="delete",
            ),
            idempotency_key=memory_sync.sync_idempotency_key(
                agent_id, entry["namespace"], entry["key"], "delete"
            ),
        )

    await get_audit().write(
        principal.org_id,
        "memory.delete",
        actor=principal.user_id,
        resource_type="agent_memory",
        resource_id=entry_id,
        detail={"namespace": entry["namespace"], "key": entry["key"]},
    )
    return {"deleted": True, "id": entry_id}
