"""Command authentication verifier — two-signature Ed25519 scheme.

Every human-triggered command must carry a ``command_auth`` field with:
  * ``envelope``  — dict with actor, daemon_id, nonce, not_before, expires_at, command_type
  * ``cloud_sig`` — Ed25519 over SHA-256(canonical JSON) using the grant signing key
  * ``user_sig``  — Ed25519 over the same bytes using the user's per-session command key

The verifier is installed as a singleton at startup (after daemon.register response) and
consulted by ``dispatch()`` in ``router.py`` before any handler runs.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from nacl.signing import VerifyKey

from .logging import get_logger

if TYPE_CHECKING:
    from .store import LocalStore

log = get_logger(__name__)

# Commands that require dual-signature authorisation before execution.
HUMAN_TRIGGERED: frozenset[str] = frozenset({
    "agent.run",
    "agent.cancel",
    "agent.deploy",
    "agent.update_prompt",
    "hitl.resolve",
    "run.recover",
    "env.set",
    "env.delete",
    "daemon.revoke",
})


@dataclass
class VerifyResult:
    ok: bool
    reason: str = ""


class CommandAuthVerifier:
    def __init__(self, cloud_verify_key_b64: str, store: "LocalStore", settings) -> None:
        self._cloud_vk = VerifyKey(base64.b64decode(cloud_verify_key_b64))
        self._store = store
        self._settings = settings  # for cloud API base URL + access token

    async def verify(
        self,
        command_type: str,
        command_auth: Optional[dict],
        daemon_id: str,
    ) -> VerifyResult:
        if command_type not in HUMAN_TRIGGERED:
            return VerifyResult(ok=True, reason="automated")
        if command_auth is None:
            return VerifyResult(ok=False, reason="missing command_auth")

        envelope = command_auth.get("envelope", {})
        user_sig_b64 = command_auth.get("user_sig", "")
        cloud_sig_b64 = command_auth.get("cloud_sig", "")

        # Canonical bytes: sort_keys compact JSON -> SHA-256
        canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        sig_input = hashlib.sha256(canonical).digest()

        # Verify cloud_sig
        try:
            self._cloud_vk.verify(sig_input, base64.b64decode(cloud_sig_b64))
        except Exception:
            return VerifyResult(ok=False, reason="invalid cloud_sig")

        # Check expiry windows
        now = datetime.datetime.now(datetime.timezone.utc)
        try:
            expires_at = datetime.datetime.fromisoformat(
                envelope["expires_at"].replace("Z", "+00:00")
            )
            not_before = datetime.datetime.fromisoformat(
                envelope["not_before"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            return VerifyResult(ok=False, reason="invalid expiry fields")
        if now > expires_at:
            return VerifyResult(ok=False, reason="command_auth expired")
        if now < not_before:
            return VerifyResult(ok=False, reason="command_auth not yet valid")

        # Check daemon_id matches this daemon
        if envelope.get("daemon_id") != daemon_id:
            return VerifyResult(ok=False, reason="daemon_id mismatch")

        # Nonce replay check — reject early if expires_at is missing to avoid
        # storing a nonce with empty expiry that prune_expired_nonces deletes immediately.
        expires_at_str = envelope.get("expires_at", "")
        nonce = envelope.get("nonce", "")
        if not nonce or not expires_at_str or not await self._store.check_and_store_nonce(nonce, expires_at_str):
            return VerifyResult(ok=False, reason="nonce replay or missing")

        # Verify user_sig
        actor = envelope.get("actor", "")
        user_pub = await self._get_user_key(actor)
        if not user_pub:
            return VerifyResult(ok=False, reason=f"no public key for user {actor}")
        try:
            VerifyKey(base64.b64decode(user_pub)).verify(sig_input, base64.b64decode(user_sig_b64))
        except Exception:
            return VerifyResult(ok=False, reason="invalid user_sig")

        return VerifyResult(ok=True)

    async def _get_user_key(self, user_id: str) -> Optional[str]:
        cached = await self._store.get_command_key(user_id)
        if cached:
            return cached
        try:
            import httpx

            from .connection import tokens
            access_token, _ = tokens.load_tokens()
            base_url = getattr(self._settings, "cloud_api_url", "")
            if not base_url or not access_token:
                return None
            headers = {"Authorization": f"Bearer {access_token}"}
            async with httpx.AsyncClient(
                verify=getattr(self._settings, "verify_tls", True),
                timeout=5.0,
            ) as client:
                resp = await client.get(
                    f"{base_url}/auth/command-key/{user_id}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    key = data.get("public_key")
                    if key:
                        await self._store.set_command_key(user_id, key)
                    return key
        except Exception as exc:
            log.debug("failed to fetch command key for %s: %s", user_id, exc)
        return None
