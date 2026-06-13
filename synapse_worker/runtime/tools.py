"""Tool execution seam + blast-radius classification (§4.3 / §10.5).

The API adapter runs an agentic tool-calling loop: the model proposes a tool, the daemon
executes it through a :class:`ToolExecutor`, and the result is fed back. This module owns:

  * :class:`ToolExecutor` — the protocol the loop calls; the default runs a small set of
    harmless **read-only** builtins and any tool registered on it.
  * **blast-radius classification** (``read_only`` / ``side_effecting`` / ``hitl_gated``) —
    derived from the agent manifest's ``[[tools]]`` entries (operator-declared), with a
    conservative default of ``side_effecting`` for anything unknown.

Classification is independent of execution so the §10 draft-mode shim
(:mod:`synapse_worker.comparison.draft_shim`) can wrap *any* executor and decide — per call,
below the model — whether to run it for real or simulate it. A wrong/missing classification
degrades to *over*-simulating (safe), never to executing an unexpected side effect.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Protocol, runtime_checkable

# ── blast-radius classes ────────────────────────────────────────────────────
READ_ONLY = "read_only"
SIDE_EFFECTING = "side_effecting"
HITL_GATED = "hitl_gated"

_VALID_CLASSES = {READ_ONLY, SIDE_EFFECTING, HITL_GATED}

# A few well-known builtin tool names whose class is obvious. Operator manifest entries
# always win over this; it only seeds a sensible default for un-annotated builtins.
_BUILTIN_CLASS = {
    "echo": READ_ONLY,
    "now": READ_ONLY,
    "read_file": READ_ONLY,
    "search": READ_ONLY,
    "fetch": READ_ONLY,
    "http_get": READ_ONLY,
    "list_dir": READ_ONLY,
}


def classify_tool(name: str, manifest_tools: Optional[list[dict[str, Any]]] = None) -> str:
    """Return the blast-radius class for ``name``.

    Precedence: the manifest ``[[tools]]`` entry's ``blast_radius`` (operator-declared) →
    a builtin default → ``side_effecting`` (conservative: an unknown tool is never run for
    real in draft mode). An ``hitl`` flag on the tool entry maps to ``hitl_gated``.
    """
    for t in manifest_tools or []:
        if not isinstance(t, dict) or str(t.get("name")) != name:
            continue
        raw = str(t.get("blast_radius") or "").strip().lower()
        if raw in _VALID_CLASSES:
            return raw
        if t.get("hitl") or t.get("require_approval"):
            return HITL_GATED
        if t.get("read_only") is True:
            return READ_ONLY
        if t.get("side_effecting") is True:
            return SIDE_EFFECTING
        break
    return _BUILTIN_CLASS.get(name, SIDE_EFFECTING)


# ── tool execution seam ─────────────────────────────────────────────────────
@dataclass
class ToolCall:
    """One model-proposed tool invocation, normalized across providers."""

    id: str
    name: str
    args: dict[str, Any]


@runtime_checkable
class ToolExecutor(Protocol):
    async def execute(self, name: str, args: dict[str, Any]) -> Any: ...


ToolFn = Callable[[dict[str, Any]], Awaitable[Any]]


class DefaultToolExecutor:
    """Executes registered tools; ships a couple of harmless read-only builtins.

    Unknown tools return a typed error result (never raise) so the agentic loop can feed a
    result back and let the model recover instead of crashing the run.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolFn] = {}
        self.register("echo", self._echo)

    def register(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        fn = self._tools.get(name)
        if fn is None:
            return {"error": f"unknown tool {name!r}"}
        try:
            return await fn(args)
        except Exception as exc:  # noqa: BLE001 - a tool failure is a result, not a crash
            return {"error": str(exc)}

    @staticmethod
    async def _echo(args: dict[str, Any]) -> Any:
        return {"echo": args}
