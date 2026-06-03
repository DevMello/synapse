"""``skill.install`` command handler (§4.2 / §4.3).

Skills are *knowledge* (prompts/instructions) — what an agent KNOWS — as opposed to
plugins (capabilities). They live as versioned files under the agent directory and are
rendered with the prompt at run time. Installing a skill writes its content to
``~/.synapse/agents/{agent_id}/skills/{name}`` with owner-only perms.

This completes the §4.2 command surface; the cloud relays a marketplace skill install as
a ``skill.install`` command. Payload is read defensively:

    {"agent_id": str, "name": str, "content": str, "version"?: int, "format"?: "md"|"toml"}
"""
from __future__ import annotations

from typing import Any

from ..logging import get_logger
from ..paths import get_paths, secure_write
from ..router import CommandContext, on_command

log = get_logger(__name__)


def _agent_id(ctx: CommandContext, payload: dict[str, Any]) -> str | None:
    if payload.get("agent_id"):
        return str(payload["agent_id"])
    # Fall back to the idempotency key shape skill.install:{agent_id}:{name}.
    if ctx.idempotency_key and ctx.idempotency_key.startswith("skill.install:"):
        parts = ctx.idempotency_key.split(":")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return None


@on_command("skill.install")
async def handle_skill_install(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Write a skill file under the target agent's ``skills/`` dir (versioned)."""
    agent_id = _agent_id(ctx, payload)
    name = payload.get("name") or payload.get("skill")
    content = payload.get("content")
    if not agent_id or not name or content is None:
        log.warning("skill.install: missing agent_id/name/content; ignoring")
        return

    fmt = payload.get("format") or "md"
    filename = name if "." in str(name) else f"{name}.{fmt}"
    skills_dir = get_paths().agent_dir(agent_id) / "skills"
    target = skills_dir / filename
    try:
        secure_write(target, content if isinstance(content, str) else str(content))
        log.info("installed skill %s for agent %s", name, agent_id)
    except Exception:  # noqa: BLE001 - a bad path/IO shouldn't crash the control loop
        log.exception("skill.install: failed to write skill %s", name)
