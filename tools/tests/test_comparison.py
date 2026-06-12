"""Model Comparison Runs — cloud unit tests (possible-features §10).

DB-free unit tests of the cloud logic that doesn't need the new ``run_groups`` table: the
per-model cost estimate (§10.8/§10.9) and the API-agents-only / production-exclusion launch
validation (§10.1/E5). The full launch/cancel/winner/promote integration against live
Supabase requires migration 0020 applied to the project (same deferral as §11's 0019 / §2's
0015), so it is exercised separately once the schema is live.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from synapse_cloud.comparison_pricing import (
    estimate_group,
    estimate_variant,
    known_models,
    provider_of,
)
from synapse_cloud.routers.comparison import _validate_api_agent


# ── pricing / estimate ───────────────────────────────────────────────────────
def test_estimate_variant_known_model():
    e = estimate_variant("claude-opus-4-8", 1_000_000, 1_000_000)
    # 5.0 input + 25.0 output per Mtok
    assert e["cost_usd"] == 30.0
    assert e["provider"] == "anthropic"
    assert e["estimated"] is True


def test_estimate_variant_unknown_model_flagged_not_billed():
    e = estimate_variant("totally-made-up", 1_000_000, 1_000_000)
    assert e["cost_usd"] == 0.0
    assert e["estimated"] is False
    assert e["provider"] is None


def test_estimate_group_totals():
    g = estimate_group(["claude-opus-4-8", "gpt-5"], input_tokens=1_000_000, max_output_tokens=0)
    # opus input 5.0 + gpt-5 input 10.0 (output tokens = 0)
    assert g["total_usd"] == 15.0
    assert len(g["per_model"]) == 2


def test_known_models_filtered_by_provider_credentials():
    only_anthropic = known_models({"anthropic"})
    assert only_anthropic and all(m["provider"] == "anthropic" for m in only_anthropic)
    # the full catalog spans multiple providers
    providers = {m["provider"] for m in known_models()}
    assert {"anthropic", "openai", "google"} <= providers


def test_provider_of():
    assert provider_of("gpt-5") == "openai"
    assert provider_of("gemini-2-pro") == "google"
    assert provider_of("nope") is None


# ── launch validation (E5 / §10.1) ───────────────────────────────────────────
def test_validate_rejects_cli_agent():
    with pytest.raises(HTTPException) as exc:
        _validate_api_agent({"type": "cli"})
    assert exc.value.status_code == 400


def test_validate_rejects_production_tagged_agent():
    with pytest.raises(HTTPException) as exc:
        _validate_api_agent({"type": "api", "tags": ["production"]})
    assert exc.value.status_code == 400


def test_validate_accepts_plain_api_agent():
    _validate_api_agent({"type": "api", "tags": ["safe"]})  # no raise
