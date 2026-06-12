"""Handoff broker — local chain-grant verification + authorization (§11.7).

``authorize_handoff(...)`` is the pure security core: verify the ed25519 signature over
the canonical chain-grant core, then enforce expiry, same-daemon (H2), the **edge must
exist in the signed graph** (H3), the mode is allowed, the hop is below ``max_hops``, and
the chain's accumulated cost is below ``chain_budget_usd``. Everything is enforced on the
daemon — never trusted to the model or a cloud round-trip (H6).

The signature is verified against the daemon's **trusted** cloud public key
(``settings.grant_public_key``) — the SAME key §2's orchestration grants use — NOT a key
delivered alongside the grant.
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

VALID_MODES = {"tail", "return"}


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class AuthzResult:
    decision: Decision
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


def canonical_bytes(core: dict[str, Any]) -> bytes:
    """Deterministic bytes for a chain-grant core — MUST match the cloud's signer
    (:func:`synapse_cloud.chain_crypto` reuses orchestration_crypto's canonical_bytes)."""
    return json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")


# Test/runtime seam for the trusted cloud signing key (shared with the orchestrator).
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


def edge_in_grant(core: dict[str, Any], from_agent: str, to_agent: str, mode: str) -> bool:
    """True iff an edge from→to with this mode exists in the signed graph (H3)."""
    for e in core.get("edges") or []:
        if str(e.get("from")) == str(from_agent) and str(e.get("to")) == str(to_agent):
            edge_mode = str(e.get("mode") or "tail")
            if edge_mode == mode:
                return True
    return False


def authorize_handoff(
    *,
    core: dict[str, Any],
    signature: str,
    daemon_id: str,
    from_agent_id: str,
    to_agent_id: str,
    mode: str = "tail",
    hop: int = 0,
    chain_cost_usd: float = 0.0,
    trusted_key: Optional[str] = None,
    now: Optional[datetime] = None,
) -> AuthzResult:
    """Authorize one handoff against a signed chain-grant core. Pure (no I/O)."""
    now = now or datetime.now(timezone.utc)
    key = trusted_key if trusted_key is not None else _trusted_key()

    if mode not in VALID_MODES:
        return AuthzResult(Decision.DENY, f"invalid handoff mode '{mode}'")
    if not verify_signature(canonical_bytes(core), signature or "", key or ""):
        return AuthzResult(Decision.DENY, "invalid chain-grant signature")
    if _expired(core, now):
        return AuthzResult(Decision.DENY, "chain grant expired")
    if str(core.get("daemon_id")) != str(daemon_id):
        return AuthzResult(Decision.DENY, "cross-daemon handoff (H2: daemon-local only)")
    if mode not in (core.get("modes") or []):
        return AuthzResult(Decision.DENY, f"mode '{mode}' not allowed by grant")
    if not edge_in_grant(core, from_agent_id, to_agent_id, mode):
        # H3: off-graph target is simply not callable.
        return AuthzResult(Decision.DENY, "edge not in chain grant (off-graph handoff)")
    if int(hop) >= int(core.get("max_hops", 0)):
        return AuthzResult(Decision.DENY, "max_hops exceeded")
    if float(chain_cost_usd) >= float(core.get("chain_budget_usd", 0)):
        return AuthzResult(Decision.DENY, "chain budget exhausted")
    return AuthzResult(Decision.ALLOW, "ok")


# ── chain-grant cache (store-backed; verified offline before each handoff) ──────
async def cache_chain_grant(
    grant_id: str,
    daemon_id: Optional[str],
    flow_id: Optional[str],
    core: dict,
    signature: str,
    public_key: Optional[str],
) -> None:
    await get_store().execute(
        "INSERT INTO chain_grants (grant_id, daemon_id, flow_id, core, signature, public_key, cached_at)"
        " VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(grant_id) DO UPDATE SET daemon_id=excluded.daemon_id, flow_id=excluded.flow_id,"
        " core=excluded.core, signature=excluded.signature, public_key=excluded.public_key,"
        " cached_at=excluded.cached_at",
        (grant_id, daemon_id, flow_id, json.dumps(core), signature, public_key, time.time()),
    )


async def drop_chain_grant(grant_id: str) -> None:
    await get_store().execute("DELETE FROM chain_grants WHERE grant_id=?", (grant_id,))


def _decode(row: dict) -> dict:
    try:
        row["core"] = json.loads(row["core"])
    except (ValueError, TypeError):
        row["core"] = {}
    return row


async def grant_for_edge(from_agent_id: str, to_agent_id: str) -> Optional[dict]:
    """The most-recent cached chain grant whose graph contains edge from→to.

    A daemon may hold several published chains; pick the newest one that authorizes this
    specific edge so the runner can authorize without the caller naming a grant id.
    """
    rows = await get_store().fetchall(
        "SELECT * FROM chain_grants ORDER BY cached_at DESC"
    )
    for row in rows:
        decoded = _decode(dict(row))
        core = decoded["core"]
        for e in core.get("edges") or []:
            if str(e.get("from")) == str(from_agent_id) and str(e.get("to")) == str(to_agent_id):
                return decoded
    return None


async def successors(from_agent_id: str) -> list[dict[str, Any]]:
    """List the successors ``from_agent_id`` may hand off to across all cached grants
    (powers ``synapse.list_chain``)."""
    rows = await get_store().fetchall("SELECT * FROM chain_grants ORDER BY cached_at DESC")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        core = _decode(dict(row))["core"]
        for e in core.get("edges") or []:
            if str(e.get("from")) == str(from_agent_id):
                key = (str(e.get("to")), str(e.get("mode") or "tail"))
                if key not in seen:
                    seen.add(key)
                    out.append({"to": e.get("to"), "mode": e.get("mode") or "tail", "when": e.get("when")})
    return out
