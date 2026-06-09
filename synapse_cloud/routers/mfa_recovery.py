"""MFA recovery codes and org security policy (Unit 2 — backend MFA recovery router).

REST endpoints:
  * ``POST /mfa/recovery-codes``              — generate a fresh set of recovery codes
    for the authenticated user and persist their hashes.
  * ``POST /mfa/recovery-codes/redeem``       — redeem a single recovery code (atomic
    UPDATE guards against TOCTOU races).
  * ``DELETE /mfa/users/{user_id}/factors``   — admin: delete all Supabase Auth MFA
    factors for a user and clear their mfa_enabled flag.
  * ``GET  /mfa/policy``                      — fetch the org's MFA security policy.
  * ``PATCH /mfa/policy``                     — upsert the org's MFA security policy.

Every query is org-scoped via the service-role client (RLS bypassed); ownership is
verified explicitly via the ``Principal`` dependency.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..db import service_db
from ..deps import Principal, get_principal, require_admin, require_write

router = APIRouter(prefix="/mfa", tags=["mfa-recovery"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _hash_code(code: str) -> str:
    """SHA-256 hex-digest of a recovery code for safe storage."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_recovery_codes(count: int = 8) -> list[str]:
    """Generate `count` recovery codes in ``XXXXX-XXXXX`` format.

    Bug 3 fix: use the full ``secrets.token_hex(5)`` (10 hex chars = 40 bits per
    half) rather than slicing to 5 chars (which would only give 20 bits per half).
    """
    codes = []
    for _ in range(count):
        left = secrets.token_hex(5)   # 10 hex chars, 40 bits — NOT [:5]
        right = secrets.token_hex(5)  # 10 hex chars, 40 bits — NOT [:5]
        codes.append(f"{left}-{right}")
    return codes


# ── request / response models ─────────────────────────────────────────────────

class GenerateCodesResponse(BaseModel):
    codes: list[str]
    count: int


class RedeemRequest(BaseModel):
    code: str = Field(min_length=1, description="Plain-text recovery code to redeem")


class RedeemResponse(BaseModel):
    user_id: str
    redeemed: bool


class DeleteFactorsResponse(BaseModel):
    user_id: str
    factors_removed: int


class PolicyRequest(BaseModel):
    require_mfa: Optional[bool] = None
    allowed_factors: Optional[list[str]] = None
    grace_period_hours: Optional[int] = Field(default=None, ge=0)


class PolicyResponse(BaseModel):
    org_id: str
    require_mfa: bool
    allowed_factors: list[str]
    grace_period_hours: int


# ── POST /mfa/recovery-codes ──────────────────────────────────────────────────

@router.post("/recovery-codes", response_model=GenerateCodesResponse)
async def generate_recovery_codes(
    principal: Principal = Depends(get_principal),
) -> GenerateCodesResponse:
    """Generate and store a fresh set of MFA recovery codes for the caller.

    Existing unused codes for this user are deleted before the new ones are
    inserted, so only the most recently generated batch is ever valid.
    """
    db = await service_db()
    user_id = principal.user_id
    org_id = principal.org_id

    # Invalidate any pre-existing codes for this user in this org.
    await (
        db.table("recovery_codes")
        .delete()
        .eq("user_id", user_id)
        .eq("org_id", org_id)
        .execute()
    )

    codes = _generate_recovery_codes()
    rows = [
        {
            "user_id": user_id,
            "org_id": org_id,
            "code_hash": _hash_code(c),
        }
        for c in codes
    ]
    await db.table("recovery_codes").insert(rows).execute()

    return GenerateCodesResponse(codes=codes, count=len(codes))


# ── POST /mfa/recovery-codes/redeem ──────────────────────────────────────────

@router.post("/recovery-codes/redeem", response_model=RedeemResponse)
async def redeem_recovery_code(
    body: RedeemRequest,
    principal: Principal = Depends(get_principal),
) -> RedeemResponse:
    """Redeem a single recovery code for the authenticated user.

    Bug 1 fix (TOCTOU): the check-and-mark is done atomically with a single
    UPDATE … WHERE used_at IS NULL.  If 0 rows are updated the code is either
    invalid or was already redeemed (race lost) — return 401 in both cases.
    There is intentionally no prior SELECT; the UPDATE response confirms existence.
    """
    db = await service_db()
    user_id = principal.user_id
    org_id = principal.org_id
    code_hash = _hash_code(body.code)

    # Atomic: mark used only if the row exists AND has not been used yet.
    result = await (
        db.table("recovery_codes")
        .update({"used_at": "now()"})
        .eq("user_id", user_id)
        .eq("org_id", org_id)
        .eq("code_hash", code_hash)
        .is_("used_at", "null")
        .execute()
    )
    if not result.data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid recovery code")

    return RedeemResponse(user_id=user_id, redeemed=True)


# ── DELETE /mfa/users/{user_id}/factors ──────────────────────────────────────

