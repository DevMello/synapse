"""Durable execution & recovery: checkpoint ingest, reconcile, recover (unit #15).

A run's progress is checkpointed on the daemon and synced here E2E-encrypted to
an org recovery key. The cloud stores **opaque ciphertext blobs + plaintext
metadata only** — it never decrypts a checkpoint payload.

Inbound (daemon → cloud), registered on the message bus:
  * ``run.checkpoint``  — upsert a `run_checkpoints` row + store its opaque blob.
  * ``run.reconcile``   — a reconnected daemon uploads offline work; ingest any
    checkpoints it carries and move the run out of `interrupted`.

REST (Web UI → cloud):
  * ``GET  /runs/{run_id}/checkpoints`` — list a run's checkpoints (org-scoped).
  * ``POST /runs/{run_id}/recover``     — recover an interrupted run onto another
    daemon in the org: mark `recovering`, reassign `daemon_id`, and dispatch the
    `run.recover` command with the latest checkpoint's blob ref.

Every query is org-scoped via the service-role client (RLS is bypassed), and
ownership of the run + target daemon is verified explicitly.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..db import service_db
from ..deps import Principal, get_principal, require_write
from ..message_registry import (
    CHECKPOINT,
    RUN_RECONCILE,
    MessageContext,
    on_daemon_message,
)
from ..services.recovery import (
    RUN_RECOVER_COMMAND,
    build_recover_payload,
    ingest_checkpoint,
    latest_checkpoint,
)

router = APIRouter(tags=["recovery"])


class RecoverRequest(BaseModel):
    """Body for recovering an interrupted run onto another daemon."""

    target_daemon_id: str = Field(min_length=1)


async def _get_run(db, org_id: str, run_id: str) -> dict[str, Any]:
    rows = (
        await db.table("runs")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", run_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return rows[0]


async def _get_daemon(db, org_id: str, daemon_id: str) -> dict[str, Any]:
    rows = (
        await db.table("daemons")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", daemon_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "target daemon not found")
    return rows[0]


# ── Inbound daemon messages ──────────────────────────────────────────────────
@on_daemon_message(CHECKPOINT)
async def handle_checkpoint(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Ingest a ``run.checkpoint`` frame: store the opaque blob + upsert metadata.

    Scoped strictly by ``ctx.org_id`` — a daemon can only checkpoint its own
    org's runs. Idempotent on ``(run_id, seq)``.
    """
    run_id = ctx.run_id or payload.get("run_id")
    if not run_id:
        return
    body = dict(payload)
    if ctx.seq is not None and "seq" not in body:
        body["seq"] = ctx.seq

    db = await service_db()
    await ingest_checkpoint(
        db,
        org_id=ctx.org_id,
        run_id=run_id,
        payload=body,
        daemon_id=ctx.daemon_id,
    )


@on_daemon_message(RUN_RECONCILE)
async def handle_reconcile(ctx: MessageContext, payload: dict[str, Any]) -> None:
    """Handle a reconnected daemon's ``run.reconcile``: ingest offline work.

    Ingests any checkpoints the daemon carries (single or batched) and, when the
    run is currently `interrupted`, transitions it back to a live state
    (`resumed` if the daemon reports completion of offline catch-up, else
    `running`). Org-scoped via ``ctx.org_id``.
    """
    run_id = ctx.run_id or payload.get("run_id")
    if not run_id:
        return

    db = await service_db()

    # A reconcile may carry one inline checkpoint and/or a list of them.
    checkpoints: list[dict[str, Any]] = []
    if isinstance(payload.get("checkpoints"), list):
        checkpoints.extend(payload["checkpoints"])
    if payload.get("seq") is not None or payload.get("payload_blob_ref") is not None:
        checkpoints.append(payload)

    for cp in checkpoints:
        await ingest_checkpoint(
            db,
            org_id=ctx.org_id,
            run_id=run_id,
            payload=cp,
            daemon_id=ctx.daemon_id,
        )

    run = (
        await db.table("runs")
        .select("status")
        .eq("org_id", ctx.org_id)
        .eq("id", run_id)
        .execute()
    ).data or []
    if not run:
        return

    if run[0].get("status") == "interrupted":
        new_status = payload.get("status")
        if new_status not in ("running", "resumed"):
            # Daemon signalling its offline work is complete maps to `resumed`.
            new_status = "resumed" if payload.get("completed") else "running"
        updates: dict[str, Any] = {"status": new_status, "daemon_id": ctx.daemon_id}
        await (
            db.table("runs")
            .update(updates)
            .eq("org_id", ctx.org_id)
            .eq("id", run_id)
            .execute()
        )


# ── REST ─────────────────────────────────────────────────────────────────────
@router.get("/runs/{run_id}/checkpoints")
async def list_checkpoints(
    run_id: str, principal: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    """List a run's checkpoints, org-scoped, ordered by ``seq`` ascending."""
    db = await service_db()
    await _get_run(db, principal.org_id, run_id)
    return (
        await db.table("run_checkpoints")
        .select("*")
        .eq("org_id", principal.org_id)
        .eq("run_id", run_id)
        .order("seq")
        .execute()
    ).data or []


@router.post("/runs/{run_id}/recover")
async def recover_run(
    run_id: str,
    body: RecoverRequest,
    principal: Principal = Depends(require_write),
) -> dict[str, Any]:
    """Recover an interrupted run onto another daemon in the org.

    Verifies the run + target daemon belong to the caller's org, sets the run
    `recovering` with ``daemon_id`` = target, finds the latest checkpoint, and
    dispatches a ``run.recover`` command carrying that checkpoint's opaque blob
    ref + seq. The action is audited.
    """
    db = await service_db()
    run = await _get_run(db, principal.org_id, run_id)
    daemon = await _get_daemon(db, principal.org_id, body.target_daemon_id)
    target_id = daemon["id"]

    checkpoint = await latest_checkpoint(db, org_id=principal.org_id, run_id=run_id)

    updated = (
        await db.table("runs")
        .update({"status": "recovering", "daemon_id": target_id})
        .eq("org_id", principal.org_id)
        .eq("id", run_id)
        .execute()
    ).data
    recovered = updated[0] if updated else {**run, "status": "recovering", "daemon_id": target_id}

    cmd_payload = build_recover_payload(recovered, checkpoint)
    await get_command_bus().send(
        target_id,
        RUN_RECOVER_COMMAND,
        cmd_payload,
        idempotency_key=f"recover:{run_id}:{cmd_payload.get('seq')}",
    )

    await get_audit().write(
        principal.org_id,
        RUN_RECOVER_COMMAND,
        actor=principal.user_id,
        resource_type="run",
        resource_id=run_id,
        run_id=run_id,
        detail={
            "target_daemon_id": target_id,
            "from_seq": checkpoint.get("seq") if checkpoint else None,
        },
    )
    return recovered
