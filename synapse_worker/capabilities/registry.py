"""Two-tier capability registry (§4.11).

  * **Daemon tier** — a capability (MCP server / plugin / system tool) is *available* on
    this host once provisioned (``mark_available``).
  * **Agent tier** — each agent *selects* which available capabilities it may use
    (``attach`` / ``detach``). The Ruleset Engine enforces selection at run time, so an
    unattached capability is simply not callable.

Default state is "defaults on, rest off": the built-in defaults
(filesystem/fetch/git/memory) are auto-attached to every agent (still detachable), and
every other capability is opt-in per agent.

This registry is the in-memory selection state; durability is in the SQLite store
(``capabilities`` / ``agent_capabilities`` tables) maintained by the plugin unit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Built-in MCP servers auto-attached to every agent (§4.11).
DEFAULT_CAPABILITIES: tuple[str, ...] = ("filesystem", "fetch", "git", "memory")


@dataclass
class Capability:
    name: str
    kind: str = "mcp"          # mcp | script | workspace | composite
    status: str = "ready"      # installing | ready | failed
    tools: list[str] = field(default_factory=list)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._available: dict[str, Capability] = {}
        # Per-agent explicit attach/detach overrides on top of the defaults.
        self._attached: dict[str, set[str]] = {}
        self._detached_defaults: dict[str, set[str]] = {}
        for name in DEFAULT_CAPABILITIES:
            self._available[name] = Capability(name=name, kind="mcp", status="ready")

    # ── daemon tier ───────────────────────────────────────────────────────
    def mark_available(self, cap: Capability) -> None:
        self._available[cap.name] = cap

    def remove_available(self, name: str) -> None:
        self._available.pop(name, None)
        for s in self._attached.values():
            s.discard(name)

    def is_available(self, name: str) -> bool:
        return name in self._available

    def available(self) -> list[Capability]:
        return list(self._available.values())

    def get(self, name: str) -> Optional[Capability]:
        return self._available.get(name)

    # ── agent tier ────────────────────────────────────────────────────────
    def attach(self, agent_id: str, name: str) -> None:
        self._attached.setdefault(agent_id, set()).add(name)
        self._detached_defaults.get(agent_id, set()).discard(name)

    def detach(self, agent_id: str, name: str) -> None:
        self._attached.get(agent_id, set()).discard(name)
        if name in DEFAULT_CAPABILITIES:
            self._detached_defaults.setdefault(agent_id, set()).add(name)

    def attached(self, agent_id: str) -> set[str]:
        """Effective attachments: defaults (minus detached) plus explicit attaches."""
        eff = {c for c in DEFAULT_CAPABILITIES
               if c not in self._detached_defaults.get(agent_id, set())}
        eff |= self._attached.get(agent_id, set())
        return {c for c in eff if c in self._available}

    def is_attached(self, agent_id: str, name: str) -> bool:
        return name in self.attached(agent_id)


_registry: CapabilityRegistry = CapabilityRegistry()


def get_capability_registry() -> CapabilityRegistry:
    return _registry


def reset_capability_registry() -> None:  # test helper
    global _registry
    _registry = CapabilityRegistry()
