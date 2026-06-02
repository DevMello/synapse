"""Local token/cost accounting for CLI agents via the ``ccusage`` Node CLI (§4.3).

CLI agents (Claude Code, Codex, Gemini CLI, aider, ...) don't return per-call token
usage the way the API adapter does. Instead, several of them write **local** usage logs
(e.g. ``~/.claude/projects/**.jsonl``) that the external ``ccusage`` tool aggregates.

This module shells out to ``ccusage`` *if it's on PATH* and normalizes its JSON into the
same :class:`~synapse_worker.runtime.base.Usage` shape the API adapter emits, so
cost-per-run / caps / checkpoint accounting stay uniform across agent types.

Design rules (on-device cost guarantee):

  * Parsing stays **local** — we only ever read a CLI we found on this machine's PATH and
    never call out to a network service.
  * ``read_usage`` **never raises**. When ``ccusage`` is absent, errors, or doesn't cover
    the requested tool, we degrade to ``Usage(estimated=True)`` rather than reporting a
    wrong (zeroed) exact cost. Estimated-vs-exact is a first-class field consumers honor.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Optional

from ..logging import get_logger
from .base import Usage

log = get_logger(__name__)

# The agent "tool" families whose local logs stock ``ccusage`` can read. Other CLIs
# (aider, generic shell) aren't covered, so they fall through to estimated usage.
_CCUSAGE_TOOLS = {"claude", "claude-code", "claudecode"}

# How long we let ccusage run before giving up and degrading to estimated.
_CCUSAGE_TIMEOUT_SEC = 20


def read_usage(tool: str, *, run_window: Optional[tuple[float, float]] = None) -> Usage:
    """Best-effort exact usage for a finished CLI run; degrades to estimated.

    ``tool`` is the agent's CLI family (e.g. ``"claude"``). ``run_window`` is an optional
    ``(start_ts, end_ts)`` epoch-seconds pair reserved for future date-scoped queries; we
    accept it now so callers needn't change when scoping lands. Stock ``ccusage`` reports
    cumulative daily totals, so we currently ignore the window and flag the result
    estimated (it can't be attributed to a single run exactly).

    Never raises: any failure (missing CLI, bad JSON, unknown tool) returns
    ``Usage(estimated=True)``.
    """
    tool_key = (tool or "").strip().lower()
    if tool_key not in _CCUSAGE_TOOLS:
        # ccusage only covers Claude-family logs; everything else is unknown -> estimated.
        return Usage(estimated=True)

    exe = shutil.which("ccusage")
    if not exe:
        # The normal case on most boxes / CI: no Node CLI installed.
        return Usage(estimated=True)

    payload = _invoke_ccusage(exe)
    if payload is None:
        return Usage(estimated=True)

    usage = _parse_ccusage(payload)
    return usage if usage is not None else Usage(estimated=True)


def usage_from_cli_json(output: Any) -> Optional[Usage]:
    """Extract exact usage from a CLI's own ``--output-format json`` blob, if present.

    Some agents (e.g. ``claude -p --output-format json``) embed a ``usage``/``cost`` block
    in their structured stdout. When they do, that's an *exact*, local figure we prefer
    over (and don't need) ccusage for. Returns ``None`` when no recognizable usage block
    is found, so the caller can fall back to :func:`read_usage`.
    """
    block = _find_usage_block(output)
    if block is None:
        return None
    try:
        return Usage(
            input_tokens=_as_int(block, "input_tokens", "prompt_tokens", "inputTokens"),
            output_tokens=_as_int(
                block, "output_tokens", "completion_tokens", "outputTokens"
            ),
            cache_create_tokens=_as_int(
                block,
                "cache_create_tokens",
                "cache_creation_input_tokens",
                "cacheCreationInputTokens",
            ),
            cache_read_tokens=_as_int(
                block,
                "cache_read_tokens",
                "cache_read_input_tokens",
                "cacheReadInputTokens",
            ),
            cost_usd=_as_float(block, "cost_usd", "total_cost_usd", "costUSD", "cost"),
            estimated=False,
        )
    except Exception:  # noqa: BLE001 - any shape surprise degrades, never crashes a run
        return None


# ── internals ───────────────────────────────────────────────────────────────
def _invoke_ccusage(exe: str) -> Optional[Any]:
    """Run ``ccusage --json`` and return parsed JSON, or ``None`` on any failure."""
    try:
        proc = subprocess.run(
            [exe, "--json"],
            capture_output=True,
            text=True,
            timeout=_CCUSAGE_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("ccusage invocation failed: %s", exc)
        return None
    if proc.returncode != 0:
        log.debug("ccusage exited %s", proc.returncode)
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        log.debug("ccusage output was not JSON: %s", exc)
        return None


def _parse_ccusage(payload: Any) -> Optional[Usage]:
    """Normalize a ccusage ``--json`` payload into a :class:`Usage`.

    ccusage shapes vary across versions; we look for a ``totals`` object, else sum a list
    of daily/session rows. Because these are cumulative daily aggregates rather than a
    single run's exact spend, the result is flagged ``estimated=True``.
    """
    totals: Any = None
    if isinstance(payload, dict):
        totals = payload.get("totals")
        if totals is None:
            rows = _first_list(payload, "daily", "sessions", "data", "rows")
            if rows is not None:
                totals = _sum_rows(rows)
    elif isinstance(payload, list):
        totals = _sum_rows(payload)

    if not isinstance(totals, dict):
        return None

    return Usage(
        input_tokens=_as_int(totals, "inputTokens", "input_tokens"),
        output_tokens=_as_int(totals, "outputTokens", "output_tokens"),
        cache_create_tokens=_as_int(
            totals,
            "cacheCreationTokens",
            "cache_creation_tokens",
            "cacheCreationInputTokens",
        ),
        cache_read_tokens=_as_int(
            totals, "cacheReadTokens", "cache_read_tokens", "cacheReadInputTokens"
        ),
        cost_usd=_as_float(totals, "totalCost", "total_cost", "costUSD", "cost"),
        # Cumulative daily totals can't be attributed to one run exactly -> estimated.
        estimated=True,
    )


def _sum_rows(rows: Any) -> dict[str, float]:
    """Sum the numeric token/cost fields across a list of ccusage row dicts."""
    acc: dict[str, float] = {}
    if not isinstance(rows, list):
        return acc
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                acc[key] = acc.get(key, 0) + value
    return acc


def _first_list(payload: dict[str, Any], *keys: str) -> Optional[list[Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None


def _find_usage_block(output: Any) -> Optional[dict[str, Any]]:
    """Locate a ``usage``/``cost`` dict inside a CLI's structured output."""
    data: Any = output
    if isinstance(output, str):
        try:
            data = json.loads(output)
        except (ValueError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if isinstance(usage, dict):
        # Some CLIs put cost as a sibling of usage; merge so callers see both.
        merged = dict(usage)
        for cost_key in ("cost_usd", "total_cost_usd", "costUSD", "cost"):
            if cost_key in data and cost_key not in merged:
                merged[cost_key] = data[cost_key]
        return merged
    # Fall back: a flat dict that itself carries token fields.
    if any(k in data for k in ("input_tokens", "prompt_tokens", "inputTokens")):
        return data
    return None


def _as_int(d: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in d and isinstance(d[key], (int, float)) and not isinstance(d[key], bool):
            return int(d[key])
    return 0


def _as_float(d: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in d and isinstance(d[key], (int, float)) and not isinstance(d[key], bool):
            return round(float(d[key]), 6)
    return 0.0
