"""Low-level security primitives shared across units.

Daemon tokens are NOT Supabase Auth tokens — daemons get their own HS256 JWT
(short-lived access token) minted by the device-code flow (unit 1) and validated
by the gRPC interceptor (unit 2) and the revoke endpoint (unit 4). Keeping the
encode/decode/hash helpers here lets those units share them without importing
each other's files.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import jwt

from .config import get_settings

_ALG = "HS256"
_TOKEN_TYPE = "daemon_access"


@dataclass(frozen=True)
class DaemonPrincipal:
    daemon_id: str
    org_id: str


def encode_daemon_access_token(daemon_id: str, org_id: str, *, ttl_seconds: int | None = None) -> str:
    s = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else s.daemon_access_token_ttl_seconds
    now = int(time.time())
    claims = {
        "sub": daemon_id,
        "org_id": org_id,
        "type": _TOKEN_TYPE,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, s.daemon_jwt_secret, algorithm=_ALG)


def decode_daemon_access_token(token: str) -> DaemonPrincipal:
    """Validate a daemon access token. Raises jwt exceptions on failure."""
    s = get_settings()
    claims = jwt.decode(token, s.daemon_jwt_secret, algorithms=[_ALG])
    if claims.get("type") != _TOKEN_TYPE:
        raise jwt.InvalidTokenError("not a daemon access token")
    return DaemonPrincipal(daemon_id=claims["sub"], org_id=claims["org_id"])


# ── opaque tokens (device_code, refresh_token) ────────────────────────────────
def new_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Deterministic SHA-256 hash for storing/looking up opaque tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def new_user_code() -> str:
    """Human-readable 'ABCD-1234' device user_code (unambiguous alphabet)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ"  # no I, L, O
    digits = "23456789"                    # no 0, 1
    left = "".join(secrets.choice(alphabet) for _ in range(4))
    right = "".join(secrets.choice(digits) for _ in range(4))
    return f"{left}-{right}"
