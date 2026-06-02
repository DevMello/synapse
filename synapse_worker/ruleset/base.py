"""Ruleset / blocker engine base (§4.6).

Per-agent policy enforced by the *daemon* (not the model): command allow/deny, write-path
guards, network host allow-list, capability/MCP gating, and cost/tool-call caps. Each
check returns a :class:`Decision`; the runtime maps it to block / pause-for-HITL / warn.

The foundation ships a :class:`PermissiveRuleset` (allow everything) so the runtime works
before the real engine lands. The engine unit installs its implementation via
:func:`set_ruleset`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class Action(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    REQUIRE_HITL = "require-approval"
    BLOCK = "block"


@dataclass
class Decision:
    action: Action = Action.ALLOW
    rule: str = ""
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.action in (Action.ALLOW, Action.WARN)

    @property
    def needs_hitl(self) -> bool:
        return self.action is Action.REQUIRE_HITL

    @classmethod
    def allow(cls) -> "Decision":
        return cls(action=Action.ALLOW)


@runtime_checkable
class Ruleset(Protocol):
    def check_command(self, command: str, *, agent_id: str) -> Decision: ...
    def check_path(self, path: str, *, agent_id: str, write: bool = True) -> Decision: ...
    def check_network(self, host: str, *, agent_id: str) -> Decision: ...
    def check_capability(self, capability: str, *, agent_id: str) -> Decision: ...
    def check_cost(
        self, cost_usd: float, tool_calls: int, *, agent_id: str
    ) -> Decision: ...


class PermissiveRuleset:
    """Default engine — allows everything (foundation/no-policy fallback)."""

    name = "permissive"

    def check_command(self, command: str, *, agent_id: str) -> Decision:
        return Decision.allow()

    def check_path(self, path: str, *, agent_id: str, write: bool = True) -> Decision:
        return Decision.allow()

    def check_network(self, host: str, *, agent_id: str) -> Decision:
        return Decision.allow()

    def check_capability(self, capability: str, *, agent_id: str) -> Decision:
        return Decision.allow()

    def check_cost(self, cost_usd: float, tool_calls: int, *, agent_id: str) -> Decision:
        return Decision.allow()


_ruleset: Ruleset = PermissiveRuleset()


def get_ruleset() -> Ruleset:
    return _ruleset


def set_ruleset(ruleset: Ruleset) -> None:
    global _ruleset
    _ruleset = ruleset


def reset_ruleset() -> None:  # test helper
    global _ruleset
    _ruleset = PermissiveRuleset()
