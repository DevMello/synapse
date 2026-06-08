"""HITL timeout sweeper (periodic job).

`sweep_expired_hitl` enforces the HITL *default-deny* policy: any pending
`hitl_requests` row past its `expires_at` is flipped to 'expired' and a denied
`hitl.resolve` command is sent back to the originating daemon. It runs every minute
via the in-process scheduler and is a plain async function so tests can call it
directly.

Event-driven notification *delivery* is inline at the emit sites (HITL create §hitl,
anomaly §anomaly, run failure §runs) via ``get_notifier().notify(...)`` — not a queued
task.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ..scheduler import PeriodicJob
from ..command_bus import get_command_bus
from ..db import service_db

log = logging.getLogger("synapse.workers.notify")


async def sweep_expired_hitl(ctx: Optional[dict] = None) -> int:
    """Expire overdue pending HITL requests (default-deny) and command daemons.

    Returns the number of requests expired. Callable directly in tests.
    """
    db = await service_db()
    now_iso = datetime.now(timezone.utc).isoformat()

    overdue = (
        await db.table("hitl_requests")
        .select("*")
        .eq("status", "pending")
        .not_.is_("expires_at", "null")
        .lt("expires_at", now_iso)
        .execute()
    ).data or []

    expired = 0
    for request in overdue:
        updated = (
            await db.table("hitl_requests")
            .update(
                {
                    "status": "expired",
                    "resolution_reason": "timed out (default-deny)",
                    "resolved_at": "now()",
                }
            )
            .eq("org_id", request["org_id"])
            .eq("id", request["id"])
            .eq("status", "pending")
            .execute()
        ).data or []
        if not updated:
            # Resolved concurrently by an operator; skip the command.
            continue
        row = updated[0]
        expired += 1
        await get_command_bus().send(
            row["daemon_id"],
            "hitl.resolve",
            {
                "hitl_id": row["id"],
                "run_id": row.get("run_id"),
                "agent_id": row.get("agent_id"),
                "action": row.get("action"),
                "decision": "denied",
                "reason": "timed out (default-deny)",
            },
            idempotency_key=f"hitl.resolve:{row['id']}",
        )
    if expired:
        log.info("swept %d expired HITL requests", expired)
    return expired


periodic_jobs = [PeriodicJob("notify.sweep_expired_hitl", sweep_expired_hitl, 60)]
