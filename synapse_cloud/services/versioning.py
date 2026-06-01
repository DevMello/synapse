"""Agent version-management helpers (immutable, append-only).

Every prompt/config change for an agent appends a brand-new `agent_versions`
row with a per-agent monotonically increasing `version` and points
`agents.current_version` at it. Existing version rows are NEVER mutated except
for their `tags` (operator labels like 'known-good'/'production'), which are not
part of the immutable prompt/config snapshot.

These helpers are service-role (RLS-bypassing) and therefore always require an
explicit `org_id`; callers (the agents router) resolve it from the principal.
"""
from __future__ import annotations

import difflib
import json
from typing import Any, Optional

from supabase import AsyncClient


async def next_version_number(db: AsyncClient, org_id: str, agent_id: str) -> int:
    """Return the next monotonic version number for an agent (1-based)."""
    rows = (
        await db.table("agent_versions")
        .select("version")
        .eq("org_id", org_id)
        .eq("agent_id", agent_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    ).data or []
    return (rows[0]["version"] + 1) if rows else 1


async def get_version(
    db: AsyncClient, org_id: str, agent_id: str, version: int
) -> Optional[dict]:
    """Fetch a single version row, org+agent scoped, or None."""
    rows = (
        await db.table("agent_versions")
        .select("*")
        .eq("org_id", org_id)
        .eq("agent_id", agent_id)
        .eq("version", version)
        .execute()
    ).data or []
    return rows[0] if rows else None


async def list_versions(db: AsyncClient, org_id: str, agent_id: str) -> list[dict]:
    """List all versions for an agent, newest first."""
    return (
        await db.table("agent_versions")
        .select("*")
        .eq("org_id", org_id)
        .eq("agent_id", agent_id)
        .order("version", desc=True)
        .execute()
    ).data or []


async def create_version(
    db: AsyncClient,
    *,
    org_id: str,
    agent_id: str,
    prompt: Optional[str],
    config: dict[str, Any],
    author_user_id: Optional[str],
    message: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Append a new immutable version row and bump `agents.current_version`.

    The new version number is computed as max(version)+1 for this agent. The
    `agent_versions(agent_id, version)` unique constraint guards against races.
    """
    version = await next_version_number(db, org_id, agent_id)
    row = (
        await db.table("agent_versions")
        .insert(
            {
                "org_id": org_id,
                "agent_id": agent_id,
                "version": version,
                "prompt": prompt,
                "config": config or {},
                "author_user_id": author_user_id,
                "message": message,
                "tags": tags or [],
            }
        )
        .execute()
    ).data[0]

    await db.table("agents").update({"current_version": version}).eq(
        "org_id", org_id
    ).eq("id", agent_id).execute()

    return row


async def set_version_tags(
    db: AsyncClient, org_id: str, agent_id: str, version: int, tags: list[str]
) -> Optional[dict]:
    """Set/clear tags on an existing version. Tags are the only mutable field;
    prompt/config remain immutable."""
    updated = (
        await db.table("agent_versions")
        .update({"tags": tags})
        .eq("org_id", org_id)
        .eq("agent_id", agent_id)
        .eq("version", version)
        .execute()
    ).data or []
    return updated[0] if updated else None


def _config_text(config: Any) -> str:
    """Stable, human-readable serialization of a config for diffing."""
    try:
        return json.dumps(config or {}, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        return str(config)


def diff_versions(a: dict, b: dict) -> dict:
    """Structured diff between two version rows (a -> b).

    Returns a unified text diff of prompts and of pretty-printed configs, plus
    a `changed` flag for each so callers can render concisely.
    """
    a_prompt = a.get("prompt") or ""
    b_prompt = b.get("prompt") or ""
    prompt_diff = "".join(
        difflib.unified_diff(
            a_prompt.splitlines(keepends=True),
            b_prompt.splitlines(keepends=True),
            fromfile=f"v{a.get('version')}/prompt",
            tofile=f"v{b.get('version')}/prompt",
        )
    )

    a_config = _config_text(a.get("config"))
    b_config = _config_text(b.get("config"))
    config_diff = "".join(
        difflib.unified_diff(
            a_config.splitlines(keepends=True),
            b_config.splitlines(keepends=True),
            fromfile=f"v{a.get('version')}/config",
            tofile=f"v{b.get('version')}/config",
        )
    )

    return {
        "from_version": a.get("version"),
        "to_version": b.get("version"),
        "prompt": {
            "changed": a_prompt != b_prompt,
            "diff": prompt_diff,
        },
        "config": {
            "changed": a.get("config") != b.get("config"),
            "diff": config_diff,
        },
    }
