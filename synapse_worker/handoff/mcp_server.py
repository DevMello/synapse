"""The built-in ``handoff`` MCP server (§11.4).

An **elevated** capability (NOT auto-attached) whose single dangerous verb passes the
current task to a successor in a **pre-approved chain**. Unlike the ``orchestrator``
server it has **no create/edit and no fan-out** — a sequential baton-pass only. The
runtime binds one instance per agent run with the caller's run_id/agent_id/daemon_id/hop,
so a CLI/tool agent calls ``synapse.handoff({"to": ...})`` without passing its own identity.

Mirrors the ``orchestrator`` MCP server surface (ToolSpec dict + ``call(name, args)``).
"""
from __future__ import annotations

from typing import Any, Optional

from ..logging import get_logger
from ..memory.mcp_server import ToolSpec  # reuse the shared ToolSpec shape
from .broker import successors
from .runner import handoff

log = get_logger(__name__)


class HandoffMcpServer:
    server_name = "handoff"

    def __init__(
        self,
        *,
        default_run_id: Optional[str] = None,
        default_agent_id: Optional[str] = None,
        daemon_id: Optional[str] = None,
        caller_hop: int = 0,
    ) -> None:
        self._run_id = default_run_id
        self._agent_id = default_agent_id
        self._daemon_id = daemon_id
        self._hop = caller_hop
        self._tools: dict[str, ToolSpec] = {}
        self._register_tools()

    def _register_tools(self) -> None:
        self._tools = {
            "synapse.list_chain": ToolSpec(
                "synapse.list_chain",
                "List the successors this agent may hand off to (scoped to the chain grant).",
                self._tool_list_chain,
            ),
            "synapse.handoff": ToolSpec(
                "synapse.handoff",
                "Pass the current task to a successor named in the chain grant (tail mode).",
                self._tool_handoff,
            ),
            "synapse.handoff_return": ToolSpec(
                "synapse.handoff_return",
                "Pause self, run a successor, resume with its result (return mode; one-at-a-time).",
                self._tool_handoff_return,
            ),
        }

    def tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def call(self, name: str, args: Optional[dict[str, Any]] = None) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"unknown handoff tool: {name}")
        return await spec.handler(args or {})

    # ── tools ─────────────────────────────────────────────────────────────────
    async def _tool_list_chain(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"successors": await successors(str(self._agent_id))}

    async def _handoff(self, args: dict[str, Any], mode: str) -> dict[str, Any]:
        to = args.get("to") or args.get("agent_id")
        if not to:
            raise ValueError("handoff requires 'to' (a successor agent id)")
        return await handoff(
            caller_run_id=self._run_id,
            from_agent_id=str(self._agent_id),
            daemon_id=str(self._daemon_id),
            to_agent_id=str(to),
            context=args.get("context") or {},
            mode=mode,
            caller_hop=self._hop,
        )

    async def _tool_handoff(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._handoff(args, "tail")

    async def _tool_handoff_return(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._handoff(args, "return")
