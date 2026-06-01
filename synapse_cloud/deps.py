"""FastAPI auth dependencies.

Browser/user requests carry a Supabase JWT (Authorization: Bearer <jwt>). We
validate it against Supabase Auth, then resolve the caller's org + role from
`memberships`. Multi-org users select an org with the `X-Org-Id` header; if a
user belongs to exactly one org it is used by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from .db import service_db
from .rbac import Role, can_admin, can_write


@dataclass(frozen=True)
class Principal:
    user_id: str
    org_id: str
    role: str
    access_token: str

    @property
    def can_write(self) -> bool:
        return can_write(self.role)

    @property
    def can_admin(self) -> bool:
        return can_admin(self.role)


def _bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return authorization.split(" ", 1)[1].strip()


async def get_principal(
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None),
) -> Principal:
    """Resolve and authenticate the calling user + their active org/role."""
    token = _bearer(authorization)
    db = await service_db()

    try:
        user_resp = await db.auth.get_user(token)
    except Exception as exc:  # noqa: BLE001 - supabase raises various auth errors
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    if not user_resp or not getattr(user_resp, "user", None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    user_id = user_resp.user.id

    q = db.table("memberships").select("org_id, role").eq("user_id", user_id)
    if x_org_id:
        q = q.eq("org_id", x_org_id)
    rows = (await q.execute()).data or []
    if not rows:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no org membership")
    if x_org_id is None and len(rows) > 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "multiple orgs; set X-Org-Id header"
        )
    row = rows[0]
    return Principal(
        user_id=user_id, org_id=row["org_id"], role=row["role"], access_token=token
    )


def require_write(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "operator role required")
    return principal


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.can_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return principal
