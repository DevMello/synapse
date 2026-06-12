"""Native Handoff Protocol — flow publish + chain grants (possible-features §11).

A human authors a chain on the visual **Flow Canvas** (`agent_flows`, edited directly via
the Supabase data API under RLS). **Publishing** compiles the design into a signed,
attenuated **chain grant** (`agent_chain_grants`) — the enforced security artifact. The
cloud signs it (ed25519, reusing §2's key), stores it, and **pushes it to the daemon**,
which verifies + enforces it **locally** (offline). The cloud keeps revoke + the kill
switch and ingests async handoff audit/lineage.

Endpoints (operator+ to write):
  POST /flows/{flow_id}/publish              compile + sign + push the chain grant
  POST /chain-grants/{grant_id}/revoke       revoke + halt the chain

Inbound: `agent.handoff` (daemon → cloud) records audit + the successor-run lineage.

Flow CRUD itself stays a direct Supabase operation in the browser (RLS) — only the
signing publish + revoke + kill-switch need the backend, exactly like §2's grants.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..audit import get_audit
from ..chain_crypto import chain_grant_core, grant_public_key_b64, sign_core
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import MessageContext, on_daemon_message

router = APIRouter(tags=["handoff"])

_VALID_MODES = {"tail", "return"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FlowPublish(BaseModel):
    expires_in_seconds: int = 86_400


async def _get_flow(db, org_id: str, flow_id: str) -> dict:
    rows = (
        await db.table("agent_flows")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", flow_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flow not found")
    return rows[0]


def _compile_edges(flow: dict, agent_by_node: dict[str, str]) -> list[dict[str, Any]]:
    """Translate canvas node→node edges into the grant's agent→agent edge graph.

    Structural nodes (Start/Router/Return/End — anything without a resolved agent) are
    UX-only: edges touching them seed/route at runtime and are dropped from the signed
    grant (H3 lists only real agent→agent handoffs).
    """
    out: list[dict[str, Any]] = []
    for e in flow.get("edges") or []:
        src = agent_by_node.get(str(e.get("from")))
        dst = agent_by_node.get(str(e.get("to")))
        if not src or not dst:
            continue
        mode = str(e.get("mode") or "tail")
        if mode not in _VALID_MODES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid edge mode: {mode}"
            )
        out.append({"from": src, "to": dst, "mode": mode, "when": e.get("when")})
    return out


@router.post("/flows/{flow_id}/publish", status_code=status.HTTP_201_CREATED)
async def publish_flow(
    flow_id: str, body: FlowPublish, principal: Principal = Depends(require_write)
) -> dict:
    """Validate the §11 envelope, compile + sign a chain grant, push it to the daemon."""
    db = await service_db()
    flow = await _get_flow(db, principal.org_id, flow_id)

    daemon_id = flow.get("daemon_id")
    if not daemon_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "flow has no daemon; cannot publish (H2)"
        )

    nodes = flow.get("nodes") or []
    agent_ids = [str(n.get("agent_id")) for n in nodes if n.get("agent_id")]
    agent_by_node: dict[str, str] = {
        str(n.get("id")): str(n.get("agent_id")) for n in nodes if n.get("agent_id")
    }

    # Validate the agent nodes: all on this daemon (H2), none production-tagged (§4).
    if agent_ids:
        agents = (
            await db.table("agents")
            .select("id,daemon_id,tags")
            .eq("org_id", principal.org_id)
            .in_("id", agent_ids)
            .execute()
        ).data or []
        found = {a["id"]: a for a in agents}
        for aid in agent_ids:
            a = found.get(aid)
            if a is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"agent {aid} not found")
            if str(a.get("daemon_id")) != str(daemon_id):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"agent {aid} is on a different daemon (H2: daemon-local only)",
                )
            if "production" in (a.get("tags") or []):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"agent {aid} is production-tagged and cannot be a chain node (§4)",
                )

    edges = _compile_edges(flow, agent_by_node)
    if not edges:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "flow has no agent→agent handoff edges to publish"
        )

    settings = flow.get("settings") or {}
    expires_at = (_now() + timedelta(seconds=int(body.expires_in_seconds))).isoformat()
    modes = sorted({e["mode"] for e in edges} | set(settings.get("modes") or ["tail"]))
    grant_fields = {
        "org_id": principal.org_id,
        "daemon_id": daemon_id,
        "flow_id": flow_id,
        "edges": edges,
        "routing": settings.get("routing", "first_match"),
        "max_hops": int(settings.get("max_hops", 8)),
        "chain_budget_usd": float(settings.get("chain_budget_usd", 5.0)),
        "max_payload_bytes": int(settings.get("max_payload_bytes", 32768)),
        "modes": modes,
        "expires_at": expires_at,
        "key_id": None,
    }
    core = chain_grant_core(grant_fields)
    signature = sign_core(core)

    row = (
        await db.table("agent_chain_grants")
        .insert(
            {
                "org_id": principal.org_id,
                "daemon_id": daemon_id,
                "flow_id": flow_id,
                "granted_by": principal.user_id,
                "edges": edges,
                "routing": core["routing"],
                "max_hops": core["max_hops"],
                "chain_budget_usd": core["chain_budget_usd"],
                "max_payload_bytes": core["max_payload_bytes"],
                "modes": modes,
                "key_id": core["key_id"],
                "signature": signature,
                "expires_at": expires_at,
            }
        )
        .execute()
    ).data[0]

    # Mark the design published + link the compiled grant.
    await (
        db.table("agent_flows")
        .update({"status": "published", "published_grant_id": row["id"], "updated_at": _now().isoformat()})
        .eq("org_id", principal.org_id)
        .eq("id", flow_id)
        .execute()
    )

    # Push the signed grant to the daemon (it verifies + caches; enforces offline).
    await get_command_bus().send(
        daemon_id,
        "chain.grant",
        {
            "grant_id": row["id"],
            "core": core,
            "signature": signature,
            "public_key": grant_public_key_b64(),
        },
        idempotency_key=f"chain.grant:{row['id']}",
    )
    await get_audit().write(
        principal.org_id,
        "chain.publish",
        actor=principal.user_id,
        resource_type="flow",
        resource_id=flow_id,
        detail={"grant_id": row["id"], "daemon_id": daemon_id, "edges": len(edges)},
    )
    return row


@router.post("/chain-grants/{grant_id}/revoke")
async def revoke_chain_grant(
    grant_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Revoke a chain grant and halt its chain on the daemon."""
    db = await service_db()
    rows = (
        await db.table("agent_chain_grants")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("id", grant_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "chain grant not found")
    grant = rows[0]

    updated = (
        await db.table("agent_chain_grants")
        .update({"revoked_at": _now().isoformat()})
        .eq("org_id", principal.org_id)
        .eq("id", grant_id)
        .execute()
    ).data[0]

    daemon_id = grant["daemon_id"]
    await get_command_bus().send(
        daemon_id, "chain.revoke", {"grant_id": grant_id},
        idempotency_key=f"chain.revoke:{grant_id}",
    )
    # Reuse §2's kill switch to cancel any hops still running under this grant.
    await get_command_bus().send(
        daemon_id, "orchestration.halt", {"grant_id": grant_id, "reason": "chain revoked"},
        idempotency_key=f"orchestration.halt:{grant_id}",
    )
    await get_audit().write(
        principal.org_id,
        "chain.revoke",
        actor=principal.user_id,
        resource_type="flow",
        resource_id=grant.get("flow_id"),
        detail={"grant_id": grant_id, "daemon_id": daemon_id},
    )
    return updated


# ── inbound: agent.handoff (audit + successor-run lineage) ───────────────────────
@on_daemon_message("agent.handoff")
async def handle_agent_handoff(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Record a handoff: append audit + the successor-run lineage row.

    Enforcement happened on the daemon (local, H6); this is audit/lineage only (§11.10).
    """
    child_run_id = payload.get("child_run_id")
    to_agent_id = payload.get("to_agent_id")

    await get_audit().write(
        ctx.org_id,
        "agent.handoff",
        actor=f"agent:{payload.get('from_agent_id')}",
        resource_type="agent",
        resource_id=to_agent_id,
        run_id=child_run_id,
        detail={
            "from_agent_id": payload.get("from_agent_id"),
            "grant_id": payload.get("grant_id"),
            "flow_id": payload.get("flow_id"),
            "mode": payload.get("mode"),
            "hop": payload.get("hop"),
            "parent_run_id": payload.get("parent_run_id"),
            "root_run_id": payload.get("root_run_id"),
            "payload_hash": payload.get("payload_hash"),
        },
    )

    if child_run_id and to_agent_id:
        db = await service_db()
        await (
            db.table("runs")
            .upsert(
                {
                    "id": child_run_id,
                    "org_id": ctx.org_id,
                    "agent_id": to_agent_id,
                    "daemon_id": ctx.daemon_id,
                    "trigger": "manual",
                    "status": "running",
                    "initiator": "agent",
                    "initiator_agent_id": payload.get("from_agent_id"),
                    "root_run_id": payload.get("root_run_id"),
                    "parent_run_id": payload.get("parent_run_id"),
                    "depth": int(payload.get("hop", 1)),
                    "hop": int(payload.get("hop", 1)),
                    "handoff_mode": payload.get("mode"),
                    "flow_id": payload.get("flow_id"),
                },
                on_conflict="id",
            )
            .execute()
        )
