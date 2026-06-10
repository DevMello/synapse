"""Application settings (pydantic-settings, read from environment / .env)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase
    supabase_url: str = "http://localhost:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Daemon auth (custom OAuth 2.0 device-code; HS256 JWT)
    daemon_jwt_secret: str = "dev-only-change-me"
    daemon_access_token_ttl_seconds: int = 900
    device_code_ttl_seconds: int = 600

    # WebSocket daemon hub
    hub_node_id: str = "local"

    # Agent-orchestration grant signing (ed25519). grant_signing_key is a base64
    # 32-byte seed; empty => a deterministic dev/test key (NOT for production).
    grant_signing_key: str = ""
    grant_key_id: str = "k1"

    # Runtime
    synapse_env: str = "dev"      # "test" => use in-memory fakes for side-effects
    web_ui_dist: str = ""         # path to built Web UI bundle (static mount)

    # CORS — comma-separated list of allowed origins for browser API calls.
    # In production the SPA is served from the same origin so this is unused.
    # In development set SYNAPSE_CORS_ORIGINS=http://localhost:5173 (Vite).
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_test(self) -> bool:
        return self.synapse_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
