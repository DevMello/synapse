"""Daemon WebSocket handshake auth.

The daemon presents its short-lived device access token (HS256 JWT minted by the
device-code flow, unit 1) on the WebSocket handshake. We accept it either as an
`Authorization: Bearer <token>` header or as a `?token=` query param (browsers and
some WS clients can't set custom handshake headers, so the query param is a fallback).

On any failure we close the socket with application close code 4401 ("unauthorized",
mirroring the revoke teardown code from cloud-backend.md §5) and return None so the
caller aborts before accepting any frames.
"""
from __future__ import annotations

from typing import Optional

from fastapi import WebSocket

from ..security import DaemonPrincipal, decode_daemon_access_token

# Application-level close code for an unauthenticated/revoked daemon socket.
WS_UNAUTHORIZED = 4401


def _extract_token(ws: WebSocket) -> Optional[str]:
    """Pull the bearer token from the Authorization header or ?token= query param."""
    header = ws.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
        if token:
            return token
    token = ws.query_params.get("token")
    if token:
        return token.strip()
    return None


async def authenticate(ws: WebSocket) -> Optional[DaemonPrincipal]:
    """Validate the handshake token.

    Returns the DaemonPrincipal on success. On failure, closes the socket with
    code 4401 and returns None. The caller MUST abort when None is returned.

    Note: the socket must already be accepted (``await ws.accept()``) before
    calling ``ws.close`` with a custom code, so callers accept first, then auth.
    """
    token = _extract_token(ws)
    if not token:
        await ws.close(code=WS_UNAUTHORIZED)
        return None
    try:
        return decode_daemon_access_token(token)
    except Exception:  # noqa: BLE001 - any jwt error => reject the handshake
        await ws.close(code=WS_UNAUTHORIZED)
        return None
