"""Database access via the Supabase async client.

Two access modes:
  * `service_db()` — uses the service_role key, BYPASSES RLS. Used by the backend
    for server-side work (WebSocket hub writes, async workers, daemon-originated rows)
    and by REST handlers that have already resolved+checked the caller's org via
    the auth dependency. Always scope queries by org_id yourself in this mode.
  * `user_db(access_token)` — uses the anon key + the caller's Supabase JWT, so
    Postgres RLS is enforced. Use when you want the DB itself to gate access.

The Supabase client is created lazily and cached per access mode/token.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from supabase import AsyncClient, acreate_client
from supabase.lib.client_options import AsyncClientOptions

from .config import get_settings

_service_client: Optional[AsyncClient] = None


async def service_db() -> AsyncClient:
    """Cached service-role client (bypasses RLS)."""
    global _service_client
    if _service_client is None:
        s = get_settings()
        key = s.supabase_service_role_key or s.supabase_anon_key
        _service_client = await acreate_client(
            s.supabase_url,
            key,
            options=AsyncClientOptions(auto_refresh_token=False, persist_session=False),
        )
    return _service_client


async def user_db(access_token: str) -> AsyncClient:
    """RLS-scoped client carrying the caller's Supabase JWT."""
    s = get_settings()
    client = await acreate_client(
        s.supabase_url,
        s.supabase_anon_key,
        options=AsyncClientOptions(
            auto_refresh_token=False,
            persist_session=False,
            headers={"Authorization": f"Bearer {access_token}"},
        ),
    )
    return client


async def get_db() -> AsyncClient:
    """FastAPI dependency: service-role client. Org scoping is enforced by the
    auth dependency + handler logic (see deps.get_principal)."""
    return await service_db()


def reset_db_cache() -> None:
    """Test helper — drop the cached service client (e.g. after settings change)."""
    global _service_client
    _service_client = None


@lru_cache
def _warn_no_service_key() -> bool:  # pragma: no cover - advisory only
    s = get_settings()
    return not s.supabase_service_role_key
