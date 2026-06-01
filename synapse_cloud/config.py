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

    # gRPC hub
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    hub_node_id: str = "local"

    # Async workers
    redis_url: str = "redis://localhost:6379"

    # Runtime
    synapse_env: str = "dev"      # "test" => use in-memory fakes for side-effects
    web_ui_dist: str = ""         # path to built Web UI bundle (static mount)

    @property
    def is_test(self) -> bool:
        return self.synapse_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
