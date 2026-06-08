"""Orchestration broker — local grant verification + authorization (§2.4 / §2.5).

`authorize(...)` is the pure security core: verify the ed25519 signature over the
canonical grant core, then enforce expiry, same-daemon (D1), verb, target allow-list,
depth, and **no-escalation** (the child's effective perms must be a subset of the
caller's). Create/edit require HITL. Everything is enforced on the daemon — never
trusted to the model or a cloud round-trip.

The signature is verified against the daemon's **trusted** cloud public key
(`settings.grant_public_key`), NOT a key delivered alongside the grant.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional

from ..config import get_settings
from ..logging import get_logger
from ..selfupdate import verify_signature
from ..store import get_store

log = get_logger(__name__)

VALID_VERBS = {"run", "create", "edit"}
HITL_VERBS = {"create", "edit"}


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HITL = "require_hitl"


@dataclass
class AuthzResult:
    decision: Decision
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


def canonical_bytes(core: dict[str, Any]) -> bytes:
    """Deterministic bytes for a grant core — MUST match the cloud's signer."""
    return json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")


# Test/runtime seam for the trusted cloud signing key.
_override_key: Optional[str] = None


def set_trusted_grant_key(key: Optional[str]) -> None:
    global _override_key
    _override_key = key


def _trusted_key() -> str:
    if _override_key is not None:
        return _override_key
    return get_settings().grant_public_key


def _expired(core: dict[str, Any], now: datetime) -> bool:
    try:
        exp = datetime.fromisoformat(str(core["expires_at"]).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now >= exp
    except Exception:  # noqa: BLE001 - unparseable expiry => treat as expired
        return True


def _target_allowed(target_id: str, allow: Iterable[str]) -> bool:
    allow = list(allow or [])
    if not allow:
        return False
    if "*" in allow:
        return True
    return target_id in allow


def authorize(
    *,
    core: dict[str, Any],
    signature: str,
    daemon_id: str,
    verb: str,
    target_agent_id: str,
    caller_depth: int = 0,
    caller_perms: Optional[Iterable[str]] = None,
    target_perms: Optional[Iterable[str]] = None,
    trusted_key: Optional[str] = None,
    now: Optional[datetime] = None,
) -> AuthzResult:
    """Authorize one orchestration call against a signed grant core. Pure."""
    now = now or datetime.now(timezone.utc)
    key = trusted_key if trusted_key is not None else _trusted_key()

    if not verify_signature(canonical_bytes(core), signature or "", key or ""):
        return AuthzResult(Decision.DENY, "invalid grant signature")
    if _expired(core, now):
        return AuthzResult(Decision.DENY, "grant expired")
    if str(core.get("daemon_id")) != str(daemon_id):
        return AuthzResult(Decision.DENY, "cross-daemon target (D1: daemon-local only)")
    if verb not in (core.get("verbs") or []):
        return AuthzResult(Decision.DENY, f"verb '{verb}' not granted")
    if not _target_allowed(target_agent_id, core.get("target_allow") or []):
        return AuthzResult(Decision.DENY, "target not in grant allow-list")
    if int(caller_depth) >= int(core.get("max_depth", 0)):
        return AuthzResult(Decision.DENY, "max_depth exceeded")
    # No-escalation (§2.5): the child's effective perms must be a subset of the caller's.
    if caller_perms is not None and target_perms is not None:
        if not set(target_perms) <= set(caller_perms):
            return AuthzResult(
                Decision.DENY, "no-escalation: child would exceed caller's permissions"
            )
    if verb in HITL_VERBS:
        return AuthzResult(Decision.REQUIRE_HITL, f"verb '{verb}' requires human approval")
    return AuthzResult(Decision.ALLOW, "ok")


# ── grant cache (store-backed; verified offline before each call) ──────────────
async def cache_grant(
    grant_id: str, agent_id: Optional[str], core: dict, signature: str, public_key: Optional[str]
) -> None:
    await get_store().execute(
        "INSERT INTO orchestration_grants (grant_id, agent_id, core, signature, public_key, cached_at)"
        " VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(grant_id) DO UPDATE SET agent_id=excluded.agent_id, core=excluded.core,"
        " signature=excluded.signature, public_key=excluded.public_key, cached_at=excluded.cached_at",
        (grant_id, agent_id, json.dumps(core), signature, public_key, time.time()),
    )


async def drop_grant(grant_id: str) -> None:
    await get_store().execute(
        "DELETE FROM orchestration_grants WHERE grant_id=?", (grant_id,)
    )


async def grant_for_agent(agent_id: str) -> Optional[dict]:
    """Most-recent cached grant for an orchestrator agent (core decoded)."""
    row = await get_store().fetchone(
        "SELECT * FROM orchestration_grants WHERE agent_id=? ORDER BY cached_at DESC LIMIT 1",
        (agent_id,),
    )
    if not row:
        return None
    try:
        row["core"] = json.loads(row["core"])
    except (ValueError, TypeError):
        row["core"] = {}
    return row


# ── lineage WAL (§2.4 step 4) ─────────────────────────────────────────────────
async def lineage_append(
    *,
    parent_run_id: Optional[str],
    child_run_id: str,
    root_run_id: str,
    grant_id: str,
    verb: str,
    depth: int,
) -> int:
    store = get_store()
    cur = await store.db.execute(
        "INSERT INTO orchestration_lineage"
        " (parent_run_id, child_run_id, root_run_id, grant_id, verb, depth, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (parent_run_id, child_run_id, root_run_id, grant_id, verb, int(depth), "running", time.time()),
    )
    await store.db.commit()
    return int(cur.lastrowid)


async def lineage_update(child_run_id: str, status: str) -> None:
    await get_store().execute(
        "UPDATE orchestration_lineage SET status=?, completed_at=? WHERE child_run_id=?",
        (status, time.time(), child_run_id),
    )
