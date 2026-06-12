"""Native Handoff Protocol — chain-grant signing + flow→grant compilation (§11).

These are **DB-free unit tests** of the security-critical cloud logic: the canonical
chain-grant core, the ed25519 sign↔verify round-trip (reusing §2's key), and the
canvas-design → grant-edge compilation that strips structural nodes and rejects bad
modes. (The full publish/revoke integration against live Supabase requires migration
0019 applied to the project — see the orchestration MVP, where 0015 was applied the
same way — so it is exercised separately once the schema is live.)
"""
from __future__ import annotations

import pytest

from synapse_cloud.chain_crypto import chain_grant_core, sign_core
from synapse_cloud.orchestration_crypto import grant_public_key_b64, verify_core
from synapse_cloud.routers.handoff import _compile_edges


def _grant_fields() -> dict:
    return {
        "org_id": "org_1",
        "daemon_id": "dmn_1",
        "flow_id": "flw_1",
        "edges": [
            {"from": "agt_planner", "to": "agt_critic", "mode": "tail", "when": None},
            {"from": "agt_critic", "to": "agt_executor", "mode": "tail", "when": "approved"},
        ],
        "routing": "first_match",
        "max_hops": 8,
        "chain_budget_usd": 5.0,
        "max_payload_bytes": 32768,
        "modes": ["tail", "return"],
        "expires_at": "2026-06-07T00:00:00Z",
        "key_id": None,
    }


def test_chain_core_sign_and_verify_round_trip():
    core = chain_grant_core(_grant_fields())
    sig = sign_core(core)
    assert verify_core(core, sig, grant_public_key_b64()) is True


def test_tampering_core_breaks_signature():
    core = chain_grant_core(_grant_fields())
    sig = sign_core(core)
    # Add a forbidden edge after signing — must fail verification.
    bad = dict(core)
    bad["edges"] = core["edges"] + [{"from": "agt_x", "to": "agt_root", "mode": "tail", "when": None}]
    assert verify_core(bad, sig, grant_public_key_b64()) is False
    # Loosening the budget is also caught.
    assert verify_core(dict(core, chain_budget_usd=999.0), sig, grant_public_key_b64()) is False


def test_core_is_deterministic_regardless_of_edge_draw_order():
    a = _grant_fields()
    b = dict(a)
    b["edges"] = list(reversed(a["edges"]))  # author drew them in the other order
    assert chain_grant_core(a) == chain_grant_core(b)
    # ...and therefore the signature is identical.
    assert sign_core(chain_grant_core(a)) == sign_core(chain_grant_core(b))


def test_compile_strips_structural_nodes_and_resolves_agents():
    flow = {
        "nodes": [
            {"id": "n_start", "kind": "start"},          # structural — no agent
            {"id": "n_p", "agent_id": "agt_planner"},
            {"id": "n_c", "agent_id": "agt_critic"},
            {"id": "n_end", "kind": "end"},              # structural — no agent
        ],
        "edges": [
            {"from": "n_start", "to": "n_p", "mode": "tail"},   # seed → dropped from grant
            {"from": "n_p", "to": "n_c", "mode": "tail", "when": "always"},
            {"from": "n_c", "to": "n_end", "mode": "tail"},     # → end → dropped
        ],
    }
    edges = _compile_edges(flow, {"n_p": "agt_planner", "n_c": "agt_critic"})
    assert edges == [{"from": "agt_planner", "to": "agt_critic", "mode": "tail", "when": "always"}]


def test_compile_rejects_invalid_mode():
    from fastapi import HTTPException

    flow = {"edges": [{"from": "n_p", "to": "n_c", "mode": "fan_out"}]}
    with pytest.raises(HTTPException):
        _compile_edges(flow, {"n_p": "agt_planner", "n_c": "agt_critic"})
