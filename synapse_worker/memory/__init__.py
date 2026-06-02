"""Agent memory interface + swappable storage providers (§4.13).

Every agent gets persistent memory out of the box — facts, results, and learned context
that survive across runs (distinct from §4.12 session/checkpoint state). Memory is
**local-first** on the daemon and **synced on demand** so the Web UI can inspect/correct it.

Public surface:
  * :class:`~synapse_worker.memory.api.MemoryAPI` / :func:`get_memory` — the provider-agnostic
    API surfaced to every agent (and, via the built-in ``memory`` MCP server, to CLI agents).
  * :func:`~synapse_worker.memory.providers.get_provider` — the provider factory
    (sqlite default, vector with graceful fallback).
  * :func:`~synapse_worker.memory.api.flush_deltas` — batch the change journal into a
    ``memory.delta`` upstream frame (called by the ``memory_sync`` background service).
"""
from __future__ import annotations

from .api import MemoryAPI, MemoryEntry, flush_deltas, get_memory
from .providers import (
    MemoryProvider,
    SqliteMemoryProvider,
    VectorMemoryProvider,
    get_provider,
)

__all__ = [
    "MemoryAPI",
    "MemoryEntry",
    "get_memory",
    "flush_deltas",
    "MemoryProvider",
    "SqliteMemoryProvider",
    "VectorMemoryProvider",
    "get_provider",
]
