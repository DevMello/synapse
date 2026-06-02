"""OAuth 2.0 Device Authorization Grant client (RFC 8628), §2.

The daemon is not a Supabase Auth user; it pairs with the org via the device-code flow
served by ``synapse_cloud/routers/auth_device.py``:

  1. ``POST /auth/device/code``  → device_code + human user_code + verification URIs.
  2. The operator opens the URL in an already-authenticated browser and approves.
  3. ``POST /auth/device/token`` is polled every ``interval`` seconds; the cloud answers
     HTTP 400 ``{"error": ...}`` (``authorization_pending`` / ``slow_down`` /
     ``access_denied`` / ``expired_token``) until approval, then 200 with the tokens.

This module is pure flow logic: it returns/yields data and never touches the keychain or
the store. ``synapse login`` (cli/cmd_login.py) wires the side effects so this stays
unit-testable with an in-process httpx transport.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

from ..logging import get_logger

log = get_logger(__name__)

_DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

# Cloud error bodies (HTTP 400 {"error": ...}) we must understand.
_PENDING = "authorization_pending"
_SLOW_DOWN = "slow_down"
_ACCESS_DENIED = "access_denied"
_EXPIRED = "expired_token"

# Terminal errors that abort the poll loop with a clear message.
_TERMINAL = {_ACCESS_DENIED: "access denied", _EXPIRED: "the device code expired"}


class DeviceFlowError(RuntimeError):
    """Raised when pairing cannot complete (denied, expired, timed out, HTTP error)."""


@dataclass(frozen=True)
class DeviceCode:
    """Server response to ``POST /auth/device/code``."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    interval: int
    expires_in: int


@dataclass(frozen=True)
class TokenPair:
    """Server response to a successful ``POST /auth/device/token``."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


def _error_code(resp: httpx.Response) -> Optional[str]:
    """Pull the OAuth ``error`` field out of a 400 body, tolerating odd shapes.

    FastAPI wraps ``HTTPException(detail={"error": ...})`` as ``{"detail": {...}}`` so we
    look in both places; the cloud's contract is the ``error`` string either way.
    """
    try:
        body = resp.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        if isinstance(body.get("error"), str):
            return body["error"]
        detail = body.get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("error"), str):
            return detail["error"]
        if isinstance(detail, str):
            return detail
    return None


class DeviceFlowClient:
    """Drives the device-code handshake against one cloud base URL."""

    def __init__(
        self,
        cloud_base_url: str,
        *,
        client: Optional[httpx.Client] = None,
        verify: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self._base = cloud_base_url.rstrip("/")
        # An injected client (tests pass one wrapping a MockTransport) is reused as-is;
        # otherwise we own the client's lifecycle and close it in close().
        self._owns_client = client is None
        self._client = client or httpx.Client(verify=verify, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "DeviceFlowClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── step 1: request a device code ────────────────────────────────────────
    def request_device_code(
        self,
        *,
        hostname: str,
        os_version: str,
        daemon_version: str,
    ) -> DeviceCode:
        resp = self._client.post(
            f"{self._base}/auth/device/code",
            json={
                "hostname": hostname,
                "os_version": os_version,
                "daemon_version": daemon_version,
            },
        )
        if resp.status_code != 200:
            raise DeviceFlowError(
                f"device code request failed (HTTP {resp.status_code})"
            )
        data = resp.json()
        return DeviceCode(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            verification_uri_complete=data["verification_uri_complete"],
            interval=int(data.get("interval", 5)),
            expires_in=int(data.get("expires_in", 600)),
        )

    # ── step 3: poll for the token ───────────────────────────────────────────
    def poll_for_token(
        self,
        device: DeviceCode,
        *,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> TokenPair:
        """Poll ``/auth/device/token`` until approval, honoring interval/slow_down.

        ``sleep``/``now`` are injectable so tests drive the loop without real delays.
        """
        interval = max(1, device.interval)
        deadline = now() + device.expires_in
        while True:
            if now() >= deadline:
                raise DeviceFlowError("the device code expired before approval")

            resp = self._client.post(
                f"{self._base}/auth/device/token",
                json={
                    "grant_type": _DEVICE_CODE_GRANT,
                    "device_code": device.device_code,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return TokenPair(
                    access_token=data["access_token"],
                    refresh_token=data["refresh_token"],
                    token_type=data.get("token_type", "Bearer"),
                    expires_in=int(data.get("expires_in", 0)),
                )

            error = _error_code(resp)
            if error == _PENDING:
                pass  # keep polling at the current interval
            elif error == _SLOW_DOWN:
                # RFC 8628 §3.5: back off by 5s and keep going.
                interval += 5
            elif error in _TERMINAL:
                raise DeviceFlowError(_TERMINAL[error])
            else:
                raise DeviceFlowError(
                    f"unexpected token response (HTTP {resp.status_code}, error={error!r})"
                )

            sleep(interval)
