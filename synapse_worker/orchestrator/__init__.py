"""Agent orchestration (possible-features §2): local grant enforcement + run_agent.

The daemon caches a cloud-signed grant, verifies it **offline** (ed25519), and
enforces verb/target/same-daemon/depth/no-escalation locally before spawning a child
run — then streams async audit upstream. Public surface:

  * broker.authorize(...)         — the pure authorization decision (security core)
  * broker.cache_grant/drop_grant — grant cache (store-backed)
  * runner.run_agent(...)         — the run_agent flow (authorize → lineage → dispatch)
  * OrchestratorMcpServer         — the agent-facing MCP tool surface
"""
from .broker import (  # noqa: F401
    AuthzResult,
    Decision,
    authorize,
    cache_grant,
    drop_grant,
    grant_for_agent,
    lineage_append,
    lineage_update,
    set_trusted_grant_key,
)
from .mcp_server import OrchestratorMcpServer  # noqa: F401
from .runner import run_agent  # noqa: F401
