"""``synapse login`` — pair this daemon with the org via the device-code flow (§2).

Wires the pure flow logic (auth.device_flow) to its side effects: prints the user code +
URL + a terminal QR, polls for the token, stores tokens + the daemon keypair in the
keychain, and records daemon_id/org_id in the local store's kv table. Network calls stay
out of import time — they run only when the command is invoked.
"""
from __future__ import annotations

import asyncio
import base64
import json
import platform
import socket
from typing import Optional

import typer

from .. import __version__
from ..auth import keys
from ..auth.device_flow import DeviceCode, DeviceFlowClient, DeviceFlowError
from ..config import get_settings
from ..crypto import get_keystore
from ..logging import get_logger
from ..store import LocalStore
from ..paths import paths_for

log = get_logger(__name__)


def _decode_jwt_claims(token: str) -> dict:
    """Read claims from an HS256 JWT WITHOUT verifying (we don't hold the cloud secret).

    Prefer PyJWT (a transitive dep); fall back to manual base64url so login never depends
    on PyJWT being importable.
    """
    try:
        import jwt  # PyJWT

        return jwt.decode(token, options={"verify_signature": False})
    except Exception:  # noqa: BLE001 - PyJWT missing or odd token => manual parse
        try:
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)  # restore base64 padding
            return json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))
        except Exception:  # noqa: BLE001
            return {}


def _render_qr(data: str) -> None:
    """Print an ASCII QR for the completion URL; degrade gracefully if it can't."""
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(data)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception:  # noqa: BLE001 - QR is a convenience, never a hard requirement
        typer.echo("(QR unavailable — open the URL above)")


def _print_prompt(device: DeviceCode) -> None:
    typer.echo("")
    typer.echo("To pair this daemon, open the URL below and enter the code:")
    typer.echo(f"  URL:  {device.verification_uri}")
    typer.secho(f"  Code: {device.user_code}", bold=True)
    typer.echo("")
    _render_qr(device.verification_uri_complete)
    typer.echo("")
    typer.echo("Waiting for approval in your browser...")


def _run_async(coro) -> None:
    """Run a coroutine to completion from the sync CLI.

    Normally there's no running loop (``asyncio.run``). Under a host loop (e.g. a test
    invoking the command inside pytest-asyncio) we run it on a worker thread so we don't
    trip ``asyncio.run() cannot be called from a running event loop``.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return
    import threading

    error: list[BaseException] = []

    def _worker() -> None:
        try:
            asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread
            error.append(exc)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    if error:
        raise error[0]


async def _persist_identity(daemon_id: str, org_id: str) -> None:
    """Record daemon_id/org_id in the store's kv table.

    We open a short-lived connection to the durable db file rather than reuse the
    ``get_store()`` singleton: an aiosqlite connection is bound to the loop that created
    it, and ``login`` runs this on its own loop. WAL mode makes the concurrent write safe,
    and any already-open store reads the same committed rows back.
    """
    paths = paths_for(get_settings())
    paths.ensure_layout()
    store = await LocalStore(paths.db_path).connect()
    try:
        await store.kv_set("daemon_id", daemon_id)
        await store.kv_set("org_id", org_id)
    finally:
        await store.close()


def login(
    cloud_base_url: Optional[str] = typer.Option(
        None, "--cloud", help="Cloud base URL (defaults to configured SYNAPSE_CLOUD_BASE_URL)."
    ),
) -> None:
    """Pair this daemon with your Synapse org (OAuth 2.0 device-code flow)."""
    settings = get_settings()
    base = cloud_base_url or settings.cloud_base_url

    hostname = socket.gethostname()
    os_version = platform.platform()

    with DeviceFlowClient(base, verify=settings.verify_tls) as client:
        try:
            device = client.request_device_code(
                hostname=hostname,
                os_version=os_version,
                daemon_version=__version__,
            )
        except DeviceFlowError as exc:
            typer.secho(f"Login failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        _print_prompt(device)

        try:
            tokens = client.poll_for_token(device)
        except DeviceFlowError as exc:
            typer.secho(f"Login failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    # Tokens land in the keychain only — never echoed or written in plaintext.
    keystore = get_keystore()
    keys.store_tokens(tokens.access_token, tokens.refresh_token, keystore=keystore)
    keys.ensure_daemon_keypair(keystore=keystore)

    claims = _decode_jwt_claims(tokens.access_token)
    daemon_id = str(claims.get("sub", ""))
    org_id = str(claims.get("org_id", ""))
    if daemon_id and org_id:
        _run_async(_persist_identity(daemon_id, org_id))

    typer.secho("Daemon paired successfully.", fg=typer.colors.GREEN, bold=True)
    if daemon_id:
        typer.echo(f"  daemon id: {daemon_id}")
    if org_id:
        typer.echo(f"  org id:    {org_id}")
    typer.echo(f"  host:      {hostname}")


def register(app: typer.Typer) -> None:
    app.command("login")(login)
