"""Daemon auth — OAuth 2.0 Device Authorization Grant (RFC 8628).

Daemons are not Supabase Auth users; they get their own scoped, revocable HS256
JWT access token + a rotating opaque refresh token, minted by this flow.

Flow (cloud-backend.md §5):
  1. `POST /auth/device/code`  — unauthenticated; daemon sends device metadata,
     gets back a device_code (shown once) + a human user_code (ABCD-1234).
  2. `POST /auth/device/approve` — authenticated Web UI user enters the user_code,
     reviews the requesting device, and binds it to their org (provisions a daemon).
  3. `POST /auth/device/token` — polled by the daemon; once approved, mints tokens.
  4. `POST /auth/token` — refresh-token rotation.
  5. `POST /daemons/{id}/revoke` — admin revokes a daemon (kills its socket).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..audit import get_audit
from ..command_bus import get_command_bus
from ..config import get_settings
from ..db import service_db
from ..deps import Principal, require_admin, require_write
from ..security import hash_token, new_opaque_token, new_user_code
from ..services.tokens import is_revoked, mint_token_pair, refresh_token_matches

router = APIRouter(tags=["auth-device"])

_DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_REFRESH_GRANT = "refresh_token"
_VERIFICATION_PATH = "/activate"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _verification_uri() -> str:
    """Where the user enters the user_code (Web UI is co-located on this host)."""
    return _VERIFICATION_PATH


# ── request/response models ───────────────────────────────────────────────────
class DeviceCodeRequest(BaseModel):
    hostname: str | None = None
    os_version: str | None = None
    daemon_version: str | None = None


class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    interval: int
    expires_in: int


class ApproveRequest(BaseModel):
    user_code: str = Field(min_length=1)


class ApproveResponse(BaseModel):
    daemon_id: str
    status: str


class DeviceTokenRequest(BaseModel):
    grant_type: str
    device_code: str


class RefreshRequest(BaseModel):
    grant_type: str
    refresh_token: str


# ── POST /auth/device/code (unauthenticated) ──────────────────────────────────
@router.post("/auth/device/code", response_model=DeviceCodeResponse)
async def device_code(body: DeviceCodeRequest, request: Request) -> DeviceCodeResponse:
    s = get_settings()
    db = await service_db()

    device_code_plain = new_opaque_token()
    user_code = new_user_code()
    interval = 5
    expires_at = _now() + timedelta(seconds=s.device_code_ttl_seconds)
    request_ip = request.client.host if request.client else None

    await db.table("device_authorizations").insert(
        {
            "device_code_hash": hash_token(device_code_plain),
            "user_code": user_code,
            "status": "pending",
            "hostname": body.hostname,
            "os_version": body.os_version,
            "daemon_version": body.daemon_version,
            "request_ip": request_ip,
            "interval_seconds": interval,
            "expires_at": expires_at.isoformat(),
        }
    ).execute()

    verification_uri = _verification_uri()
    return DeviceCodeResponse(
        device_code=device_code_plain,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=f"{verification_uri}?user_code={user_code}",
        interval=interval,
        expires_in=s.device_code_ttl_seconds,
    )


# ── POST /auth/device/approve (authenticated Web UI) ──────────────────────────
@router.post("/auth/device/approve", response_model=ApproveResponse)
async def device_approve(
    body: ApproveRequest,
    principal: Principal = Depends(require_write),
) -> ApproveResponse:
    db = await service_db()

    rows = (
        await db.table("device_authorizations")
        .select("*")
        .eq("user_code", body.user_code)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown user_code")
    auth = rows[0]

    if auth["status"] != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "authorization not pending")
    if datetime.fromisoformat(auth["expires_at"]) <= _now():
        await db.table("device_authorizations").update({"status": "expired"}).eq(
            "id", auth["id"]
        ).execute()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "authorization expired")

    # Provision the daemon row, bound to the approving user's org.
    daemon = (
        await db.table("daemons")
        .insert(
            {
                "org_id": principal.org_id,
                "name": auth.get("hostname") or "daemon",
                "status": "offline",
                "hostname": auth.get("hostname"),
                "os_version": auth.get("os_version"),
                "version": auth.get("daemon_version"),
            }
        )
        .execute()
    ).data[0]
    daemon_id = daemon["id"]

    await db.table("device_authorizations").update(
        {
            "status": "authorized",
            "org_id": principal.org_id,
            "user_id": principal.user_id,
            "daemon_id": daemon_id,
        }
    ).eq("id", auth["id"]).execute()

    await get_audit().write(
        principal.org_id,
        "daemon.device.approve",
        actor=principal.user_id,
        resource_type="daemon",
        resource_id=daemon_id,
        detail={
            "hostname": auth.get("hostname"),
            "os_version": auth.get("os_version"),
            "daemon_version": auth.get("daemon_version"),
        },
    )

    return ApproveResponse(daemon_id=daemon_id, status="authorized")


# ── POST /auth/device/token (polling, unauthenticated) ────────────────────────
@router.post("/auth/device/token")
async def device_token(body: DeviceTokenRequest) -> dict:
    if body.grant_type != _DEVICE_CODE_GRANT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "unsupported_grant_type"}
        )

    db = await service_db()
    rows = (
        await db.table("device_authorizations")
        .select("*")
        .eq("device_code_hash", hash_token(body.device_code))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_grant"}
        )
    auth = rows[0]

    if datetime.fromisoformat(auth["expires_at"]) <= _now():
        if auth["status"] not in ("authorized",):
            await db.table("device_authorizations").update({"status": "expired"}).eq(
                "id", auth["id"]
            ).execute()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "expired_token"}
        )

    if auth["status"] == "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "authorization_pending"}
        )
    if auth["status"] == "denied":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "access_denied"}
        )
    if auth["status"] != "authorized":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "expired_token"}
        )

    daemon_id = auth["daemon_id"]
    org_id = auth["org_id"]
    if not daemon_id or not org_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_grant"}
        )

    pair, fields = mint_token_pair(daemon_id, org_id)
    await db.table("daemons").update(fields).eq("id", daemon_id).execute()

    await get_audit().write(
        org_id,
        "daemon.token.issue",
        resource_type="daemon",
        resource_id=daemon_id,
    )

    return pair.to_response()


# ── POST /auth/token (refresh rotation, unauthenticated) ──────────────────────
@router.post("/auth/token")
async def refresh_token(body: RefreshRequest) -> dict:
    if body.grant_type != _REFRESH_GRANT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "unsupported_grant_type"}
        )

    db = await service_db()
    rows = (
        await db.table("daemons")
        .select("*")
        .eq("refresh_token_hash", hash_token(body.refresh_token))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_grant"}
        )
    daemon = rows[0]

    if is_revoked(daemon):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_grant"}
        )
    # Defense in depth: confirm the presented token matches the stored hash.
    if not refresh_token_matches(daemon, body.refresh_token):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_grant"}
        )

    daemon_id = daemon["id"]
    org_id = daemon["org_id"]
    pair, fields = mint_token_pair(daemon_id, org_id)
    await db.table("daemons").update(fields).eq("id", daemon_id).execute()

    await get_audit().write(
        org_id,
        "daemon.token.refresh",
        resource_type="daemon",
        resource_id=daemon_id,
    )

    return pair.to_response()


# ── POST /daemons/{id}/revoke (admin) ─────────────────────────────────────────
@router.post("/daemons/{daemon_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_daemon(
    daemon_id: str,
    principal: Principal = Depends(require_admin),
) -> Response:
    db = await service_db()

    rows = (
        await db.table("daemons")
        .select("id, org_id, revoked_at")
        .eq("id", daemon_id)
        .eq("org_id", principal.org_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "daemon not found")

    await db.table("daemons").update(
        {
            "revoked_at": _now().isoformat(),
            "status": "revoked",
            "refresh_token_hash": None,
        }
    ).eq("id", daemon_id).eq("org_id", principal.org_id).execute()

    await get_command_bus().close_stream(daemon_id, "revoked")

    await get_audit().write(
        principal.org_id,
        "daemon.revoke",
        actor=principal.user_id,
        resource_type="daemon",
        resource_id=daemon_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
