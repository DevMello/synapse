"""Ed25519 signing for agent **chain grants** (possible-features §11.4).

A published Flow Canvas design compiles into an **attenuated chain grant** — a signed,
directed graph of allowed handoff edges. As with the §2 orchestration grant, the cloud
signs the security-critical subset of fields (the **canonical core**) and the daemon
verifies the signature **offline** before enforcing it locally.

This deliberately **reuses §2's signing key + canonical encoding**
(:mod:`synapse_cloud.orchestration_crypto`) so the daemon trusts a single cloud public
key (``settings.grant_public_key``) for both grant kinds. Only the set of *signed fields*
differs — defined here.
"""
from __future__ import annotations

import json
from typing import Any

from .config import get_settings
from .orchestration_crypto import (  # reuse: one key, identical canonical bytes
    canonical_bytes,
    grant_public_key_b64,
    sign_core,
)

# The exact fields covered by a chain-grant signature. Anything outside this set is NOT
# protected and must not be trusted by the daemon.
SIGNED_FIELDS = (
    "org_id",
    "daemon_id",
    "flow_id",
    "edges",
    "routing",
    "max_hops",
    "chain_budget_usd",
    "max_payload_bytes",
    "modes",
    "expires_at",
    "key_id",
)

# Edge fields that participate in the signed core (in canonical order). Extra UX-only
# fields on an edge (e.g. payload `mapping`, label) are NOT signed — the daemon enforces
# only the security-relevant topology: which from→to edges exist, the mode, and the
# router `when` condition.
_EDGE_FIELDS = ("from", "to", "mode", "when")


def _canonical_edge(edge: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "from": str(edge.get("from") or ""),
        "to": str(edge.get("to") or ""),
        "mode": str(edge.get("mode") or "tail"),
    }
    when = edge.get("when")
    out["when"] = str(when) if when not in (None, "") else None
    return out


def chain_grant_core(grant: dict[str, Any]) -> dict[str, Any]:
    """The canonical signed subset of a chain grant, with coerced types + sorted edges.

    Built once at publish time and delivered verbatim to the daemon as ``core``.
    """
    edges = [_canonical_edge(e) for e in (grant.get("edges") or [])]
    # Deterministic ordering so the signed bytes don't depend on author draw order.
    edges.sort(key=lambda e: (e["from"], e["to"], e["mode"], e["when"] or ""))
    return {
        "org_id": str(grant["org_id"]),
        "daemon_id": str(grant["daemon_id"]),
        "flow_id": str(grant.get("flow_id") or ""),
        "edges": edges,
        "routing": str(grant.get("routing") or "first_match"),
        "max_hops": int(grant.get("max_hops", 0)),
        "chain_budget_usd": float(grant.get("chain_budget_usd", 0)),
        "max_payload_bytes": int(grant.get("max_payload_bytes", 0)),
        "modes": sorted(str(m) for m in (grant.get("modes") or [])),
        "expires_at": str(grant["expires_at"]),
        "key_id": str(grant.get("key_id") or get_settings().grant_key_id),
    }


__all__ = [
    "SIGNED_FIELDS",
    "chain_grant_core",
    "canonical_bytes",
    "sign_core",
    "grant_public_key_b64",
]
