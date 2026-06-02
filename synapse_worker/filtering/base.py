"""Filtering middleware base (§4.5).

Two layers sit on both edges of the Agent Runtime: Layer A redacts PII/secrets leaving
the box; Layer B screens untrusted inbound content and model output for injection /
jailbreak attempts. Both implement :class:`Filter` and register into the shared
:class:`FilterChain`.

The foundation ships a **pass-through** chain so the runtime works before the redaction
and injection units land — but the chain is ordered so that, once present, redaction
runs before anything is persisted or uploaded.

> Hard guarantee (spec): all filtering runs on-device, before any byte leaves the
> machine. Callers MUST route outbound text through ``get_filter_chain().screen_outbound``
> before upload/persist, and inbound untrusted content through ``screen_inbound``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class Direction(str, Enum):
    INBOUND = "inbound"    # untrusted content -> model
    OUTBOUND = "outbound"  # model output / logs -> action / upload


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Finding:
    """A single detection. Never carries the raw matched secret/content."""

    category: str               # e.g. API_KEY, EMAIL, INJECTION, EXFILTRATION
    severity: Severity = Severity.MEDIUM
    action: str = "warn"        # block | mask | hash | require-approval | warn
    excerpt: str = ""           # already-redacted / signal-only excerpt
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RedactionManifest:
    """Counts/types only — the dashboard shows '12 secrets masked' with no values."""

    counts: dict[str, int] = field(default_factory=dict)

    def bump(self, category: str, n: int = 1) -> None:
        self.counts[category] = self.counts.get(category, 0) + n

    def merge(self, other: "RedactionManifest") -> None:
        for k, v in other.counts.items():
            self.bump(k, v)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


@dataclass
class FilterResult:
    text: str
    findings: list[Finding] = field(default_factory=list)
    manifest: RedactionManifest = field(default_factory=RedactionManifest)
    blocked: bool = False       # the whole field was dropped (block mode / high injection)

    def merge(self, other: "FilterResult") -> "FilterResult":
        self.text = other.text
        self.findings.extend(other.findings)
        self.manifest.merge(other.manifest)
        self.blocked = self.blocked or other.blocked
        return self


@runtime_checkable
class Filter(Protocol):
    name: str

    def screen(
        self, text: str, *, direction: Direction, context: Optional[dict[str, Any]] = None
    ) -> FilterResult: ...


class FilterChain:
    """Ordered filters applied edge-to-edge. Empty chain = pass-through."""

    def __init__(self) -> None:
        self._filters: list[Filter] = []

    def register(self, flt: Filter) -> None:
        self._filters.append(flt)

    def clear(self) -> None:
        self._filters.clear()

    @property
    def filters(self) -> list[Filter]:
        return list(self._filters)

    def _run(
        self, text: str, direction: Direction, context: Optional[dict[str, Any]]
    ) -> FilterResult:
        result = FilterResult(text=text)
        for flt in self._filters:
            step = flt.screen(result.text, direction=direction, context=context)
            result.merge(step)
            if step.blocked:
                break
        return result

    def screen_inbound(
        self, text: str, *, context: Optional[dict[str, Any]] = None
    ) -> FilterResult:
        return self._run(text, Direction.INBOUND, context)

    def screen_outbound(
        self, text: str, *, context: Optional[dict[str, Any]] = None
    ) -> FilterResult:
        return self._run(text, Direction.OUTBOUND, context)


_chain: FilterChain = FilterChain()


def get_filter_chain() -> FilterChain:
    return _chain


def reset_filter_chain() -> None:  # test helper
    global _chain
    _chain = FilterChain()
