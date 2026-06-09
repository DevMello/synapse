"""Auth: command public-key registration and lookup.

The browser generates an Ed25519 keypair; the public key is registered here.
The daemon calls the lookup endpoint to fetch a user's verify key when it needs
to validate command-auth tokens.
"""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import service_db
from ..deps import Principal, get_principal

router = APIRouter(prefix="/auth", tags=["auth"])


class CommandKeyRegister(BaseModel):
    public_key: str


@router.post("/command-key")
async def register_command_key(
    body: CommandKeyRegister,
    principal: Principal = Depends(get_principal),
) -> dict:
    # Validate: must be base64-decodeable and exactly 32 bytes (Ed25519 public key).
    try:
        raw = base64.b64decode(body.public_key)
        if len(raw) != 32:
            raise ValueError(f"expected 32 bytes, got {len(raw)}")
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid public_key: {exc}") from exc

    db = await service_db()
    await (
        db.table("users")
        .update({"command_public_key": body.public_key})
        .eq("id", principal.user_id)
        .execute()
    )
    return {"ok": True}


@router.get("/command-key/{user_id}")
async def get_command_key(
    user_id: str,
    principal: Principal = Depends(get_principal),
) -> dict:
    db = await service_db()

    # Verify user_id is a member of the caller's org.
    membership_rows = (
        await db.table("memberships")
        .select("user_id")
        .eq("org_id", principal.org_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    if not membership_rows:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user not in caller's org")

    rows = (
        await db.table("users")
        .select("command_public_key")
        .eq("id", user_id)
        .execute()
    ).data or []
    public_key: str | None = rows[0].get("command_public_key") if rows else None
    return {"user_id": user_id, "public_key": public_key}
