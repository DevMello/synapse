"""Agent-memory sync helpers (shared by the memory router + inbound handler).

The cloud stores a **redacted plaintext** snapshot of agent memory under RLS so
the Web UI can read and edit it (this subsystem is deliberately NOT E2E-encrypted
— see routers/memory.py). The daemon's local store is the source of truth; the
cloud is a snapshot + editor that pushes UI edits back down via the `memory.sync`
command and absorbs daemon-originated deltas via the `memory.delta` inbound
message.

These helpers are pure/testable: byte accounting, the `memory.sync` command
payload shape, and the service-role upsert against `agent_memory`. All DB calls
require an explicit `org_id` because the service-role client bypasses RLS.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from supabase import AsyncClient

# Outbound command type (cloud → daemon). The daemon applies these to its local
# store. One command carries a single entry op (upsert or delete).
MEMORY_SYNC_COMMAND = "memory.sync"

_TABLE = "agent_memory"


def compute_bytes(value: Any, text: Optional[str]) -> int:
    """Size accounting for a memory entry: len(json.dumps(value)) + len(text).

    `value` is serialized with json.dumps (None -> "null", i.e. 4 bytes); `text`
    contributes its own character length. Mirrors what the daemon reports so the
    UI and daemon agree on quota math.
    """
    value_len = len(json.dumps(value))
    text_len = len(text) if text else 0
    return value_len + text_len


def build_sync_payload(
    *,
    agent_id: str,
    namespace: str,
    key: str,
    op: str,
    value: Any = None,
    text: Optional[str] = None,
    tags: Optional[list[str]] = None,
    version: Optional[int] = None,
) -> dict[str, Any]:
    """Build the `memory.sync` command payload sent to the owning daemon.

    `op` is "upsert" or "delete". An upsert carries the redacted value/text/tags
    so the daemon can apply the edit; a delete carries only the identifying
    (namespace, key) tuple.
    """
    payload: dict[str, Any] = {
        "op": op,
        "agent_id": agent_id,
        "namespace": namespace,
        "key": key,
    }
    if op == "upsert":
        payload["value"] = value
        payload["text"] = text
        payload["tags"] = tags or []
        if version is not None:
            payload["version"] = version
    return payload


def sync_idempotency_key(agent_id: str, namespace: str, key: str, op: str) -> str:
    """Stable idempotency key for a memory.sync command."""
    return f"{MEMORY_SYNC_COMMAND}:{op}:{agent_id}:{namespace}:{key}"


async def current_version(
    db: AsyncClient, org_id: str, agent_id: str, namespace: str, key: str
) -> Optional[int]:
    """Return the existing entry's version (or None if it does not exist)."""
    rows = (
        await db.table(_TABLE)
        .select("version")
        .eq("org_id", org_id)
        .eq("agent_id", agent_id)
        .eq("namespace", namespace)
        .eq("key", key)
        .execute()
    ).data or []
    return rows[0]["version"] if rows else None


async def upsert_entry(
    db: AsyncClient,
    *,
    org_id: str,
    agent_id: str,
    namespace: str,
    key: str,
    value: Any = None,
    text: Optional[str] = None,
    tags: Optional[list[str]] = None,
    updated_by: str,
    version: Optional[int] = None,
    bytes_override: Optional[int] = None,
) -> dict:
    """Upsert one redacted memory entry, bumping `version` (existing+1 else 1).

    Upserts on the unique (agent_id, namespace, key) constraint. `bytes` is
    computed from value+text unless `bytes_override` is supplied (the daemon may
    report its own byte count in a delta). Returns the persisted row.
    """
    if version is None:
        existing = await current_version(db, org_id, agent_id, namespace, key)
        version = (existing + 1) if existing is not None else 1

    nbytes = bytes_override if bytes_override is not None else compute_bytes(value, text)

    row = (
        await db.table(_TABLE)
        .upsert(
            {
                "org_id": org_id,
                "agent_id": agent_id,
                "namespace": namespace,
                "key": key,
                "value_redacted": value,
                "text_redacted": text,
                "tags": tags or [],
                "version": version,
                "bytes": nbytes,
                "updated_by": updated_by,
                "updated_at": "now()",
            },
            on_conflict="agent_id,namespace,key",
        )
        .execute()
    ).data[0]
    return row
