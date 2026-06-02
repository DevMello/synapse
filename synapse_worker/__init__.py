"""Synapse TUI Worker Daemon (`synapse-worker`).

The on-machine execution substrate of Synapse: connects outbound-only to the Cloud
Backend over two JSON WebSocket channels, executes agents (API + CLI) in isolated
processes, redacts secrets on-device, enforces rulesets, pauses for HITL, checkpoints
runs, and ships a Textual TUI.

This package is split into a small **foundation** (config, paths, the wire envelope,
the local SQLite store, the command-dispatch registry, the outbound uplink seam, and
base protocols for runtime/filtering/ruleset/capabilities/plugins) plus feature units
that register into those seams without editing shared files. See docs/tui-daemon.md.
"""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
