"""Daemon token helpers for the device-code auth flow (unit 1).

Builds on `synapse_cloud.security` to mint short-lived access tokens (HS256 JWT)
and long-lived, rotating refresh tokens (opaque, stored hashed on the daemon row).

A daemon authenticates with a `Bearer` access token on the WebSocket handshake; it
exchanges its refresh token at `POST /auth/token` to mint a new access token, and
the refresh token is rotated on every use so a replayed/stolen refresh token is
detectable. A revoked daemon (`revoked_at` set) can never mint a new token.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from ..security import (
    encode_daemon_access_token,
    hash_token,
    new_opaque_token,
)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"

    def to_response(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
        }


def is_revoked(daemon_row: dict[str, Any]) -> bool:
    """True if the daemon has been revoked (revoked_at set)."""
    return daemon_row.get("revoked_at") is not None


def access_token_ttl() -> int:
    return get_settings().daemon_access_token_ttl_seconds


def mint_access_token(daemon_id: str, org_id: str) -> str:
    """Short-lived HS256 daemon access token."""
    return encode_daemon_access_token(daemon_id, org_id)


def new_refresh_token() -> tuple[str, str]:
    """Return (plaintext_refresh_token, refresh_token_hash). Store the hash only."""
    token = new_opaque_token()
    return token, hash_token(token)


def refresh_fields() -> tuple[str, dict[str, Any]]:
    """Build a fresh refresh token + the daemon-row columns to persist it.

    Returns (plaintext_refresh_token, {refresh_token_hash, refresh_token_issued_at}).
    """
    plaintext, token_hash = new_refresh_token()
    fields = {
        "refresh_token_hash": token_hash,
        "refresh_token_issued_at": datetime.now(timezone.utc).isoformat(),
    }
    return plaintext, fields


def mint_token_pair(daemon_id: str, org_id: str) -> tuple[TokenPair, dict[str, Any]]:
    """Mint an access + refresh token pair and the daemon-row update fields.

    Returns (TokenPair, daemon_row_update_fields). The caller persists the update
    fields (refresh_token_hash + issued_at) on the daemons row.
    """
    access = mint_access_token(daemon_id, org_id)
    refresh_plain, fields = refresh_fields()
    pair = TokenPair(
        access_token=access,
        refresh_token=refresh_plain,
        expires_in=access_token_ttl(),
    )
    return pair, fields


def refresh_token_matches(daemon_row: dict[str, Any], presented: str) -> bool:
    """Constant-time-ish check that a presented refresh token matches the stored hash."""
    stored = daemon_row.get("refresh_token_hash")
    if not stored:
        return False
    from ..security import tokens_equal

    return tokens_equal(stored, hash_token(presented))
