"""Per-model pricing + pre-launch cost estimate for Model Comparison Runs (§10.8/§10.9).

N models ≈ up to N× spend, so the launcher shows a **per-model estimate** and a **group
total** before the human confirms, and the launch enforces a **group cost cap**. The cloud
has no live per-model price feed, so this is a curated static table (USD per **million**
tokens) — the same shape the daemon's runtime price table uses. Unknown models are returned
with ``estimated=False``/zero so the UI can flag "price unknown" rather than bill a wrong
number.

Pure + dependency-free so it is the cloud test anchor (the new ``run_groups`` table isn't
applied to live in this env, so DB-touching endpoints are integration-tested later — these
helpers are unit-tested now, mirroring §11's ``test_handoff.py``).
"""
from __future__ import annotations

from typing import Any, Optional

# provider, input $/Mtok, output $/Mtok. Curated; extend as needed.
_PRICES: dict[str, dict[str, Any]] = {
    # Anthropic
    "claude-opus-4-8": {"provider": "anthropic", "input": 5.0, "output": 25.0},
    "claude-opus-4-7": {"provider": "anthropic", "input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"provider": "anthropic", "input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"provider": "anthropic", "input": 1.0, "output": 5.0},
    # OpenAI
    "gpt-5": {"provider": "openai", "input": 10.0, "output": 30.0},
    "gpt-5-mini": {"provider": "openai", "input": 0.5, "output": 1.5},
    "gpt-4.1": {"provider": "openai", "input": 2.0, "output": 8.0},
    "o4-mini": {"provider": "openai", "input": 1.1, "output": 4.4},
    # Google
    "gemini-2-pro": {"provider": "google", "input": 1.25, "output": 5.0},
    "gemini-2-flash": {"provider": "google", "input": 0.15, "output": 0.6},
}

# Default token assumptions when the caller doesn't supply real counts.
DEFAULT_INPUT_TOKENS = 1_500
DEFAULT_OUTPUT_TOKENS = 800


def provider_of(model: str) -> Optional[str]:
    entry = _PRICES.get(model)
    return entry["provider"] if entry else None


def known_models(providers: Optional[set[str]] = None) -> list[dict[str, Any]]:
    """Return the catalog, optionally limited to providers with credentials (§10.9)."""
    out: list[dict[str, Any]] = []
    for model, p in sorted(_PRICES.items()):
        if providers is not None and p["provider"] not in providers:
            continue
        out.append(
            {
                "model": model,
                "provider": p["provider"],
                "input_per_mtok": p["input"],
                "output_per_mtok": p["output"],
            }
        )
    return out


def estimate_variant(model: str, in_tokens: int, out_tokens: int) -> dict[str, Any]:
    """Estimated USD for one model on the given token budget.

    Returns ``estimated=False`` (cost 0) for an unknown model so the UI flags it rather than
    pretending a price.
    """
    entry = _PRICES.get(model)
    if not entry:
        return {
            "model": model,
            "provider": None,
            "cost_usd": 0.0,
            "estimated": False,
        }
    cost = (in_tokens * float(entry["input"]) + out_tokens * float(entry["output"])) / 1_000_000.0
    return {
        "model": model,
        "provider": entry["provider"],
        "cost_usd": round(cost, 6),
        "estimated": True,
    }


def estimate_group(
    models: list[str],
    input_tokens: int = DEFAULT_INPUT_TOKENS,
    max_output_tokens: int = DEFAULT_OUTPUT_TOKENS,
) -> dict[str, Any]:
    """Per-model estimates + the group total for the N× cost confirmation (§10.8)."""
    per_model = [estimate_variant(m, input_tokens, max_output_tokens) for m in models]
    total = round(sum(float(p["cost_usd"]) for p in per_model), 6)
    return {
        "per_model": per_model,
        "total_usd": total,
        "input_tokens": input_tokens,
        "output_tokens": max_output_tokens,
    }
