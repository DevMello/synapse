"""Liveness/readiness endpoints (foundation)."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "env": s.synapse_env,
        "supabase_configured": bool(s.supabase_url and s.supabase_service_role_key),
    }
