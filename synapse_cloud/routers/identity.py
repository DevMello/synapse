"""Identity & tenancy REST (orgs / users / memberships / roles).

Exposes the current principal, the active org, and CRUD over memberships,
including Supabase Auth user sync (link-or-create) and RBAC role assignment.

All queries use the service-role client (BYPASSES RLS), so every query is
explicitly scoped to `principal.org_id`.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..audit import get_audit
from ..db import service_db
from ..deps import Principal, get_principal, require_admin
from ..rbac import Role

router = APIRouter(tags=["identity"])

_VALID_ROLES = {r.value for r in Role}


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class MeResponse(BaseModel):
    user_id: str
    org_id: str
    role: str
    email: Optional[str] = None
    display_name: Optional[str] = None


class OrgResponse(BaseModel):
    id: str
    name: str
    settings: dict[str, Any] = {}
    created_at: Optional[str] = None


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class MemberResponse(BaseModel):
    user_id: str
    org_id: str
    role: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    created_at: Optional[str] = None


class MemberCreate(BaseModel):
    email: str
    role: str = Role.viewer.value


class MemberUpdate(BaseModel):
    role: str


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _check_role(role: str) -> None:
    if role not in _VALID_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"invalid role '{role}'; must be one of {sorted(_VALID_ROLES)}",
        )


async def _user_lookup(db, user_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Map user_id -> {email, display_name} for the given ids."""
    if not user_ids:
        return {}
    rows = (
        await db.table("users")
        .select("id, email, display_name")
        .in_("id", user_ids)
        .execute()
    ).data or []
    return {r["id"]: r for r in rows}


async def _count_owners(db, org_id: str) -> int:
    rows = (
        await db.table("memberships")
        .select("user_id")
        .eq("org_id", org_id)
        .eq("role", Role.owner.value)
        .execute()
    ).data or []
    return len(rows)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/me", response_model=MeResponse)
async def get_me(principal: Principal = Depends(get_principal)) -> MeResponse:
    db = await service_db()
    rows = (
        await db.table("users")
        .select("email, display_name")
        .eq("id", principal.user_id)
        .execute()
    ).data or []
    profile = rows[0] if rows else {}
    return MeResponse(
        user_id=principal.user_id,
        org_id=principal.org_id,
        role=principal.role,
        email=profile.get("email"),
        display_name=profile.get("display_name"),
    )


