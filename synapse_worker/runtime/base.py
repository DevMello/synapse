"""Agent runtime base protocols (§4.3).

Shared shapes the API and CLI adapters both produce, so cost-per-run, caps, and
checkpoint accounting are uniform across agent types:

  * :class:`Usage` — normalized token/cost accounting.
  * :class:`AgentManifest` — a parsed ``agent.toml`` (synced from the cloud).
  * :class:`TraceEvent` / :class:`RunContext` — the live reasoning trace surface.
  * :class:`Adapter` — the run interface; adapters register by ``type`` ("api"/"cli").

The engine and adapters live in sibling modules added by feature units; this file only
declares the contract + a registry seam so they don't import each other directly.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol, runtime_checkable

from ..errors import ManifestError

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


# ── usage / cost accounting ─────────────────────────────────────────────────
@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_create_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    estimated: bool = False  # True when cost couldn't be derived exactly (§4.3 CLI)

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_create_tokens=self.cache_create_tokens + other.cache_create_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cost_usd=round(self.cost_usd + other.cost_usd, 6),
            estimated=self.estimated or other.estimated,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_create_tokens": self.cache_create_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cost_usd": self.cost_usd,
            "estimated": self.estimated,
        }


# ── agent manifest (agent.toml) ─────────────────────────────────────────────
@dataclass
class AgentManifest:
    id: str
    name: str
    type: str  # "api" | "cli"
    platform: str = "any"
    version: int = 1
    api: dict[str, Any] = field(default_factory=dict)
    cli: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentManifest":
        agent = data.get("agent", {})
        if not agent.get("id"):
            raise ManifestError("agent.toml missing [agent].id")
        return cls(
            id=agent["id"],
            name=agent.get("name", agent["id"]),
            type=agent.get("type", "api"),
            platform=agent.get("platform", "any"),
            version=int(agent.get("version", 1)),
            api=data.get("api", {}),
            cli=data.get("cli", {}),
            limits=data.get("limits", {}),
            tools=data.get("tools", []) if isinstance(data.get("tools"), list) else [],
            raw=data,
        )

    @classmethod
    def from_toml(cls, text: str) -> "AgentManifest":
        if tomllib is None:  # pragma: no cover
            raise ManifestError("tomllib unavailable (Python < 3.11)")
        try:
            data = tomllib.loads(text)
        except Exception as exc:  # noqa: BLE001
            raise ManifestError(f"invalid agent.toml: {exc}") from exc
        return cls.from_dict(data)

    @property
    def max_cost_usd(self) -> Optional[float]:
        v = self.limits.get("max_cost_usd")
        return float(v) if v is not None else None

    @property
    def timeout_sec(self) -> Optional[int]:
        v = self.limits.get("timeout_sec")
        return int(v) if v is not None else None

    @property
    def max_tool_calls(self) -> Optional[int]:
        v = self.limits.get("max_tool_calls")
        return int(v) if v is not None else None


# ── live trace ──────────────────────────────────────────────────────────────
@dataclass
class TraceEvent:
    run_id: str
    kind: str  # prompt | completion | tool_call | tool_result | token | status | error
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_payload(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "kind": self.kind, "data": self.data, "ts": self.ts}


@dataclass
class RunContext:
    run_id: str
    agent_id: str
    manifest: AgentManifest
    prompt_vars: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    emit: Optional[Callable[[TraceEvent], Awaitable[None]]] = None

    async def trace(self, kind: str, **data: Any) -> None:
        if self.emit is not None:
            await self.emit(TraceEvent(run_id=self.run_id, kind=kind, data=data))


@dataclass
class RunResult:
    status: str  # success | failed | cancelled | paused
    usage: Usage = field(default_factory=Usage)
    output: str = ""
    error: Optional[str] = None


@runtime_checkable
class Adapter(Protocol):
    async def run(self, ctx: RunContext) -> RunResult: ...


# ── adapter registry seam ───────────────────────────────────────────────────
AdapterFactory = Callable[[], Adapter]
_adapters: dict[str, AdapterFactory] = {}


def register_adapter(agent_type: str, factory: AdapterFactory) -> None:
    _adapters[agent_type] = factory


def get_adapter(agent_type: str) -> Adapter:
    if agent_type not in _adapters:
        raise KeyError(f"no adapter registered for agent type {agent_type!r}")
    return _adapters[agent_type]()


def has_adapter(agent_type: str) -> bool:
    return agent_type in _adapters


# ── price table hook (kept fresh by the cloud; default empty) ───────────────
_price_table: dict[str, Any] = {}


def set_price_table(table: dict[str, Any]) -> None:
    global _price_table
    _price_table = table


def get_price_table() -> dict[str, Any]:
    return _price_table
