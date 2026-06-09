"""Connection registry + presence for the daemon WebSocket hub.

A WebSocket gives NO cross-reconnect redelivery, so at-least-once delivery of
cloud->daemon commands lives at the APP layer here:

  * each control connection has a monotonic outbound ``seq`` counter;
  * every command we push is buffered (keyed by seq) until the daemon acks it;
  * on reconnect the registry redelivers the still-unacked commands.

Presence/routing state is persisted in Supabase Postgres (``daemon_presence`` row
with a TTL refreshed by heartbeats), so the hub itself stays effectively stateless
across restarts and any node can serve any daemon socket.

CRITICAL: the registry must be inert until a real connection exists. Nothing here
touches Supabase or starts background work at import/construction time — the
presence-reaper is started explicitly by ``ws_hub.startup`` and presence writes
only happen when a daemon actually connects. In ``SYNAPSE_ENV=test`` the
foundation tests never open a socket, so no DB I/O occurs.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..config import get_settings
from ..db import service_db

# Presence row TTL (seconds). Daemons heartbeat ~every 15s; we expire after a
# few missed beats so a dead socket's presence row is reaped promptly.
PRESENCE_TTL_SECONDS = 45
# How often the reaper sweeps for expired presence rows.
REAPER_INTERVAL_SECONDS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _PendingCommand:
    seq: int
    frame: dict[str, Any]


@dataclass
class DaemonConnection:
    """One live control channel for a daemon, with at-least-once send state."""

    daemon_id: str
    org_id: str
    websocket: Any  # starlette/fastapi WebSocket
    _seq: int = 0
    pending: dict[int, _PendingCommand] = field(default_factory=dict)
    _send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def send_command(
        self,
        command_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
        command_auth: Optional[dict[str, Any]] = None,
    ) -> int:
        """Assign a seq, buffer the frame for redelivery, and push it. Returns seq."""
        seq = self.next_seq()
        frame: dict[str, Any] = {
            "type": "command",
            "seq": seq,
            "command_type": command_type,
            "payload": payload,
            "idempotency_key": idempotency_key,
        }
        if command_auth is not None:
            frame["command_auth"] = command_auth
        self.pending[seq] = _PendingCommand(seq=seq, frame=frame)
        await self._send(frame)
        return seq

    async def _send(self, frame: dict[str, Any]) -> None:
        async with self._send_lock:
            await self.websocket.send_text(json.dumps(frame))

    def ack(self, seq: int) -> None:
        """Clear a buffered command the daemon has acknowledged."""
        self.pending.pop(seq, None)

    async def redeliver_pending(self) -> None:
        """Re-push every still-unacked command (called on reconnect)."""
        for pc in sorted(self.pending.values(), key=lambda p: p.seq):
            await self._send(pc.frame)


class ConnectionRegistry:
    """Maps daemon_id -> live control DaemonConnection, with presence persistence.

    Inert until a daemon connects: construction does nothing but allocate dicts.
    """

    def __init__(self) -> None:
        self._connections: dict[str, DaemonConnection] = {}
        # Buffer for commands sent while a daemon is offline (queued for later).
        self._offline_pending: dict[str, dict[int, _PendingCommand]] = {}
        self._offline_seq: dict[str, int] = {}

    # ── connection lifecycle ──────────────────────────────────────────────
    async def connect(self, daemon_id: str, org_id: str, websocket: Any) -> DaemonConnection:
        """Register a control channel, carry over any unacked/queued commands,
        upsert presence, and mark the daemon online."""
        existing = self._connections.get(daemon_id)
        conn = DaemonConnection(daemon_id=daemon_id, org_id=org_id, websocket=websocket)
        # Carry over still-unacked commands from a previous live connection.
        if existing is not None:
            if existing.pending:
                conn.pending.update(existing.pending)
            conn._seq = existing._seq
            # Tear down the stale socket so we don't leak it or double-deliver.
            try:
                await existing.websocket.close(code=1012, reason="reconnected")
            except Exception:  # noqa: BLE001 - already-dead socket
                pass
        # Carry over commands buffered while the daemon was fully offline.
        offline = self._offline_pending.pop(daemon_id, None)
        if offline:
            conn.pending.update(offline)
            conn._seq = max(conn._seq, self._offline_seq.pop(daemon_id, 0))
        self._connections[daemon_id] = conn
        await self._upsert_presence(daemon_id, org_id)
        await self._set_status(daemon_id, "online")
        if conn.pending:
            await conn.redeliver_pending()
        return conn

    def get(self, daemon_id: str) -> Optional[DaemonConnection]:
        return self._connections.get(daemon_id)

    def is_connected(self, daemon_id: str) -> bool:
        return daemon_id in self._connections

    async def disconnect(self, daemon_id: str, conn: Optional["DaemonConnection"] = None) -> None:
        """Drop the live connection, mark offline, and let presence expire.

        ``conn`` is the connection the caller owns. If a *newer* connection has
        already replaced it in the registry (the daemon reconnected before this
        socket's handler unwound), this is a stale disconnect: we must NOT evict
        the live connection or mark the daemon offline. Identity-guarding here
        prevents a late teardown from clobbering a fresh reconnect.

        Any unacked commands on the closing connection are preserved as
        offline-buffered so they redeliver on the next reconnect (at-least-once
        across reconnects)."""
        current = self._connections.get(daemon_id)
        if conn is not None and current is not None and current is not conn:
            # Stale: a newer connection owns this daemon now. Leave it alone.
            return
        removed = self._connections.pop(daemon_id, None)
        target = conn if conn is not None else removed
        if target is not None and target.pending:
            self._offline_pending[daemon_id] = dict(target.pending)
            self._offline_seq[daemon_id] = target._seq
        await self._set_status(daemon_id, "offline")

    # ── outbound command buffering for offline daemons ────────────────────
    def buffer_offline_command(
        self,
        daemon_id: str,
        command_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
        command_auth: Optional[dict[str, Any]] = None,
    ) -> int:
        """Queue a command for a daemon that isn't currently connected."""
        seq = self._offline_seq.get(daemon_id, 0) + 1
        self._offline_seq[daemon_id] = seq
        frame: dict[str, Any] = {
            "type": "command",
            "seq": seq,
            "command_type": command_type,
            "payload": payload,
            "idempotency_key": idempotency_key,
        }
        if command_auth is not None:
            frame["command_auth"] = command_auth
        self._offline_pending.setdefault(daemon_id, {})[seq] = _PendingCommand(seq=seq, frame=frame)
        return seq

    # ── presence persistence (Supabase) ───────────────────────────────────
    async def heartbeat(self, daemon_id: str, org_id: str) -> None:
        """Refresh the presence TTL on a ping/heartbeat frame."""
        await self._upsert_presence(daemon_id, org_id)

    async def _upsert_presence(self, daemon_id: str, org_id: str) -> None:
        now = _now()
        expires = now.timestamp() + PRESENCE_TTL_SECONDS
        expires_at = datetime.fromtimestamp(expires, tz=timezone.utc)
        db = await service_db()
        await (
            db.table("daemon_presence")
            .upsert(
                {
                    "daemon_id": daemon_id,
                    "org_id": org_id,
                    "hub_node": get_settings().hub_node_id,
                    "last_heartbeat": now.isoformat(),
                    "expires_at": expires_at.isoformat(),
                },
                on_conflict="daemon_id",
            )
            .execute()
        )

    async def _set_status(self, daemon_id: str, status: str) -> None:
        db = await service_db()
        update: dict[str, Any] = {"status": status}
        if status == "online":
            update["last_seen"] = _now().isoformat()
        await db.table("daemons").update(update).eq("id", daemon_id).execute()

    async def _delete_presence(self, daemon_id: str) -> None:
        db = await service_db()
        await db.table("daemon_presence").delete().eq("daemon_id", daemon_id).execute()

    async def reap_expired(self) -> int:
        """Delete presence rows whose TTL has lapsed. Returns rows considered."""
        db = await service_db()
        now_iso = _now().isoformat()
        resp = (
            await db.table("daemon_presence")
            .delete()
            .lt("expires_at", now_iso)
            .execute()
        )
        return len(getattr(resp, "data", None) or [])

    async def close_all(self, reason: str = "shutdown") -> None:
        """Close every live socket (used on hub shutdown)."""
        for daemon_id in list(self._connections.keys()):
            conn = self._connections.pop(daemon_id, None)
            if conn is None:
                continue
            try:
                await conn.websocket.close(code=1001, reason=reason)
            except Exception:  # noqa: BLE001 - best effort during shutdown
                pass


async def presence_reaper(registry: ConnectionRegistry) -> None:
    """Background coroutine: periodically delete stale presence rows."""
    while True:
        try:
            await asyncio.sleep(REAPER_INTERVAL_SECONDS)
            await registry.reap_expired()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never let the reaper crash the hub
            # Transient DB errors shouldn't kill the loop; try again next sweep.
            await asyncio.sleep(REAPER_INTERVAL_SECONDS)
