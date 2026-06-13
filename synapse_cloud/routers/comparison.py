"""Model Comparison Runs — launch / cancel / select-winner / promote (possible-features §10).

A human launches a one-off "Compare models" run to evaluate how different LLMs handle the
*same* task. This router owns the cloud side:

  GET  /agents/{agent_id}/comparison-models    models + per-model cost estimate (§10.9)
  POST /agents/{agent_id}/comparisons          create a run_group + push `agent.compare`
  POST /comparisons/{group_id}/cancel          stop all variants (`comparison.cancel`)
  POST /comparisons/{group_id}/winner          mark the winning variant (§10.7)
  POST /comparisons/{group_id}/promote         re-run the winner LIVE (fresh normal run, E4)

Inbound (daemon → cloud): `comparison.variant_finished` tags each variant `run` with its
group + model + draft-mode tool calls; `comparison.group_ready` flips the group to
``ready_for_review`` and rolls up the total cost.

There is **no signed grant** here (§10.4): comparison is a human-driven evaluation tool, not
a new principal. Every query is org-scoped (the service-role client bypasses RLS).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..comparison_pricing import (
    DEFAULT_INPUT_TOKENS,
    DEFAULT_OUTPUT_TOKENS,
    estimate_group,
    known_models,
    provider_of,
)
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import MessageContext, on_daemon_message

router = APIRouter(tags=["comparison"])

# Env var names that prove a provider's credentials exist on a daemon (§10.9).
_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

_VARIANT_STATUS = {"succeeded", "failed", "skipped", "running"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CompareCreate(BaseModel):
    models: list[str] = Field(min_length=1)
    input: Optional[dict[str, Any]] = None
    group_cost_cap: Optional[float] = Field(default=None, ge=0)
    max_parallel_variants: int = Field(default=3, ge=1, le=16)


class WinnerSelect(BaseModel):
    run_id: str


async def _get_agent(db, org_id: str, agent_id: str) -> dict:
    rows = (
        await db.table("agents").select("*").eq("org_id", org_id).eq("id", agent_id).execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    return rows[0]


async def _get_group(db, org_id: str, group_id: str) -> dict:
    rows = (
        await db.table("run_groups").select("*").eq("org_id", org_id).eq("id", group_id).execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "comparison group not found")
    return rows[0]


async def _provider_creds(db, org_id: str, daemon_id: Optional[str]) -> set[str]:
    """Providers whose key exists on this daemon (per-agent or shared, §10.9)."""
    if not daemon_id:
        return set()
    names = list(_PROVIDER_KEY_ENV.values())
    rows = (
        await db.table("env_var_refs")
        .select("name")
        .eq("org_id", org_id)
        .eq("daemon_id", daemon_id)
        .in_("name", names)
        .execute()
    ).data or []
    present = {r["name"] for r in rows}
    return {prov for prov, env in _PROVIDER_KEY_ENV.items() if env in present}


def _validate_api_agent(agent: dict) -> None:
    """API agents only (E5); never compare a production-tagged agent by default (§10.1)."""
    if str(agent.get("type")) != "api":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "model comparison is API-agents-only in v1 (E5)"
        )
    tags = agent.get("tags") or []
    if isinstance(tags, list) and "production" in tags:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "production-tagged agents are excluded from comparison runs by default (§10.1)",
        )


# ── GET available models + estimate ──────────────────────────────────────────
@router.get("/agents/{agent_id}/comparison-models")
async def list_comparison_models(
    agent_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """The model catalog with per-model price estimate + whether creds exist (§10.9)."""
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)
    creds = await _provider_creds(db, principal.org_id, agent.get("daemon_id"))
    catalog = known_models()
    est = estimate_group([m["model"] for m in catalog])
    by_model = {e["model"]: e for e in est["per_model"]}
    out = []
    for m in catalog:
        out.append(
            {
                **m,
                "has_credentials": m["provider"] in creds,
                "estimate_usd": by_model.get(m["model"], {}).get("cost_usd", 0.0),
            }
        )
    return {
        "agent_id": agent_id,
        "models": out,
        "estimate_basis": {"input_tokens": DEFAULT_INPUT_TOKENS, "output_tokens": DEFAULT_OUTPUT_TOKENS},
    }


# ── POST launch comparison ───────────────────────────────────────────────────
@router.post("/agents/{agent_id}/comparisons", status_code=status.HTTP_201_CREATED)
async def launch_comparison(
    agent_id: str, body: CompareCreate, principal: Principal = Depends(require_write)
) -> dict:
    """Create the run_group, compute the N× estimate, and push `agent.compare`."""
    db = await service_db()
    agent = await _get_agent(db, principal.org_id, agent_id)
    _validate_api_agent(agent)

    daemon_id = agent.get("daemon_id")
    if not daemon_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "agent has no daemon; cannot compare")

    estimate = estimate_group(body.models)

    row = (
        await db.table("run_groups")
        .insert(
            {
                "org_id": principal.org_id,
                "agent_id": agent_id,
                "agent_version": agent.get("current_version"),
                "daemon_id": daemon_id,
                "input": body.input or {},
                "selected_models": body.models,
                "status": "running",
                "group_cost_cap": body.group_cost_cap,
                "max_parallel_variants": body.max_parallel_variants,
                "created_by": principal.user_id,
            }
        )
        .execute()
    ).data[0]
    group_id = row["id"]

    await get_command_bus().send(
        daemon_id,
        "agent.compare",
        {
            "group_id": group_id,
            "agent_id": agent_id,
            "models": body.models,
            "input": body.input or {},
            "group_cost_cap": body.group_cost_cap,
            "max_parallel_variants": body.max_parallel_variants,
        },
        idempotency_key=f"agent.compare:{group_id}",
    )
    await get_audit().write(
        principal.org_id,
        "comparison.launched",
        actor=principal.user_id,
        resource_type="run_group",
        resource_id=group_id,
        detail={"agent_id": agent_id, "models": body.models, "estimate_usd": estimate["total_usd"]},
    )
    return {**row, "estimate": estimate}


# ── POST cancel ──────────────────────────────────────────────────────────────
@router.post("/comparisons/{group_id}/cancel")
async def cancel_comparison(
    group_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Stop all variants of a comparison group (§10.11)."""
    db = await service_db()
    group = await _get_group(db, principal.org_id, group_id)

    updated = (
        await db.table("run_groups")
        .update({"status": "closed", "updated_at": _now()})
        .eq("org_id", principal.org_id)
        .eq("id", group_id)
        .execute()
    ).data[0]

    if group.get("daemon_id"):
        await get_command_bus().send(
            group["daemon_id"],
            "comparison.cancel",
            {"group_id": group_id},
            idempotency_key=f"comparison.cancel:{group_id}",
        )
    await get_audit().write(
        principal.org_id,
        "comparison.cancelled",
        actor=principal.user_id,
        resource_type="run_group",
        resource_id=group_id,
        detail={},
    )
    return updated


