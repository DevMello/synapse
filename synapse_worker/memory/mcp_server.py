"""The built-in ``memory`` MCP server (§4.13 / §4.11 default capability).

CLI / tool-using agents (``claude``, ``aider``, …) reach memory as ordinary MCP tools.
``memory`` is one of the DEFAULT capabilities auto-attached to every agent
(``capabilities.registry.DEFAULT_CAPABILITIES``), so the same five API calls
(:mod:`synapse_worker.memory.api`) are exposed as tools:

    memory.store · memory.query · memory.get · memory.list · memory.delete

This is a transport-agnostic tool *surface*: each tool is a small async adapter that
validates its arguments and routes to the shared :class:`~synapse_worker.memory.api.MemoryAPI`
(so writes still pass through §4.5 redaction). A real stdio/SSE MCP transport can wrap
:class:`MemoryMcpServer` without changing the tool logic; the handlers are directly callable
(``await server.call("memory.store", {...})``) for tests and in-process use.

``agent_id`` is taken from the call args, else from the server's bound default (the runtime
binds one server instance per agent run), so a CLI agent never has to pass its own id.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from ..logging import get_logger
from .api import MemoryAPI, get_memory

log = get_logger(__name__)

ToolFn = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass
class ToolSpec:
    """One exposed MCP tool: a name, a one-line description, and its async handler."""

    name: str
    description: str
    handler: ToolFn


class MemoryMcpServer:
    """Exposes the memory API as five MCP tools.

    Construct with an optional ``default_agent_id`` (the runtime binds one per agent run) and
    an optional ``api`` override (tests inject a provider-bound API). ``tools()`` lists the
    specs; ``call(name, args)`` dispatches by name.
    """

    server_name = "memory"

    def __init__(
        self,
        *,
        default_agent_id: Optional[str] = None,
        api: Optional[MemoryAPI] = None,
    ) -> None:
        self._agent_id = default_agent_id
        self._api = api or get_memory()
        self._tools: dict[str, ToolSpec] = {}
        self._register_tools()

    # ── tool registry ─────────────────────────────────────────────────────
    def _register_tools(self) -> None:
        self._tools = {
            "memory.store": ToolSpec(
                "memory.store",
                "Persist a value under a key (with optional tags/namespace).",
                self._tool_store,
            ),
            "memory.query": ToolSpec(
                "memory.query",
                "Search memory by term (text or semantic); returns up to k matches.",
                self._tool_query,
            ),
            "memory.get": ToolSpec(
                "memory.get",
                "Fetch a single memory entry by key.",
                self._tool_get,
            ),
            "memory.list": ToolSpec(
                "memory.list",
                "List memory entries in a namespace (most recent first).",
                self._tool_list,
            ),
            "memory.delete": ToolSpec(
                "memory.delete",
                "Delete a memory entry by key.",
                self._tool_delete,
            ),
        }

    def tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def call(self, name: str, args: Optional[dict[str, Any]] = None) -> Any:
        """Dispatch an MCP tool call by name. Raises KeyError for an unknown tool."""
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"unknown memory tool: {name}")
        return await spec.handler(args or {})

    # ── argument resolution ───────────────────────────────────────────────
    def _resolve_agent_id(self, args: dict[str, Any]) -> str:
        agent_id = args.get("agent_id") or self._agent_id
        if not agent_id:
            raise ValueError("memory tool call missing agent_id")
        return str(agent_id)

    # ── tool handlers (thin adapters over the API) ─────────────────────────
    async def _tool_store(self, args: dict[str, Any]) -> dict[str, Any]:
        agent_id = self._resolve_agent_id(args)
        key = str(args["key"])
        value = str(args.get("value", ""))
        tags = args.get("tags") or []
        namespace = str(args.get("namespace", "default"))
        entry = await self._api.store(
            agent_id, key, value, tags=list(tags), namespace=namespace
        )
        return entry.to_dict()

    async def _tool_query(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        agent_id = self._resolve_agent_id(args)
        term = str(args.get("search_term", args.get("query", "")))
        k = int(args.get("k", 10))
        namespace = str(args.get("namespace", "default"))
        rows = await self._api.query(agent_id, term, k=k, namespace=namespace)
        return [r.to_dict() for r in rows]

    async def _tool_get(self, args: dict[str, Any]) -> Optional[dict[str, Any]]:
        agent_id = self._resolve_agent_id(args)
        key = str(args["key"])
        namespace = str(args.get("namespace", "default"))
        entry = await self._api.get(agent_id, key, namespace=namespace)
        return entry.to_dict() if entry else None

    async def _tool_list(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        agent_id = self._resolve_agent_id(args)
        namespace = str(args.get("namespace", "default"))
        limit = int(args.get("limit", 100))
        rows = await self._api.list(agent_id, namespace=namespace, limit=limit)
        return [r.to_dict() for r in rows]

    async def _tool_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        agent_id = self._resolve_agent_id(args)
        key = str(args["key"])
        namespace = str(args.get("namespace", "default"))
        deleted = await self._api.delete(agent_id, key, namespace=namespace)
        return {"deleted": deleted, "key": key, "namespace": namespace}


def build_memory_mcp_server(
    *, default_agent_id: Optional[str] = None, api: Optional[MemoryAPI] = None
) -> MemoryMcpServer:
    """Factory the runtime uses to bind a ``memory`` MCP server for an agent run."""
    return MemoryMcpServer(default_agent_id=default_agent_id, api=api)
