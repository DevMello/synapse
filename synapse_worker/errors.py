"""Shared exception types for the worker daemon."""
from __future__ import annotations


class WorkerError(Exception):
    """Base class for all daemon errors."""


class ConfigError(WorkerError):
    """Invalid or missing configuration."""


class AuthError(WorkerError):
    """Device-code / token failures (login, refresh, revoke)."""


class ConnectionError_(WorkerError):
    """WebSocket transport / reconnect failures."""


class ManifestError(WorkerError):
    """A malformed agent.toml / plugin.toml manifest."""


class RuntimeRunError(WorkerError):
    """An agent run failed to start or execute."""


class RulesetViolation(WorkerError):
    """A run attempted an action a ruleset blocks."""


class HitlDenied(WorkerError):
    """A human-in-the-loop gate was denied (or timed out -> default deny)."""


class CapabilityError(WorkerError):
    """Plugin/capability provisioning or attach failures."""
