"""Draft-mode tool shim — the key §10.5 mechanic.

A comparison variant must produce a realistic trace **without causing real side effects**:
running N models live would mean N× duplicate emails/pushes (E3). The shim wraps any
:class:`~synapse_worker.runtime.tools.ToolExecutor` and classifies each call below the model:

| class           | behavior                                                                  |
|-----------------|---------------------------------------------------------------------------|
| ``read_only``   | execute normally — no side effect, feeds the model a real result          |
| ``side_effecting`` | do NOT execute — record a redacted *proposed action*, return a typed stub |
| ``hitl_gated``  | do NOT page a human — record "would have paused", treat as approved-for-sim |

Each variant therefore yields a list of actions it *would* have taken, fully
redaction-screened (Layer A), plus a per-model "human intervention necessary" count. The
classification is conservative: an unknown tool defaults to ``side_effecting`` (simulated),
so the shim can only ever *over*-simulate, never run an unexpected side effect.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..filtering.base import Direction
from ..filtering.redaction import RedactionFilter
from ..runtime.tools import HITL_GATED, READ_ONLY, ToolExecutor, classify_tool


@dataclass
class DraftCollector:
    """Per-variant record of everything the draft run observed.

    ``tool_calls`` is every call (read-only + simulated); ``proposed_actions`` is the subset
    of side-effecting/HITL calls it *would* have made; ``simulated_hitl`` is the "would have
    paused for approval" points (the per-model human-intervention metric, §10.6).
    """

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    proposed_actions: list[dict[str, Any]] = field(default_factory=list)
    simulated_hitl: list[dict[str, Any]] = field(default_factory=list)


class DraftToolExecutor:
    """Wrap an inner executor; simulate side-effecting/HITL calls, run read-only ones.

    Reuses the same checkpoint-style intent recording as a normal run — the call is
    journaled exactly as usual, only its *execution* is suppressed for non-read-only tools.
    """

    def __init__(
        self,
        inner: ToolExecutor,
        collector: DraftCollector,
        manifest_tools: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._inner = inner
        self.collector = collector
        self._tools = manifest_tools or []
        self._redactor = RedactionFilter()

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        cls = classify_tool(name, self._tools)
        redacted = self._redact(args)
        simulated = cls != READ_ONLY
        self.collector.tool_calls.append(
            {"name": name, "args_redacted": redacted, "blast_radius": cls, "simulated": simulated}
        )

        if cls == READ_ONLY:
            # No side effect — run it so the model continues realistically (§10.5).
            return await self._inner.execute(name, args)

        if cls == HITL_GATED:
            # Don't page a human; record the intervention point + the proposed action, then
            # treat as approved-for-simulation so the variant continues (§10.5).
            marker = {"name": name, "args_redacted": redacted}
            self.collector.simulated_hitl.append(marker)
            self.collector.proposed_actions.append({**marker, "hitl": True})
            return {"status": "ok", "simulated": True, "would_have_paused": True}

        # side_effecting: record the intended call + redacted args, return a typed stub.
        self.collector.proposed_actions.append({"name": name, "args_redacted": redacted})
        return {"status": "ok", "simulated": True}

    # ── redaction (Layer A) ───────────────────────────────────────────────
    def _redact(self, value: Any) -> Any:
        """Screen any inline string content through Layer A before it is recorded/leaves."""
        if isinstance(value, str):
            return self._redactor.screen(value, direction=Direction.OUTBOUND).text
        if isinstance(value, dict):
            return {k: self._redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        return value
