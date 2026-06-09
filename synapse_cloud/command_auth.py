"""Command auth: verify browser Ed25519 signature + mint cloud co-signature.

The browser signs an `envelope` dict (sorted-key JSON → SHA-256 → Ed25519) with
a key that never leaves the browser. The cloud verifies that signature, then adds
its own co-signature using the same GRANT_SIGNING_KEY used for orchestration
grants. The resulting `command_auth` dict is threaded through the command bus and
delivered to the daemon inside every command frame, where the daemon verifies both
signatures before executing sensitive operations.

Backward-compatible: if the user has no registered public key (old web-UI clients
or users who haven't enrolled), verification is skipped and None is returned so
the command still dispatches without a `command_auth` block.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from .deps import Principal
from .orchestration_crypto import _signing_key


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    """Parse ISO-8601 datetime string; always return a UTC-aware datetime."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def verify_and_sign_command_auth(
    envelope: dict[str, Any],
    user_sig_b64: str,
    payload: dict[str, Any],
    principal: Principal,
    db: Any,
) -> Optional[dict[str, Any]]:
    """Verify the browser Ed25519 signature over ``envelope`` and co-sign with
    the cloud key.

    Returns the fully-signed ``command_auth`` dict, or ``None`` if the user has
    no registered public key (backward-compatible rollout).

    Raises ``HTTPException(400)`` for any signature or validation failure.
    """
    # 1. Fetch user's registered public key.
    rows = (
        await db.table("users")
        .select("command_public_key")
        .eq("id", principal.user_id)
        .execute()
    ).data or []
    if not rows:
        return None
    command_public_key = rows[0].get("command_public_key")
    if not command_public_key:
        # No key registered — skip verification (graceful rollout).
        return None

    # 2. Canonical bytes and sig_input (SHA-256 of compact sorted-key JSON).
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig_input = hashlib.sha256(canonical).digest()

    # 3. Verify user signature.
    try:
        vk = VerifyKey(base64.b64decode(command_public_key))
        vk.verify(sig_input, base64.b64decode(user_sig_b64))
    except (BadSignatureError, Exception) as exc:
        raise HTTPException(400, "invalid user signature") from exc

    now = _utcnow()

    # 4. Check expires_at.
    expires_at_raw = envelope.get("expires_at")
    if expires_at_raw is None:
        raise HTTPException(400, "envelope missing expires_at")
    try:
        expires_at = _parse_iso(str(expires_at_raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "envelope expires_at is not a valid ISO datetime") from exc
    if now >= expires_at:
        raise HTTPException(400, "command auth token has expired")

    # 5. Check not_before.
    not_before_raw = envelope.get("not_before")
    if not_before_raw is None:
        raise HTTPException(400, "envelope missing not_before")
    try:
        not_before = _parse_iso(str(not_before_raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "envelope not_before is not a valid ISO datetime") from exc
    if now < not_before:
        raise HTTPException(400, "command auth token is not yet valid")

    # 6. Check actor matches caller.
    if envelope.get("actor") != principal.user_id:
        raise HTTPException(400, "envelope actor does not match authenticated user")

    # 7. Check payload_hash.
    expected_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if envelope.get("payload_hash") != expected_hash:
        raise HTTPException(400, "envelope payload_hash does not match payload")

    # 8. Cloud co-signature.
    cloud_sig_bytes = _signing_key().sign(sig_input).signature
    cloud_sig_b64 = base64.b64encode(cloud_sig_bytes).decode("ascii")

    return {
        "envelope": envelope,
        "user_sig": user_sig_b64,
        "cloud_sig": cloud_sig_b64,
    }
