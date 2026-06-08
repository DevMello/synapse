"""The built-in ``orchestrator`` MCP server (§2.2).

An **elevated** capability (NOT auto-attached) whose tools translate into upstream-
authorized control of *other agents on this daemon*. The runtime binds one instance per
agent run with the caller's run_id/agent_id/daemon_id/depth, so a CLI/tool agent calls
``orchestrator.run_agent({"agent_id": ...})`` without passing its own identity.

Mirrors the ``memory`` MCP server surface (ToolSpec dict + ``call(name, args)``), so a
real stdio/SSE transport can wrap it unchanged and tests call it in-process.
"""
from __future__ import annotations

from typing import Any, Optional

from ..logging import get_logger
from ..memory.mcp_server import ToolSpec  # reuse the shared ToolSpec shape
from ..store import get_store
from .runner import run_agent

log = get_logger(__name__)


class OrchestratorMcpServer:
    server_name = "orchestrator"

    def __init__(
        self,
        *,
        default_run_id: Optional[str] = None,
        default_agent_id: Optional[str] = None,
        daemon_id: Optional[str] = None,
        caller_depth: int = 0,
    ) -> None:
        self._run_id = default_run_id
        self._agent_id = default_agent_id
        self._daemon_id = daemon_id
        self._depth = caller_depth
        self._tools: dict[str, ToolSpec] = {}
        self._register_tools()

    def _register_tools(self) -> None:
        self._tools = {
            "orchestrator.list_agents": ToolSpec(
                "orchestrator.list_agents",
                "List agents deployed on this daemon the caller may target.",
                self._tool_list_agents,
            ),
            "orchestrator.get_run": ToolSpec(
                "orchestrator.get_run",
                "Read status/usage of a run by id.",
                self._tool_get_run,
            ),
            "orchestrator.run_agent": ToolSpec(
                "orchestrator.run_agent",
                "Trigger a run of an already-approved sibling agent (within grant + budget).",
                self._tool_run_agent,
            ),
            "orchestrator.create_agent": ToolSpec(
                "orchestrator.create_agent",
                "Create a new agent on this daemon (requires human approval).",
                self._tool_create_agent,
            ),
            "orchestrator.edit_agent": ToolSpec(
                "orchestrator.edit_agent",
                "Edit a sibling agent's prompt/config (requires human approval).",
                self._tool_edit_agent,
            ),
        }

    def tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def call(self, name: str, args: Optional[dict[str, Any]] = None) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"unknown orchestrator tool: {name}")
        return await spec.handler(args or {})

    # ── tools ─────────────────────────────────────────────────────────────────
    async def _tool_list_agents(self, args: dict[str, Any]) -> dict[str, Any]:
        rows = await get_store().fetchall("SELECT id, name, type FROM agents ORDER BY name")
        return {"agents": rows}

    async def _tool_get_run(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = args.get("run_id")
        if not run_id:
            raise ValueError("get_run requires run_id")
        row = await get_store().fetchone(
            "SELECT run_id, agent_id, status, cost_usd, tokens_input, tokens_output FROM run_history WHERE run_id=?",
            (run_id,),
        )
        return row or {"run_id": run_id, "status": "unknown"}

    async def _tool_run_agent(self, args: dict[str, Any]) -> dict[str, Any]:
        target = args.get("agent_id") or args.get("target")
        if not target:
            raise ValueError("run_agent requires agent_id")
        return await run_agent(
            caller_run_id=self._run_id,
            caller_agent_id=str(self._agent_id),
            daemon_id=str(self._daemon_id),
            target_agent_id=str(target),
            prompt_vars=args.get("prompt_vars"),
            caller_depth=self._depth,
        )

    async def _tool_create_agent(self, args: dict[str, Any]) -> dict[str, Any]:
        # MVP: create/edit are gated behind HITL and not exercised; the broker would
        # return REQUIRE_HITL and the daemon would raise a hitl.request.
        return {"decision": "require_hitl", "reason": "create_agent requires human approval"}

    async def _tool_edit_agent(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"decision": "require_hitl", "reason": "edit_agent requires human approval"}
