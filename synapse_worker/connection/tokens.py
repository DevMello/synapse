"""Daemon access/refresh token load + rotation (§4.1 auth).

The daemon presents its short-lived **access token** as a ``Bearer`` token when opening
each socket; on a ``4401`` close the cloud is telling us the access token is stale, so we
exchange the long-lived **refresh token** for a fresh pair and reopen.

SHARED CONVENTION (Unit 2 "Auth" writes these same keys): the keystore service is
``"synapse:daemon"`` and the keys are ``"access_token"`` / ``"refresh_token"``. The
refresh token **rotates** on every refresh, so we always store both values back. We do
NOT implement a real keystore backend here — ``get_keystore()`` is the foundation seam
(InMemoryKeystore by default; the auth unit installs the OS-keychain backend).
"""
from __future__ import annotations

from typing import Optional

import httpx

from ..config import Settings
from ..crypto import get_keystore
from ..logging import get_logger

log = get_logger(__name__)

# Keystore namespace + keys shared with the Auth unit. Do NOT diverge from these.
KEYSTORE_SERVICE = "synapse:daemon"
KEY_ACCESS = "access_token"
KEY_REFRESH = "refresh_token"


def load_tokens() -> tuple[Optional[str], Optional[str]]:
    """Read ``(access_token, refresh_token)`` from the keystore (either may be None)."""
    ks = get_keystore()
    return ks.get(KEYSTORE_SERVICE, KEY_ACCESS), ks.get(KEYSTORE_SERVICE, KEY_REFRESH)


def store_tokens(access_token: str, refresh_token: Optional[str]) -> None:
    """Persist a (possibly rotated) token pair back to the keystore."""
    ks = get_keystore()
    if access_token:
        ks.set(KEYSTORE_SERVICE, KEY_ACCESS, access_token)
    # The refresh token rotates on every refresh — store the new one so the old,
    # now-invalid, refresh token is never reused.
    if refresh_token:
        ks.set(KEYSTORE_SERVICE, KEY_REFRESH, refresh_token)


async def refresh(settings: Settings) -> Optional[str]:
    """Exchange the stored refresh token for a fresh access token (RFC 6749 grant).

    POSTs ``{"grant_type":"refresh_token","refresh_token":<rt>}`` to
    ``settings.token_url`` and expects ``{"access_token","refresh_token","expires_in"}``.
    Stores the rotated pair and returns the new access token, or None on failure (so the
    caller can back off and retry rather than crash the reconnect loop).
    """
    _, refresh_token = load_tokens()
    if not refresh_token:
        log.warning("token refresh requested but no refresh_token is stored")
        return None

    try:
        # verify_tls is honored so a self-signed dev cloud can be talked to in dev.
        async with httpx.AsyncClient(verify=settings.verify_tls, timeout=10.0) as client:
            resp = await client.post(
                settings.token_url,
                json={"grant_type": "refresh_token", "refresh_token": refresh_token},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001 - transient/cloud errors must not kill reconnect
        log.exception("token refresh failed against %s", settings.token_url)
        return None

    access_token = data.get("access_token")
    new_refresh = data.get("refresh_token") or refresh_token
    if not access_token:
        log.warning("token refresh response missing access_token")
        return None
    store_tokens(access_token, new_refresh)
    log.info("daemon access token refreshed")
    return access_token
