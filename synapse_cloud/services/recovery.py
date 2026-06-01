"""Shared helpers for durable execution & recovery (unit #15).

Long agent runs are checkpointed on the daemon (SQLite WAL) and synced to the
cloud E2E-encrypted to an org recovery key. The cloud therefore stores **opaque
ciphertext blobs + plaintext metadata only** and never decrypts checkpoint
payloads.

This module centralises the DB logic shared between the inbound message
handlers (``routers/recovery.py``), the REST recover endpoint, and the
heartbeat-monitor worker (``workers/heartbeat_monitor.py``) so the same code is
exercised by tests without Redis.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Optional

from ..storage import CHECKPOINTS, get_storage

# run_status values considered "in flight" — a stale daemon's runs in these
# states get marked `interrupted` by the heartbeat sweep / get reconciled.
IN_FLIGHT_STATUSES = ("running", "recovering")

# command type sent to a target daemon to recover an interrupted run.
RUN_RECOVER_COMMAND = "run.recover"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _decode_blob(payload: dict[str, Any]) -> Optional[bytes]:
    """Extract the opaque checkpoint ciphertext from a daemon payload.

    The daemon may carry the blob as raw bytes, a base64 string (``payload_b64``
    / ``blob_b64``), or a plain ``payload`` string. Returns ``None`` when no blob
    is present (metadata-only checkpoint).
    """
    for key in ("payload_b64", "blob_b64"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return base64.b64decode(val)
    for key in ("payload_blob", "blob"):
        val = payload.get(key)
        if isinstance(val, (bytes, bytearray)):
            return bytes(val)
        if isinstance(val, str) and val:
            return val.encode("utf-8")
    return None


def checkpoint_blob_key(org_id: str, run_id: str, seq: int) -> str:
    """Storage key for a run's checkpoint blob: ``{org}/{run}/{seq}.blob``."""
    return f"{org_id}/{run_id}/{seq}.blob"


async def ingest_checkpoint(
    db,
    *,
    org_id: str,
    run_id: str,
    payload: dict[str, Any],
    daemon_id: Optional[str] = None,
) -> dict[str, Any]:
    """Upsert one ``run_checkpoints`` row and store its opaque blob.

    The blob (if any) is written to the CHECKPOINTS bucket and its ref saved to
    ``payload_blob_ref``. Upserts on the unique ``(run_id, seq)`` constraint so
    re-delivery is idempotent. The cloud never inspects the blob contents.
    Returns the persisted row.
    """
    seq = int(payload.get("seq", 0))

    blob_ref: Optional[str] = payload.get("payload_blob_ref")
    data = _decode_blob(payload)
    if data is not None:
        key = checkpoint_blob_key(org_id, run_id, seq)
        blob_ref = await get_storage().put(
            CHECKPOINTS, key, data, content_type="application/octet-stream"
        )

    row: dict[str, Any] = {
        "org_id": org_id,
        "run_id": run_id,
        "seq": seq,
        "cost_so_far_usd": payload.get("cost_so_far_usd", 0),
    }
    if "step_cursor" in payload and payload["step_cursor"] is not None:
        row["step_cursor"] = payload["step_cursor"]
    if payload.get("status") is not None:
        row["status"] = payload["status"]
    if daemon_id is not None:
        row["daemon_id"] = daemon_id
    if blob_ref is not None:
        row["payload_blob_ref"] = blob_ref

    return (
        await db.table("run_checkpoints")
        .upsert(row, on_conflict="run_id,seq")
        .execute()
    ).data[0]


async def latest_checkpoint(
    db, *, org_id: str, run_id: str
) -> Optional[dict[str, Any]]:
    """Return the highest-``seq`` checkpoint for a run (org-scoped) or None."""
    rows = (
        await db.table("run_checkpoints")
        .select("*")
        .eq("org_id", org_id)
        .eq("run_id", run_id)
        .order("seq", desc=True)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def build_recover_payload(
    run: dict[str, Any], checkpoint: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Build the ``run.recover`` command payload sent to the target daemon.

    Carries the latest checkpoint's opaque blob ref + seq so the daemon can pull
    the ciphertext and resume; the cloud passes the ref through untouched.
    """
    payload: dict[str, Any] = {
        "run_id": run["id"],
        "agent_id": run.get("agent_id"),
    }
    if run.get("agent_version") is not None:
        payload["agent_version"] = run["agent_version"]
    if checkpoint is not None:
        payload["seq"] = checkpoint.get("seq")
        payload["step_cursor"] = checkpoint.get("step_cursor")
        payload["payload_blob_ref"] = checkpoint.get("payload_blob_ref")
    return payload


async def sweep_interrupted_runs(db) -> dict[str, Any]:
    """Mark runs of stale daemons ``interrupted`` and the daemons ``offline``.

    Scans ``daemon_presence`` for rows whose ``expires_at`` has passed; for each
    stale daemon, transitions its in-flight ``runs`` (status running/recovering)
    to ``interrupted`` and sets ``daemons.status='offline'``. This is the plain
    async core called both by the Arq worker and directly by tests (no Redis).
    Returns a small summary dict.
    """
    now_iso = _now_iso()
    stale = (
        await db.table("daemon_presence")
        .select("daemon_id, org_id")
        .lt("expires_at", now_iso)
        .execute()
    ).data or []

    interrupted_runs = 0
    offline_daemons = 0
    for row in stale:
        daemon_id = row["daemon_id"]
        org_id = row["org_id"]

        updated = (
            await db.table("runs")
            .update({"status": "interrupted"})
            .eq("org_id", org_id)
            .eq("daemon_id", daemon_id)
            .in_("status", list(IN_FLIGHT_STATUSES))
            .execute()
        ).data or []
        interrupted_runs += len(updated)

        await (
            db.table("daemons")
            .update({"status": "offline"})
            .eq("org_id", org_id)
            .eq("id", daemon_id)
            .execute()
        )
        offline_daemons += 1

    return {
        "stale_daemons": len(stale),
        "interrupted_runs": interrupted_runs,
        "offline_daemons": offline_daemons,
    }