async def _delete_all_factors(db: Any, user_id: str) -> int:
    """Remove all Supabase Auth MFA factors for *user_id*.

    Bug 2 fix: errors are no longer silently swallowed.  Any exception from the
    Auth API propagates as an HTTP 502 so callers know the operation failed.

    Returns the number of factors that were removed.
    """
    try:
        factors_resp = await db.auth.admin.list_factors(user_id)
        factors: list[Any] = getattr(factors_resp, "factors", None) or []
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Failed to list MFA factors",
        ) from exc

    removed = 0
    for factor in factors:
        factor_id = factor.id if hasattr(factor, "id") else factor.get("id")
        if not factor_id:
            continue
        try:
            await db.auth.admin.delete_factor(user_id, factor_id)
            removed += 1
        except Exception as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "Failed to remove MFA factors",
            ) from exc

    return removed


@router.delete("/users/{user_id}/factors", response_model=DeleteFactorsResponse)
async def delete_user_factors(
    user_id: str,
    principal: Principal = Depends(require_admin),
) -> DeleteFactorsResponse:
    """Admin: delete all MFA factors for a user and clear their mfa_enabled flag.

    Org-scoped: verifies the target user belongs to the caller's org before
    touching anything.
    """
    db = await service_db()

    # Verify the target user is a member of the caller's org.
    membership = (
        await db.table("memberships")
        .select("user_id")
        .eq("user_id", user_id)
        .eq("org_id", principal.org_id)
        .limit(1)
        .execute()
    ).data or []
    if not membership:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found in org")

    removed = await _delete_all_factors(db, user_id)

    # Clear mfa_enabled flag if the profile table tracks it.
    await (
        db.table("profiles")
        .update({"mfa_enabled": False})
        .eq("id", user_id)
        .execute()
    )

    return DeleteFactorsResponse(user_id=user_id, factors_removed=removed)


# ── GET /mfa/policy ───────────────────────────────────────────────────────────

_POLICY_DEFAULTS: dict[str, Any] = {
    "require_mfa": False,
    "allowed_factors": ["totp"],
    "grace_period_hours": 48,
}


async def get_mfa_policy(principal: Principal) -> PolicyResponse:
    """Fetch (or synthesise) the org's MFA policy row."""
    db = await service_db()
    rows = (
        await db.table("mfa_policies")
        .select("*")
        .eq("org_id", principal.org_id)
        .limit(1)
        .execute()
    ).data or []

    if rows:
        row = rows[0]
    else:
        row = {"org_id": principal.org_id, **_POLICY_DEFAULTS}

    return PolicyResponse(
        org_id=row["org_id"],
        require_mfa=row.get("require_mfa", _POLICY_DEFAULTS["require_mfa"]),
        allowed_factors=row.get("allowed_factors", _POLICY_DEFAULTS["allowed_factors"]),
        grace_period_hours=row.get("grace_period_hours", _POLICY_DEFAULTS["grace_period_hours"]),
    )


@router.get("/policy", response_model=PolicyResponse)
async def read_mfa_policy(
    principal: Principal = Depends(get_principal),
) -> PolicyResponse:
    """Return the org's current MFA security policy."""
    return await get_mfa_policy(principal)


# ── PATCH /mfa/policy ─────────────────────────────────────────────────────────

@router.patch("/policy", response_model=PolicyResponse)
async def update_mfa_policy(
    body: PolicyRequest,
    principal: Principal = Depends(require_admin),
) -> PolicyResponse:
    """Upsert the org's MFA security policy.

    Bug 4 fix: when the upsert returns empty ``.data`` (e.g. the DB returns no
    rows on a no-op upsert) we build the ``PolicyResponse`` directly from the
    request body merged with current defaults rather than issuing a redundant
    second SELECT round-trip.
    """
    db = await service_db()

    # Merge request body with defaults; only include fields explicitly provided.
    patch: dict[str, Any] = {"org_id": principal.org_id}
    if body.require_mfa is not None:
        patch["require_mfa"] = body.require_mfa
    if body.allowed_factors is not None:
        patch["allowed_factors"] = body.allowed_factors
    if body.grace_period_hours is not None:
        patch["grace_period_hours"] = body.grace_period_hours

    result = await (
        db.table("mfa_policies")
        .upsert(patch, on_conflict="org_id")
        .execute()
    )

    if result.data:
        row = result.data[0]
        return PolicyResponse(
            org_id=row["org_id"],
            require_mfa=row.get("require_mfa", _POLICY_DEFAULTS["require_mfa"]),
            allowed_factors=row.get("allowed_factors", _POLICY_DEFAULTS["allowed_factors"]),
            grace_period_hours=row.get("grace_period_hours", _POLICY_DEFAULTS["grace_period_hours"]),
        )

    # Bug 4 fix: build response from the patch merged with defaults — no second SELECT.
    return PolicyResponse(
        org_id=principal.org_id,
        require_mfa=patch.get("require_mfa", _POLICY_DEFAULTS["require_mfa"]),
        allowed_factors=patch.get("allowed_factors", _POLICY_DEFAULTS["allowed_factors"]),
        grace_period_hours=patch.get("grace_period_hours", _POLICY_DEFAULTS["grace_period_hours"]),
    )
