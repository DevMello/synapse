"""Shared test fixtures for Synapse Cloud.

Tests run against the REAL Supabase project (Postgres/RLS/Auth) — there are no
DB fakes. The `is_test` flag (SYNAPSE_ENV=test, set below before any
synapse_cloud import) only swaps the *side-effect* seams (Realtime, Storage,
Notifications, Audit) for in-memory fakes; the database is always real.

`make_test_org` mints a fresh org per call: a real Supabase Auth user, an
`organizations` row, a `public.users` row, and a `memberships` row, plus a signed
user JWT. Because every org id is unique and RLS is org-scoped, concurrent worker
test runs against the same project never collide. Use `org.auth_headers()` to call
authenticated endpoints, and `await org.make_daemon()` for a registered daemon +
its access token.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

# Must be set before importing synapse_cloud.config (lru_cached settings).
os.environ.setdefault("SYNAPSE_ENV", "test")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from supabase import acreate_client  # noqa: E402
from supabase.lib.client_options import AsyncClientOptions  # noqa: E402

from synapse_cloud.app import create_app  # noqa: E402
from synapse_cloud.config import get_settings  # noqa: E402
from synapse_cloud.db import reset_db_cache, service_db  # noqa: E402
from synapse_cloud.security import encode_daemon_access_token  # noqa: E402

_PASSWORD = "Test-Passw0rd!"


async def _sign_in_access_token(email: str, password: str) -> str:
    """Sign in on a throwaway anon client to obtain a user access token.

    We must NOT sign in on the shared service-role client and then sign out:
    GoTrue's logout revokes the session server-side, which would invalidate the
    very access token we just handed back to the test. Using a disposable anon
    client keeps the service client's session untouched and the token valid.
    """
    s = get_settings()
    anon = await acreate_client(
        s.supabase_url,
        s.supabase_anon_key,
        options=AsyncClientOptions(auto_refresh_token=False, persist_session=False),
    )
    signin = await anon.auth.sign_in_with_password({"email": email, "password": password})
    return signin.session.access_token


@pytest.fixture(autouse=True)
def _reset_db_cache_each_test():
    """Drop the cached async Supabase client around every test.

    The client is created lazily and cached module-wide; on some event-loop
    policies (e.g. Windows ProactorEventLoop) a client bound to one test's loop
    breaks when reused by the next. Resetting per test rebinds it to the active
    loop.
    """
    reset_db_cache()
    yield
    reset_db_cache()


def _require_real_supabase() -> None:
    s = get_settings()
    if not (s.supabase_url and s.supabase_anon_key and s.supabase_service_role_key):
        pytest.skip(
            "real Supabase creds required (SUPABASE_URL / SUPABASE_ANON_KEY / "
            "SUPABASE_SERVICE_ROLE_KEY in .env)",
            allow_module_level=False,
        )


@dataclass
class TestOrg:
    org_id: str
    user_id: str
    email: str
    access_token: str
    role: str = "owner"
    daemon_ids: list[str] = field(default_factory=list)

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", "X-Org-Id": self.org_id}

    async def make_daemon(self, name: str = "test-daemon") -> tuple[str, str]:
        """Insert a daemon row for this org and mint its access token."""
        db = await service_db()
        row = (
            await db.table("daemons")
            .insert({"org_id": self.org_id, "name": name, "status": "offline"})
            .execute()
        ).data[0]
        daemon_id = row["id"]
        self.daemon_ids.append(daemon_id)
        token = encode_daemon_access_token(daemon_id, self.org_id)
        return daemon_id, token


@pytest_asyncio.fixture
async def make_test_org() -> Callable[..., Awaitable[TestOrg]]:
    """Factory fixture: call it (optionally with role=) to mint isolated orgs.

    Created auth users + org rows are torn down after the test.
    """
    _require_real_supabase()
    db = await service_db()
    created_user_ids: list[str] = []
    created_org_ids: list[str] = []

    async def _make(role: str = "owner", org_name: str | None = None) -> TestOrg:
        suffix = uuid.uuid4().hex[:12]
        email = f"test-{suffix}@synapse.test"
        name = org_name or f"test-org-{suffix}"

        user = await db.auth.admin.create_user(
            {"email": email, "password": _PASSWORD, "email_confirm": True}
        )
        user_id = user.user.id
        created_user_ids.append(user_id)

        org = (
            await db.table("organizations").insert({"name": name}).execute()
        ).data[0]
        org_id = org["id"]
        created_org_ids.append(org_id)

        await db.table("users").upsert(
            {"id": user_id, "email": email, "display_name": name}
        ).execute()
        await db.table("memberships").insert(
            {"org_id": org_id, "user_id": user_id, "role": role}
        ).execute()

        access_token = await _sign_in_access_token(email, _PASSWORD)

        return TestOrg(
            org_id=org_id,
            user_id=user_id,
            email=email,
            access_token=access_token,
            role=role,
        )

    yield _make

    for org_id in created_org_ids:
        try:
            await db.table("organizations").delete().eq("id", org_id).execute()
        except Exception:  # noqa: BLE001 - best-effort teardown
            pass
    for user_id in created_user_ids:
        try:
            await db.auth.admin.delete_user(user_id)
        except Exception:  # noqa: BLE001 - best-effort teardown
            pass


@pytest_asyncio.fixture
async def test_org(make_test_org) -> TestOrg:
    """Convenience: a single owner-role org for the common case."""
    return await make_test_org()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """In-process httpx client against the ASGI app (no network, no lifespan)."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
