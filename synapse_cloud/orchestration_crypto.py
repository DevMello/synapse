"""Ed25519 signing for agent-orchestration grants (possible-features §2.3).

The cloud mints an **attenuated grant** and signs the security-critical subset of
its fields. The daemon caches the grant and **verifies the signature offline** before
enforcing it locally (no cloud round-trip on the hot path). The signed bytes are the
**canonical core** dict — sorted-key, compact JSON — delivered verbatim to the daemon
so both sides hash identical bytes (the daemon never re-derives the core, it verifies
the delivered one).

Key handling: `grant_signing_key` (base64 32-byte seed) from settings in production;
when unset, a deterministic dev/test key is used so sign↔verify round-trips locally.
"""
from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from typing import Any

from nacl.signing import SigningKey, VerifyKey

from .config import get_settings

# The exact fields covered by the signature. Anything outside this set is NOT
# protected by the signature and must not be trusted by the daemon.
SIGNED_FIELDS = (
    "org_id",
    "agent_id",
    "daemon_id",
    "verbs",
    "target_allow",
    "max_depth",
    "max_fan_out",
    "tree_budget_usd",
    "protected_fields",
    "expires_at",
    "key_id",
)


def grant_core(grant: dict[str, Any]) -> dict[str, Any]:
    """The canonical signed subset, with coerced types + sorted lists.

    Built once at mint time and delivered verbatim to the daemon as ``core``.
    """
    return {
        "org_id": str(grant["org_id"]),
        "agent_id": str(grant["agent_id"]),
        "daemon_id": str(grant["daemon_id"]),
        "verbs": sorted(str(v) for v in (grant.get("verbs") or [])),
        "target_allow": sorted(str(v) for v in (grant.get("target_allow") or [])),
        "max_depth": int(grant.get("max_depth", 0)),
        "max_fan_out": int(grant.get("max_fan_out", 0)),
        "tree_budget_usd": float(grant.get("tree_budget_usd", 0)),
        "protected_fields": sorted(str(v) for v in (grant.get("protected_fields") or [])),
        "expires_at": str(grant["expires_at"]),
        "key_id": str(grant.get("key_id") or get_settings().grant_key_id),
    }


def canonical_bytes(core: dict[str, Any]) -> bytes:
    """Deterministic bytes for a core dict (sorted keys, compact)."""
    return json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")


@lru_cache
def _signing_key() -> SigningKey:
    s = get_settings()
    if s.grant_signing_key:
        return SigningKey(base64.b64decode(s.grant_signing_key))
    # Deterministic dev/test key — overridden by GRANT_SIGNING_KEY in production.
    return SigningKey(hashlib.sha256(b"synapse-dev-grant-signing").digest())


def grant_public_key_b64() -> str:
    """The ed25519 public key the daemon uses to verify grant signatures."""
    return base64.b64encode(bytes(_signing_key().verify_key)).decode("ascii")


def sign_core(core: dict[str, Any]) -> str:
    """Sign the canonical core; returns base64 ed25519 signature."""
    sig = _signing_key().sign(canonical_bytes(core)).signature
    return base64.b64encode(sig).decode("ascii")


def verify_core(core: dict[str, Any], signature_b64: str, public_key_b64: str) -> bool:
    """Verify a signature over a delivered core (used by tests; the daemon has its own)."""
    try:
        vk = VerifyKey(base64.b64decode(public_key_b64))
        vk.verify(canonical_bytes(core), base64.b64decode(signature_b64))
        return True
    except Exception:
        return False


def reset_signing_key_cache() -> None:  # test helper (after settings change)
    _signing_key.cache_clear()