# ── POST select winner ───────────────────────────────────────────────────────
@router.post("/comparisons/{group_id}/winner")
async def select_winner(
    group_id: str, body: WinnerSelect, principal: Principal = Depends(require_write)
) -> dict:
    """Mark one variant the winner; record the selection (§10.7)."""
    db = await service_db()
    group = await _get_group(db, principal.org_id, group_id)

    # The winning run must belong to this group.
    winner = (
        await db.table("runs")
        .select("id,variant_model,run_group_id")
        .eq("org_id", principal.org_id)
        .eq("id", body.run_id)
        .eq("run_group_id", group_id)
        .execute()
    ).data or []
    if not winner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant run not found in this group")

    # Clear any prior winner in the group, then set the new one.
    await (
        db.table("runs")
        .update({"is_winner": False})
        .eq("org_id", principal.org_id)
        .eq("run_group_id", group_id)
        .eq("is_winner", True)
        .execute()
    )
    await (
        db.table("runs")
        .update({"is_winner": True})
        .eq("org_id", principal.org_id)
        .eq("id", body.run_id)
        .execute()
    )
    updated = (
        await db.table("run_groups")
        .update({"winner_run_id": body.run_id, "status": "closed", "updated_at": _now()})
        .eq("org_id", principal.org_id)
        .eq("id", group_id)
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "winner.selected",
        actor=principal.user_id,
        resource_type="run_group",
        resource_id=group_id,
        run_id=body.run_id,
        detail={"variant_model": winner[0].get("variant_model")},
    )
    return updated


# ── POST promote winner to a live run (E4) ───────────────────────────────────
@router.post("/comparisons/{group_id}/promote", status_code=status.HTTP_201_CREATED)
async def promote_winner(
    group_id: str, principal: Principal = Depends(require_write)
) -> dict:
    """Launch a FRESH, single-model, normal run of the winner with live tools (E4).

    This is a clean live re-run, not a replay of the simulated variant (§10.7). The
    comparison group itself stays a read-only test artifact.
    """
    db = await service_db()
    group = await _get_group(db, principal.org_id, group_id)
    winner_run_id = group.get("winner_run_id")
    if not winner_run_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no winner selected for this group")

    winner = (
        await db.table("runs")
        .select("variant_model")
        .eq("org_id", principal.org_id)
        .eq("id", winner_run_id)
        .execute()
    ).data or []
    variant_model = winner[0].get("variant_model") if winner else None
    daemon_id = group.get("daemon_id")
    agent_id = group["agent_id"]

    run = (
        await db.table("runs")
        .insert(
            {
                "org_id": principal.org_id,
                "agent_id": agent_id,
                "daemon_id": daemon_id,
                "trigger": "manual",
                "status": "pending",
                "mode": "normal",
                "variant_model": variant_model,
            }
        )
        .execute()
    ).data[0]
    run_id = run["id"]

    if daemon_id:
        await get_command_bus().send(
            daemon_id,
            "agent.run",
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "trigger": "manual",
                "input": group.get("input") or {},
                # Pin the WINNING model (+ its provider, which may differ from the agent's
                # default) onto this live run — the daemon's agent.run honors the override.
                "variant_model": variant_model,
                "variant_provider": provider_of(variant_model) if variant_model else None,
            },
            idempotency_key=f"agent.run:{run_id}",
        )
    await get_audit().write(
        principal.org_id,
        "winner.promoted_live",
        actor=principal.user_id,
        resource_type="run_group",
        resource_id=group_id,
        run_id=run_id,
        detail={"agent_id": agent_id, "variant_model": variant_model},
    )
    return run


