"""Async delivery + HITL timeout sweeper (Arq tasks/cron).

`deliver_notification` is an Arq task that pushes a single event through the
configured notifier off the request path. `sweep_expired_hitl` is a cron job
(default every minute) that enforces the HITL *default-deny* policy: any pending
`hitl_requests` row past its `expires_at` is flipped to 'expired' and a denied
`hitl.resolve` command is sent back to the originating daemon.

Both are plain async functions so tests can call them directly without Redis.
Arq passes a context dict as the first arg, so it is accepted and ignored.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ..scheduler import PeriodicJob
from ..command_bus import get_command_bus
from ..db import service_db
from ..notifications.base import get_notifier

log = logging.getLogger("synapse.workers.notify")


async def deliver_notification(
    ctx: Optional[dict],
    org_id: str,
    event: str,
    payload: dict[str, Any],
    *,
    channels: Optional[list[str]] = None,
) -> None:
    """Arq task: deliver one event via the configured notifier."""
    await get_notifier().notify(org_id, event, payload, channels=channels)


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


tasks = [deliver_notification]
periodic_jobs = [PeriodicJob("notify.sweep_expired_hitl", sweep_expired_hitl, 60)]
