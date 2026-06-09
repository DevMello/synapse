"""Worker settings (pydantic-settings; env + ~/.synapse/config.toml).

Settings come from three layers, lowest precedence first:

  1. field defaults below,
  2. ``~/.synapse/config.toml`` (written by ``synapse init``),
  3. process environment (``SYNAPSE_*``).

``SYNAPSE_WORKER_ENV=test`` flips :attr:`Settings.is_test`, which makes the
side-effect seams (uplink, keystore) default to in-memory fakes so unit tests never
touch a real keychain or socket. ``SYNAPSE_HOME`` overrides the on-disk state dir so
tests can point at a tmp path.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - daemon targets 3.11+, kept importable on 3.10
    tomllib = None  # type: ignore[assignment]


def _default_home() -> Path:
    return Path.home() / ".synapse"


def _config_toml_values() -> dict[str, Any]:
    """Read ~/.synapse/config.toml (or $SYNAPSE_HOME/config.toml) if present."""
    import os

    home = os.environ.get("SYNAPSE_HOME")
    base = Path(home) if home else _default_home()
    path = base / "config.toml"
    if not path.is_file() or tomllib is None:
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:  # noqa: BLE001 - a broken config file shouldn't crash startup
        return {}
    # Accept either a flat table or a [daemon] section.
    flat = dict(data)
    flat.update(data.get("daemon", {}) if isinstance(data.get("daemon"), dict) else {})
    return flat


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SYNAPSE_", env_file=None, extra="ignore"
    )

    # Runtime mode
    worker_env: str = "dev"  # SYNAPSE_WORKER_ENV; "test" => in-memory side-effects
    home: str = ""           # SYNAPSE_HOME; overrides the ~/.synapse state dir

    # Cloud connection
    cloud_base_url: str = "https://api.synapse.dev"   # SYNAPSE_CLOUD_BASE_URL
    ws_control_path: str = "/ws/daemon"
    ws_telemetry_path: str = "/ws/daemon/telemetry"
    verify_tls: bool = True
    client_cert: str = ""    # optional mTLS client cert path

    # Identity / presentation
    daemon_name: str = ""
    daemon_tags: str = ""    # comma-separated
    platform_override: str = ""  # "" => detect

    # Liveness / resources
    heartbeat_interval_seconds: int = 15
    reconnect_max_seconds: int = 60
    max_concurrent_runs: int = 4
    max_memory_mb: int = 0   # 0 => unbounded
    cpu_quota: float = 0.0   # 0 => unbounded

    # Agent orchestration: the cloud's ed25519 public key (base64) used to verify
    # signed grants offline. Empty => orchestration grants cannot be verified.
    grant_public_key: str = ""

    # Command signing: when True, commands that fail dual-signature verification are
    # rejected (not just logged). False = soft-rollout mode.
    require_command_auth: bool = False

    # Guardrail defaults (per-agent config overrides these)
    redaction_enabled: bool = True
    injection_guard_enabled: bool = True
    local_classifier_enabled: bool = False

    workdir: str = ""        # default agent cwd; "" => home/work

    @property
    def is_test(self) -> bool:
        return self.worker_env == "test"

    @property
    def home_dir(self) -> Path:
        return Path(self.home) if self.home else _default_home()

    @property
    def tags(self) -> list[str]:
        return [t.strip() for t in self.daemon_tags.split(",") if t.strip()]

    def ws_url(self, path: str) -> str:
        base = self.cloud_base_url.rstrip("/")
        scheme = "wss" if base.startswith("https") else "ws"
        host = base.split("://", 1)[-1]
        return f"{scheme}://{host}{path}"

    @property
    def control_ws_url(self) -> str:
        return self.ws_url(self.ws_control_path)

    @property
    def telemetry_ws_url(self) -> str:
        return self.ws_url(self.ws_telemetry_path)

    @property
    def token_url(self) -> str:
        return f"{self.cloud_base_url.rstrip('/')}/auth/token"

    @property
    def cloud_api_url(self) -> str:
        """REST API base URL (same host as cloud_base_url, no trailing slash)."""
        return self.cloud_base_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    # config.toml values seed the model; env still wins (BaseSettings reads it last).
    return Settings(**_config_toml_values())


def reset_settings_cache() -> None:
    """Drop the cached settings (used by tests after mutating the environment)."""
    get_settings.cache_clear()
