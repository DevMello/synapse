"""Ruleset / blocker engine implementation (§4.6).

Per-agent policy enforced by the *daemon* (not the model), BEFORE and DURING execution.
The engine answers five checks — command, write-path, network, capability, cost — each
returning a :class:`Decision` the runtime maps to block / pause-for-HITL / warn. The model
never sees this layer; it is a hard gate the daemon owns.

Policy shape (per agent or the global default), all keys optional::

    {
      "commands": {"deny": [<regex>...], "allow": [<regex>...],
                   "default": "allow", "action": "block"},
      "write_paths": {"allow": ["/repo", "./work"], "action": "block"},
      "network":    {"allow": ["api.github.com"], "action": "block"},
      "caps":       {"action": "block"},
      "limits":     {"max_cost_usd": 2.0, "max_tool_calls": 50, "action": "block"},
    }

Resolution: a per-agent policy (via :meth:`set_agent_policy` or loaded from an agent's
``agent.toml`` ``[ruleset]`` / ``[limits]`` section) is merged over a global default. A
missing section falls back to the safe built-in behaviour described below.

Built-in defaults (why these, when a section is absent or silent):
  * commands — a curated deny-list of irreversibly destructive shells (``rm -rf``, forced
    pushes, ``DROP TABLE``, ``mkfs``, fork-bomb, raw ``dd``) is ALWAYS active; the
    per-agent allow-list can override an otherwise-denied command. Unmatched commands are
    allowed (``default: allow``) unless the policy flips ``default`` to ``deny``.
  * write_paths — with an allow-list set, a write outside every prefix is blocked; with no
    allow-list, writes are unrestricted. Reads are deliberately NOT guarded (project docs
    defer read-path guarding).
  * network — with an allow-list set, an off-list host is blocked; with no allow-list,
    outbound is unrestricted.
  * caps — a capability must be ATTACHED to the agent (consulting the capability registry);
    an unattached capability is not callable.
  * limits — a run that exceeds ``max_cost_usd`` or ``max_tool_calls`` is hard-stopped.

The plugin / ``mcp.configure`` unit feeds real policy in later via :meth:`set_agent_policy`;
this engine only exposes the setter and never imports that unit.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..capabilities.registry import get_capability_registry
from ..logging import get_logger
from ..runtime.base import AgentManifest
from .base import Action, Decision

log = get_logger(__name__)

# Built-in destructive-command denials, matched against whitespace-normalised, lower-cased
# command text (see :func:`_normalize`). Patterns are intentionally broad — substring-style
# — so flag reorderings and extra spacing don't slip a dangerous command through. Each entry
# is (label, regex); the label is surfaced in the Decision for audit.
_BUILTIN_DENY: tuple[tuple[str, str], ...] = (
    # rm with recursive AND force, flags combined or separate, any order:
    # "rm -rf", "rm -fr", "rm -r -f", "rm --recursive --force", incl. `sudo rm …`.
    # Requires BOTH r and f so a benign `rm -f file` is not blocked.
    ("rm_rf", r"\brm\b\s+-\S*r\S*f|\brm\b\s+-\S*f\S*r"
              r"|\brm\b\s+-\S*r\b.*\s-\S*f|\brm\b\s+-\S*f\b.*\s-\S*r"
              r"|\brm\b.*--recursive\b.*--force|\brm\b.*--force\b.*--recursive"),
    # forced git push: --force, --force-with-lease, or -f
    ("git_force_push", r"\bgit\s+push\b.*(?:--force(?:-with-lease)?|\s-\w*f)"),
    # SQL DROP TABLE / DROP DATABASE
    ("sql_drop", r"\bdrop\s+(?:table|database)\b"),
    # filesystem format
    ("mkfs", r"\bmkfs(?:\.\w+)?\b"),
    # classic bash fork-bomb :(){ :|:& };:  (normalised drops most spacing)
    ("fork_bomb", r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
    # raw disk write via dd
    ("dd_disk", r"\bdd\b\s+if="),
    # pipe a remote script straight into a shell (curl … | sh)
    ("curl_pipe_shell", r"\b(?:curl|wget)\b.*\|\s*(?:sudo\s+)?(?:ba)?sh\b"),
)

# Per-policy action keyword → Action. Unknown / missing keywords fall back to BLOCK because
# a violation defaulting to "allow" would defeat the guard.
_ACTIONS: dict[str, Action] = {
    "allow": Action.ALLOW,
    "warn": Action.WARN,
    "require-approval": Action.REQUIRE_HITL,
    "hitl": Action.REQUIRE_HITL,
    "block": Action.BLOCK,
}


def _resolve_action(section: dict[str, Any], default: Action = Action.BLOCK) -> Action:
    raw = str(section.get("action", "")).strip().lower()
    return _ACTIONS.get(raw, default)


def _normalize(command: str) -> str:
    """Collapse whitespace and lower-case so spacing / case variants match one pattern."""
    return re.sub(r"\s+", " ", command.strip().lower())


def _compile(patterns: Any) -> list[re.Pattern[str]]:
    out: list[re.Pattern[str]] = []
    for p in patterns or []:
        try:
            out.append(re.compile(p, re.IGNORECASE))
        except re.error as exc:  # a bad operator-supplied regex must not crash the gate
            log.warning("ruleset: ignoring invalid pattern %r: %s", p, exc)
    return out


def _norm_prefix(path: str) -> str:
    """Normalise a path for prefix comparison.

    Separators are unified to ``/`` so a Windows ``\\`` allow-list still matches a ``/``
    write (and vice-versa); a single trailing slash is dropped (root ``/`` kept). Case is
    preserved — we do not assume a case-insensitive filesystem.
    """
    p = path.strip().replace("\\", "/")
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


class RulesetEngine:
    """Daemon-side policy gate implementing the foundation :class:`Ruleset` protocol.

    Holds a global default policy plus per-agent overrides. All five checks are pure
    functions of (input, resolved policy, capability registry) — no I/O, no model calls —
    so they are cheap to run on every command / write / network call / capability use.
    """

    name = "ruleset-engine"

    def __init__(self, default_policy: Optional[dict[str, Any]] = None) -> None:
        self._default: dict[str, Any] = dict(default_policy or {})
        self._by_agent: dict[str, dict[str, Any]] = {}

    # ── policy management ────────────────────────────────────────────────────
    def set_default_policy(self, policy: dict[str, Any]) -> None:
        self._default = dict(policy or {})

    def set_agent_policy(self, agent_id: str, policy: dict[str, Any]) -> None:
        self._by_agent[agent_id] = dict(policy or {})

    def clear_agent_policy(self, agent_id: str) -> None:
        self._by_agent.pop(agent_id, None)

    def load_agent_policy_from_manifest(self, manifest: AgentManifest) -> dict[str, Any]:
        """Defensively lift a policy from an agent.toml.

        Reads a free-form ``[ruleset]`` block if present and folds the standard
        ``[limits]`` (max_cost_usd / max_tool_calls) into the policy's ``limits`` section so
        cost caps work even when only ``[limits]`` is declared. Registers it for the agent
        and returns it. Never raises on a malformed/missing section — a bad manifest must
        not disable the gate.
        """
        policy: dict[str, Any] = {}
        ruleset = manifest.raw.get("ruleset") if isinstance(manifest.raw, dict) else None
        if isinstance(ruleset, dict):
            policy = dict(ruleset)
        # Fold manifest limits in (existing policy limits take precedence via setdefault).
        existing = policy.get("limits")
        limits = dict(existing) if isinstance(existing, dict) else {}
        if manifest.max_cost_usd is not None:
            limits.setdefault("max_cost_usd", manifest.max_cost_usd)
        if manifest.max_tool_calls is not None:
            limits.setdefault("max_tool_calls", manifest.max_tool_calls)
        if limits:
            policy["limits"] = limits
        self.set_agent_policy(manifest.id, policy)
        return policy

    def _policy_for(self, agent_id: str) -> dict[str, Any]:
        """Per-agent policy merged over the global default (one level deep per section)."""
        if agent_id not in self._by_agent:
            return self._default
        merged: dict[str, Any] = dict(self._default)
        for key, val in self._by_agent[agent_id].items():
            if isinstance(val, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **val}
            else:
                merged[key] = val
        return merged

    @staticmethod
    def _section(policy: dict[str, Any], key: str) -> dict[str, Any]:
        sec = policy.get(key, {})
        return sec if isinstance(sec, dict) else {}

    # ── checks ───────────────────────────────────────────────────────────────
    def check_command(self, command: str, *, agent_id: str) -> Decision:
        norm = _normalize(command)
        if not norm:
            return Decision.allow()
        section = self._section(self._policy_for(agent_id), "commands")

        # Allow-list overrides everything — an explicitly-allowed command is never blocked,
        # even if it matches a built-in or policy deny pattern.
        for pat in _compile(section.get("allow")):
            if pat.search(norm):
                return Decision(
                    action=Action.ALLOW,
                    rule="command.allow",
                    reason="matched agent allow-list",
                    detail={"command": norm},
                )

        action = _resolve_action(section, Action.BLOCK)

        # Built-in dangerous-command denials are always active.
        for label, pat in _BUILTIN_DENY:
            if re.search(pat, norm, re.IGNORECASE):
                return Decision(
                    action=action,
                    rule=f"command.deny.builtin.{label}",
                    reason="matched built-in dangerous-command denial",
                    detail={"command": norm, "pattern": label},
                )

        # Policy-supplied deny patterns.
        for pat in _compile(section.get("deny")):
            if pat.search(norm):
                return Decision(
                    action=action,
                    rule="command.deny",
                    reason="matched agent deny-list",
                    detail={"command": norm, "pattern": pat.pattern},
                )

        # No deny match: honour the section default (default-deny posture if configured).
        if str(section.get("default", "allow")).strip().lower() == "deny":
            return Decision(
                action=action,
                rule="command.default-deny",
                reason="command not on allow-list (default deny)",
                detail={"command": norm},
            )
        return Decision.allow()

    def check_path(self, path: str, *, agent_id: str, write: bool = True) -> Decision:
        # Reads are deliberately unguarded (read-path guarding is deferred per project docs).
        if not write:
            return Decision.allow()
        section = self._section(self._policy_for(agent_id), "write_paths")
        allow = section.get("allow")
        # No allow-list configured → writes unrestricted.
        if not allow:
            return Decision.allow()
        target = _norm_prefix(path)
        for prefix in allow:
            pref = _norm_prefix(str(prefix))
            # Prefix match on a path boundary: "/repo" matches "/repo" and "/repo/x" but
            # NOT "/repofoo".
            if target == pref or target.startswith(pref.rstrip("/") + "/"):
                return Decision(
                    action=Action.ALLOW,
                    rule="write_paths.allow",
                    reason="write inside an allowed prefix",
                    detail={"path": target, "prefix": pref},
                )
        return Decision(
            action=_resolve_action(section, Action.BLOCK),
            rule="write_paths.deny",
            reason="write outside every allowed prefix",
            detail={"path": target, "allow": [str(p) for p in allow]},
        )

    def check_network(self, host: str, *, agent_id: str) -> Decision:
        section = self._section(self._policy_for(agent_id), "network")
        allow = section.get("allow")
        # No allow-list configured → outbound unrestricted.
        if not allow:
            return Decision.allow()
        target = host.strip().lower()
        for entry in allow:
            e = str(entry).strip().lower()
            # Exact host, or a leading-dot / bare suffix wildcard ("github.com" allows
            # "api.github.com"; ".github.com" allows subdomains but not the apex).
            if target == e:
                return Decision(
                    action=Action.ALLOW, rule="network.allow",
                    reason="host on allow-list", detail={"host": target},
                )
            suffix = e[1:] if e.startswith(".") else e
            if suffix and target.endswith("." + suffix):
                return Decision(
                    action=Action.ALLOW, rule="network.allow",
                    reason="host matched allowed domain",
                    detail={"host": target, "domain": e},
                )
        return Decision(
            action=_resolve_action(section, Action.BLOCK),
            rule="network.deny",
            reason="host not on allow-list",
            detail={"host": target, "allow": [str(a) for a in allow]},
        )

    def check_capability(self, capability: str, *, agent_id: str) -> Decision:
        # An agent may only invoke a capability ATTACHED to it (defaults auto-attached).
        if get_capability_registry().is_attached(agent_id, capability):
            return Decision(
                action=Action.ALLOW, rule="caps.attached",
                reason="capability attached to agent",
                detail={"capability": capability},
            )
        section = self._section(self._policy_for(agent_id), "caps")
        return Decision(
            action=_resolve_action(section, Action.BLOCK),
            rule="caps.not-attached",
            reason="capability not attached to agent",
            detail={"capability": capability},
        )

    def check_cost(self, cost_usd: float, tool_calls: int, *, agent_id: str) -> Decision:
        section = self._section(self._policy_for(agent_id), "limits")
        action = _resolve_action(section, Action.BLOCK)
        max_cost = section.get("max_cost_usd")
        if max_cost is not None and cost_usd > float(max_cost):
            return Decision(
                action=action, rule="limits.max_cost_usd",
                reason="run exceeded its cost cap",
                detail={"cost_usd": cost_usd, "max_cost_usd": float(max_cost)},
            )
        max_calls = section.get("max_tool_calls")
        if max_calls is not None and tool_calls > int(max_calls):
            return Decision(
                action=action, rule="limits.max_tool_calls",
                reason="run exceeded its tool-call cap",
                detail={"tool_calls": tool_calls, "max_tool_calls": int(max_calls)},
            )
        return Decision.allow()