# ── inbound: comparison.variant_finished (tag the variant run) ────────────────
@on_daemon_message("comparison.variant_finished")
async def handle_variant_finished(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Upsert the variant `runs` row tagged with its group + model, and its draft tool calls.

    Enforcement/execution happened on the daemon (draft mode); this is audit + tagging only.
    """
    run_id = payload.get("run_id")
    group_id = payload.get("run_group_id")
    model = payload.get("variant_model")
    if not run_id or not group_id:
        return

    db = await service_db()
    # The agent_id isn't in the frame — resolve it from the group.
    grp = (
        await db.table("run_groups")
        .select("agent_id")
        .eq("org_id", ctx.org_id)
        .eq("id", group_id)
        .execute()
    ).data or []
    agent_id = grp[0]["agent_id"] if grp else None
    # `runs.agent_id` is NOT NULL — if the group can't be resolved (e.g. a stray frame for an
    # unknown/deleted group) we can't persist a valid variant row, so audit and bail rather
    # than fail the insert. In the normal flow the group row is created before agent.compare
    # is sent, so it is always found.
    if not agent_id:
        await get_audit().write(
            ctx.org_id,
            "comparison.variant_finished",
            actor=f"daemon:{ctx.daemon_id}",
            resource_type="run_group",
            resource_id=group_id,
            run_id=run_id,
            detail={"variant_model": model, "skipped": "unresolved group/agent"},
        )
        return

    raw_status = str(payload.get("status") or "failed")
    run_status = "succeeded" if raw_status == "succeeded" else (
        "failed" if raw_status in {"failed", "skipped"} else "running"
    )
    run_row: dict[str, Any] = {
        "id": run_id,
        "org_id": ctx.org_id,
        "agent_id": agent_id,
        "daemon_id": ctx.daemon_id,
        "trigger": "manual",
        "status": run_status,
        "mode": "comparison_variant",
        "run_group_id": group_id,
        "variant_model": model,
        "cost_usd": float(payload.get("cost_usd") or 0),
        "tokens_in": int(payload.get("tokens_in") or 0),
        "tokens_out": int(payload.get("tokens_out") or 0),
    }
    await db.table("runs").upsert(run_row, on_conflict="id").execute()

    # Record each draft-mode tool call so the comparison view can show them (§10.6). A
    # side-effecting call is a proposed action; read-only calls executed for real.
    for tc in payload.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        simulated = bool(tc.get("simulated"))
        await db.table("tool_calls").insert(
            {
                "org_id": ctx.org_id,
                "run_id": run_id,
                "name": str(tc.get("name") or ""),
                "args_redacted": tc.get("args_redacted"),
                "simulated": simulated,
                "proposed_action": simulated,
            }
        ).execute()
    # "Would have paused for HITL" markers carry no real gate (§10.5).
    for h in payload.get("simulated_hitl") or []:
        if not isinstance(h, dict):
            continue
        await db.table("hitl_requests").insert(
            {
                "org_id": ctx.org_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "action": str(h.get("name") or "tool"),
                "context": {"args_redacted": h.get("args_redacted")},
                "status": "pending",
                "simulated": True,
            }
        ).execute()

    await get_audit().write(
        ctx.org_id,
        "comparison.variant_finished",
        actor=f"daemon:{ctx.daemon_id}",
        resource_type="run_group",
        resource_id=group_id,
        run_id=run_id,
        detail={"variant_model": model, "status": run_status, "cost_usd": run_row["cost_usd"]},
    )


# ── inbound: comparison.group_ready (flip status + roll up cost) ──────────────
@on_daemon_message("comparison.group_ready")
async def handle_group_ready(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Flip the group to its terminal status and record the aggregate cost (§10.8)."""
    group_id = payload.get("group_id")
    if not group_id:
        return
    raw = str(payload.get("status") or "ready_for_review")
    grp_status = raw if raw in {"ready_for_review", "closed"} else "ready_for_review"
    update: dict[str, Any] = {"status": grp_status, "updated_at": _now()}
    if payload.get("total_cost_usd") is not None:
        update["total_cost_usd"] = float(payload["total_cost_usd"])

    db = await service_db()
    await (
        db.table("run_groups")
        .update(update)
        .eq("org_id", ctx.org_id)
        .eq("id", group_id)
        .execute()
    )
