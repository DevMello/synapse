"""Webhooks REST + public ingress.

A *webhook* lets an external system trigger an agent run by POSTing to a public,
unauthenticated URL: ``POST /hooks/{token}``. Management of webhooks
(create/list/delete/toggle) is org-scoped and goes through the normal auth
dependency; only the ingress is public.

Signature scheme
----------------
On create we mint two opaque values:

  * ``token``  — the public, URL path component (lookup key, unique).
  * ``secret`` — returned to the caller **once**. We never store it in the
    clear; we persist ``secret_hash = hash_token(secret)``.

Because only the hash is stored, the HMAC verification key is the ``secret_hash``
itself. The signing contract for callers is therefore:

    signing_key = sha256_hex(secret)          # == the stored secret_hash
    signature   = HMAC_SHA256(signing_key, raw_request_body)
    header      = "X-Synapse-Signature: sha256=" + hex(signature)

Both sides hold ``secret_hash`` (the server stored it; the caller derives it from
the secret it was handed once), so the server can recompute and constant-time
compare the signature without ever persisting the plaintext secret.

On a verified ingress we map the JSON body through the webhook's
``payload_template``, insert a ``runs`` row (trigger='webhook', status='pending')
and dispatch ``agent.run`` to the agent's owning daemon (skipped when the agent
has no ``daemon_id``).

Every authed query is scoped by ``principal.org_id``; the public ingress resolves
the org from the matched webhook row itself.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..security import hash_token, new_opaque_token, tokens_equal
from ..workers.webhooks import (
    apply_payload_template,
    compute_signature,
    parse_signature_header,
)

router = APIRouter(tags=["webhooks"])


# ── request models ────────────────────────────────────────────────────────────
class WebhookCreate(BaseModel):
    payload_template: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class WebhookPatch(BaseModel):
    enabled: Optional[bool] = None
    payload_template: Optional[dict[str, Any]] = None


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


async def _get_webhook(db, org_id: str, webhook_id: str) -> dict:
    rows = (
        await db.table("webhooks")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", webhook_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    return rows[0]


def _public(row: dict) -> dict:
    """Strip the secret hash from a webhook row before returning it."""
    return {k: v for k, v in row.items() if k != "secret_hash"}


# ── management CRUD (org-scoped) ───────────────────────────────────────────────
@router.post(
    "/agents/{agent_id}/webhooks", status_code=status.HTTP_201_CREATED
)
async def create_webhook(
    agent_id: str,
    body: WebhookCreate,
    principal: Principal = Depends(require_write),
) -> dict:
    """Create a webhook for an agent. Returns the signing ``secret`` ONCE."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)

    token = new_opaque_token()
    secret = new_opaque_token()
    secret_hash = hash_token(secret)

    row = (
        await db.table("webhooks")
        .insert(
            {
                "org_id": principal.org_id,
                "agent_id": agent_id,
                "token": token,
                "secret_hash": secret_hash,
                "payload_template": body.payload_template or {},
                "enabled": body.enabled,
            }
        )
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "webhook.create",
        actor=principal.user_id,
        resource_type="webhook",
        resource_id=row["id"],
        detail={"agent_id": agent_id},
    )

    out = _public(row)
    # Returned once and never again — the caller signs with this secret.
    out["secret"] = secret
    return out


@router.get("/agents/{agent_id}/webhooks")
async def list_agent_webhooks(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> list[dict]:
    """List an agent's webhooks (without secret hashes), org-scoped."""
    db = await service_db()
    await _get_agent(db, principal.org_id, agent_id)
    rows = (
        await db.table("webhooks")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("agent_id", agent_id)
        .order("created_at")
        .execute()
    ).data or []
    return [_public(r) for r in rows]


@router.patch("/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: str,
    body: WebhookPatch,
    principal: Principal = Depends(require_write),
) -> dict:
    """Toggle ``enabled`` and/or replace ``payload_template``."""
    db = await service_db()
    await _get_webhook(db, principal.org_id, webhook_id)

    updates: dict[str, Any] = {}
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.payload_template is not None:
        updates["payload_template"] = body.payload_template
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no mutable fields provided")

    updated = (
        await db.table("webhooks")
        .update(updates)
        .eq("org_id", principal.org_id)
        .eq("id", webhook_id)
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "webhook.update",
        actor=principal.user_id,
        resource_type="webhook",
        resource_id=webhook_id,
        detail={k: v for k, v in updates.items() if k == "enabled"},
    )
    return _public(updated)


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Delete a webhook, org-scoped."""
    db = await service_db()
    await _get_webhook(db, principal.org_id, webhook_id)

    await (
        db.table("webhooks")
        .delete()
        .eq("org_id", principal.org_id)
        .eq("id", webhook_id)
        .execute()
    )

    await get_audit().write(
        principal.org_id,
        "webhook.delete",
        actor=principal.user_id,
        resource_type="webhook",
        resource_id=webhook_id,
    )
    return {"deleted": True, "id": webhook_id}


# ── public ingress (NO auth principal) ─────────────────────────────────────────
@router.post("/hooks/{token}")
async def webhook_ingress(
    token: str,
    request: Request,
    x_synapse_signature: Optional[str] = Header(default=None),
) -> dict:
    """External trigger: verify HMAC, create a run, dispatch ``agent.run``.

    Unauthenticated by design — callers prove themselves via the HMAC signature.
    Resolves org/agent from the matched webhook row. 404 if missing/disabled,
    401 on a bad/missing signature.
    """
    db = await service_db()
    rows = (
        await db.table("webhooks").select("*").eq("token", token).execute()
    ).data or []
    webhook = rows[0] if rows else None
    if webhook is None or not webhook.get("enabled"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")

    raw_body = await request.body()

    provided = parse_signature_header(x_synapse_signature)
    # The signing key is the stored secret_hash (see module docstring).
    expected = compute_signature(webhook["secret_hash"], raw_body)
    if provided is None or not tokens_equal(provided, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid signature")

    try:
        body_json = await request.json()
    except Exception:  # noqa: BLE001 - non-JSON / empty body is allowed
        body_json = {}

    mapped = apply_payload_template(webhook.get("payload_template"), body_json)

    org_id = webhook["org_id"]
    agent_id = webhook["agent_id"]
    agent = await _get_agent(db, org_id, agent_id)
    daemon_id = agent.get("daemon_id")

    insert: dict[str, Any] = {
        "org_id": org_id,
        "agent_id": agent_id,
        "trigger": "webhook",
        "status": "pending",
    }
    if daemon_id is not None:
        insert["daemon_id"] = daemon_id

    run = (await db.table("runs").insert(insert).execute()).data[0]
    run_id = run["id"]

    if daemon_id is not None:
        await get_command_bus().send(
            daemon_id,
            "agent.run",
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "trigger": "webhook",
                "input": mapped,
            },
            idempotency_key=run_id,
        )

    await get_audit().write(
        org_id,
        "agent.run",
        resource_type="run",
        resource_id=run_id,
        run_id=run_id,
        detail={
            "agent_id": agent_id,
            "trigger": "webhook",
            "webhook_id": webhook["id"],
            "daemon_id": daemon_id,
            "delivered": daemon_id is not None,
        },
    )
    return {"run_id": run_id, "status": run["status"]}