@router.get("/orgs/current", response_model=OrgResponse)
async def get_current_org(principal: Principal = Depends(get_principal)) -> OrgResponse:
    db = await service_db()
    rows = (
        await db.table("organizations")
        .select("id, name, settings, created_at")
        .eq("id", principal.org_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "org not found")
    org = rows[0]
    return OrgResponse(
        id=org["id"],
        name=org["name"],
        settings=org.get("settings") or {},
        created_at=org.get("created_at"),
    )


@router.patch("/orgs/current", response_model=OrgResponse)
async def update_current_org(
    body: OrgUpdate, principal: Principal = Depends(require_admin)
) -> OrgResponse:
    db = await service_db()
    update: dict[str, Any] = {}
    if body.name is not None:
        update["name"] = body.name
    if body.settings is not None:
        update["settings"] = body.settings
    if not update:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nothing to update")

    rows = (
        await db.table("organizations")
        .update(update)
        .eq("id", principal.org_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "org not found")
    org = rows[0]
    await get_audit().write(
        principal.org_id,
        "org.update",
        actor=principal.user_id,
        resource_type="organization",
        resource_id=principal.org_id,
        detail={"fields": list(update.keys())},
    )
    return OrgResponse(
        id=org["id"],
        name=org["name"],
        settings=org.get("settings") or {},
        created_at=org.get("created_at"),
    )


@router.get("/members", response_model=list[MemberResponse])
async def list_members(
    principal: Principal = Depends(get_principal),
) -> list[MemberResponse]:
    db = await service_db()
    memberships = (
        await db.table("memberships")
        .select("user_id, org_id, role, created_at")
        .eq("org_id", principal.org_id)
        .execute()
    ).data or []
    profiles = await _user_lookup(db, [m["user_id"] for m in memberships])
    result: list[MemberResponse] = []
    for m in memberships:
        p = profiles.get(m["user_id"], {})
        result.append(
            MemberResponse(
                user_id=m["user_id"],
                org_id=m["org_id"],
                role=m["role"],
                email=p.get("email"),
                display_name=p.get("display_name"),
                created_at=m.get("created_at"),
            )
        )
    return result


async def _find_or_create_auth_user(db, email: str) -> str:
    """Return the auth user id for `email`, creating the auth user if missing."""
    # Look for an existing public.users row first (cheap, org-agnostic).
    existing = (
        await db.table("users").select("id").eq("email", email).execute()
    ).data or []
    if existing:
        return existing[0]["id"]

    # Try to create a Supabase Auth user. If one already exists with this email,
    # the admin API errors; fall back to listing users to find the id.
    try:
        created = await db.auth.admin.create_user(
            {"email": email, "email_confirm": True}
        )
        return created.user.id
    except Exception:  # noqa: BLE001 - email may already be registered
        page = await db.auth.admin.list_users()
        users = getattr(page, "users", page)
        for u in users:
            if getattr(u, "email", None) == email:
                return u.id
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "could not create or locate auth user for email",
        )


@router.post("/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    body: MemberCreate, principal: Principal = Depends(require_admin)
) -> MemberResponse:
    _check_role(body.role)
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email")
    db = await service_db()

    user_id = await _find_or_create_auth_user(db, email)

    # Reject duplicate membership in this org.
    dup = (
        await db.table("memberships")
        .select("user_id")
        .eq("org_id", principal.org_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, "user already a member of this org")

    # Sync the public.users profile row.
    profile_rows = (
        await db.table("users")
        .upsert({"id": user_id, "email": email})
        .execute()
    ).data or []
    profile = profile_rows[0] if profile_rows else {"email": email}

    membership = (
        await db.table("memberships")
        .insert({"org_id": principal.org_id, "user_id": user_id, "role": body.role})
        .execute()
    ).data[0]

    await get_audit().write(
        principal.org_id,
        "member.add",
        actor=principal.user_id,
        resource_type="membership",
        resource_id=user_id,
        detail={"email": email, "role": body.role},
    )
    return MemberResponse(
        user_id=user_id,
        org_id=principal.org_id,
        role=membership["role"],
        email=profile.get("email", email),
        display_name=profile.get("display_name"),
        created_at=membership.get("created_at"),
    )


@router.patch("/members/{user_id}", response_model=MemberResponse)
async def update_member(
    user_id: str, body: MemberUpdate, principal: Principal = Depends(require_admin)
) -> MemberResponse:
    _check_role(body.role)
    db = await service_db()

    rows = (
        await db.table("memberships")
        .select("user_id, role")
        .eq("org_id", principal.org_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "membership not found")
    current = rows[0]

    # Guard: don't demote the last owner.
    if current["role"] == Role.owner.value and body.role != Role.owner.value:
        if await _count_owners(db, principal.org_id) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "cannot demote the last owner"
            )

    updated = (
        await db.table("memberships")
        .update({"role": body.role})
        .eq("org_id", principal.org_id)
        .eq("user_id", user_id)
        .execute()
    ).data[0]

    profiles = await _user_lookup(db, [user_id])
    p = profiles.get(user_id, {})
    await get_audit().write(
        principal.org_id,
        "member.role_change",
        actor=principal.user_id,
        resource_type="membership",
        resource_id=user_id,
        detail={"from": current["role"], "to": body.role},
    )
    return MemberResponse(
        user_id=user_id,
        org_id=principal.org_id,
        role=updated["role"],
        email=p.get("email"),
        display_name=p.get("display_name"),
        created_at=updated.get("created_at"),
    )


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: str, principal: Principal = Depends(require_admin)
) -> None:
    db = await service_db()

    rows = (
        await db.table("memberships")
        .select("user_id, role")
        .eq("org_id", principal.org_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "membership not found")
    current = rows[0]

    # Guard: don't remove the last owner.
    if current["role"] == Role.owner.value and await _count_owners(db, principal.org_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot remove the last owner")

    await db.table("memberships").delete().eq("org_id", principal.org_id).eq(
        "user_id", user_id
    ).execute()

    await get_audit().write(
        principal.org_id,
        "member.remove",
        actor=principal.user_id,
        resource_type="membership",
        resource_id=user_id,
        detail={"role": current["role"]},
    )
