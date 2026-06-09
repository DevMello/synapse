"""ConnectionManager (§4.1): dual-channel outbound WebSocket client.

Maintains two daemon-initiated sockets to the cloud:

  * **control** (``settings.control_ws_url``) — bidirectional control + HITL. Receives
    ``command`` frames (dispatched + acked) and ``ack`` frames (acking OUR upstream
    rows). Carries the heartbeat/ping liveness task and the reconnect ``run.reconcile``.
  * **telemetry** (``settings.telemetry_ws_url``) — the high-volume firehose, kept off
    the control path so a flood of trace chunks can't head-of-line-block control/HITL.

Each channel runs its own connect→serve→backoff loop so one dropping doesn't stall the
other; both re-open on a drop. Auth is a ``Bearer`` access token on the handshake (with a
``?token=`` query fallback); a ``4401`` close triggers a refresh-token exchange then a
reopen. The WebSocketUplink (installed at ``run()``) enqueues durably first, and on every
(re)connect we replay that channel's unacked rows IN seq ORDER, so nothing is lost across
a reconnect (at-least-once; the cloud dedupes via idempotency keys).
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Optional

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from .. import wire
from ..logging import get_logger
from ..router import CommandContext, dispatch, set_command_auth_verifier, should_process
from ..store import LocalStore
from ..uplink import (
    CHANNEL_CONTROL,
    CHANNEL_TELEMETRY,
    Uplink,
    set_uplink,
)
from . import tokens
from .uplink_ws import WebSocketUplink

log = get_logger(__name__)

# Cloud close code that means "your access token is stale — refresh and reopen".
CLOSE_TOKEN_EXPIRED = 4401
# Backoff: start at 1s, exponential, capped at settings.reconnect_max_seconds.
_BACKOFF_START = 1.0


class ConnectionManager:
    """The long-running connection service (one per daemon).

    Exposes ``async def run(self)`` (gathered by ``run_daemon``) and ``async def
    stop(self)`` for graceful shutdown.
    """

    def __init__(self, daemon: Any) -> None:
        self._daemon = daemon
        self._settings = daemon.settings
        self._store: LocalStore = daemon.store
        self._stopping = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        # Live connections per channel (None while that channel is down).
        self._conns: dict[str, Optional[ClientConnection]] = {
            CHANNEL_CONTROL: None,
            CHANNEL_TELEMETRY: None,
        }
        self._uplink: Optional[WebSocketUplink] = None
        self._prev_uplink: Optional[Uplink] = None
        # A refresh requested by the control loop's 4401 handler; the connect path
        # performs the actual refresh so both channels pick up the new token.
        self._refresh_requested = asyncio.Event()

    # ── lifecycle ─────────────────────────────────────────────────────────
    async def run(self) -> None:
        """Install the real uplink and drive both channel loops until stopped."""
        from ..uplink import get_uplink

        self._uplink = WebSocketUplink(self._store)
        self._prev_uplink = get_uplink()
        set_uplink(self._uplink)

        self._tasks = [
            asyncio.create_task(self._channel_loop(CHANNEL_CONTROL)),
            asyncio.create_task(self._channel_loop(CHANNEL_TELEMETRY)),
        ]
        try:
            await self._stopping.wait()
        finally:
            await self._shutdown()

    async def stop(self) -> None:
        self._stopping.set()

    async def _shutdown(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._tasks = []
        # Restore the default uplink so a stopped manager doesn't keep a dead socket
        # installed (handlers fall back to the in-memory recorder).
        if self._prev_uplink is not None:
            set_uplink(self._prev_uplink)
            self._prev_uplink = None

    # ── per-channel connect/serve/backoff loop ────────────────────────────
    async def _channel_loop(self, channel: str) -> None:
        backoff = _BACKOFF_START
        cap = float(self._settings.reconnect_max_seconds)
        while not self._stopping.is_set():
            try:
                await self._connect_and_serve(channel)
                # A clean return (socket closed normally) resets the backoff so a
                # transient blip reconnects fast.
                backoff = _BACKOFF_START
            except asyncio.CancelledError:
                raise
            except _TokenExpired:
                # 4401: the cloud says our access token is stale. Try to refresh it.
                if await self._handle_token_expiry():
                    # Got a fresh token — reconnect immediately and reset backoff
                    # (an expected, recoverable handshake-auth condition).
                    backoff = _BACKOFF_START
                    continue
                # Refresh FAILED (the daemon was revoked, so its refresh token is dead,
                # or the token endpoint is unreachable). Do NOT `continue` — that would
                # hot-loop the handshake with the same dead token, pinning a CPU and
                # hammering the cloud. Fall through to the normal backoff instead so a
                # revoked daemon retries only at the capped interval.
                log.debug("%s channel: token refresh failed; backing off", channel)
            except Exception:  # noqa: BLE001 - any connect/serve error -> backoff+retry
                log.debug("%s channel error; reconnecting", channel, exc_info=True)
            if self._stopping.is_set():
                break
            # Exponential backoff with full jitter, capped.
            await self._sleep_with_jitter(backoff)
            backoff = min(backoff * 2.0, cap)

    async def _connect_and_serve(self, channel: str) -> None:
        url = (
            self._settings.control_ws_url
            if channel == CHANNEL_CONTROL
            else self._settings.telemetry_ws_url
        )
        access_token, _ = tokens.load_tokens()
        target = url
        # ?token= fallback when a token exists but header injection is unavailable:
        # we always set the header, but appending the query param too is harmless and
        # lets a header-stripping proxy still authenticate the daemon.
        if access_token:
            target = _with_token_query(url, access_token)
        connect_kwargs = self._connect_kwargs(access_token, target.startswith("wss"))

        try:
            ws = await connect(target, **connect_kwargs)
        except ConnectionClosed as exc:
            # The server can reject the handshake by closing immediately.
            if _close_code(exc) == CLOSE_TOKEN_EXPIRED:
                raise _TokenExpired() from exc
            raise

        self._conns[channel] = ws
        try:
            await self._on_connected(channel, ws)
            await self._serve(channel, ws)
        except ConnectionClosed as exc:
            if _close_code(exc) == CLOSE_TOKEN_EXPIRED:
                raise _TokenExpired() from exc
            # Any other close: fall through to backoff/reconnect.
        finally:
            self._conns[channel] = None
            if self._uplink is not None:
                self._uplink.set_sender(channel, None)
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 - already closed
                pass

    def _connect_kwargs(self, access_token: Optional[str], is_tls: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            # Let websockets drive transport ping/pong for dead-transport detection;
            # our app-level heartbeat drives cloud presence separately.
            "open_timeout": 10,
            "close_timeout": 5,
        }
        if access_token:
            header = {"Authorization": f"Bearer {access_token}"}
            # websockets >=10 uses additional_headers; older uses extra_headers.
            try:
                # Cheap capability probe without importing version internals.
                import inspect

                params = inspect.signature(connect).parameters
                if "additional_headers" in params:
                    kwargs["additional_headers"] = header
                else:  # pragma: no cover - legacy websockets
                    kwargs["extra_headers"] = header
            except Exception:  # noqa: BLE001 - fall back to query param only
                pass
        if is_tls and (not self._settings.verify_tls or self._settings.client_cert):
            # wss:// only — websockets rejects an ssl context on a ws:// URI.
            import ssl

            ctx = ssl.create_default_context()
            if not self._settings.verify_tls:
                # Lets a self-signed dev cloud be reached without a cert bundle.
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            if self._settings.client_cert:
                # mTLS: present our client certificate (a combined cert+key PEM) on
                # the handshake, per the optional mTLS option in integration.md §2.
                try:
                    ctx.load_cert_chain(self._settings.client_cert)
                except (OSError, ssl.SSLError):
                    log.warning(
                        "client_cert %s could not be loaded; proceeding without mTLS",
                        self._settings.client_cert,
                    )
            kwargs["ssl"] = ctx
        return kwargs

    # ── on (re)connect ────────────────────────────────────────────────────
    async def _on_connected(self, channel: str, ws: ClientConnection) -> None:
        log.info("%s channel connected", channel)
        # Install the live sender so the uplink ships immediately while connected.
        if self._uplink is not None:
            self._uplink.set_sender(channel, ws.send)
        # On the control channel, tell the cloud our last-known state so any work done
        # offline reconciles (§4.12). Do this BEFORE replay so the cloud has context.
        if channel == CHANNEL_CONTROL:
            # Register our self-configured identity first (§2.3): name/tags/platform/
            # version. The cloud only learned hostname/os/version at device-approval
            # time, so this keeps the daemons row current (e.g. after a self-update
            # bumps the version, or the operator edits tags/name in config).
            await self._send_register()
            await self._send_reconcile()
            # Initialise command-auth verifier from the configured grant_public_key.
            # This is the same Ed25519 key already trusted for orchestration grants (§2.4).
            # If the cloud delivers a different key in a daemon.register response that will
            # override this via _handle_register_response().
            self._maybe_init_command_auth_verifier()
        # Replay this channel's durably-queued, still-unacked frames IN seq ORDER.
        await self._replay_pending(channel, ws)

    def _maybe_init_command_auth_verifier(self, grant_key: Optional[str] = None) -> None:
        """Install a CommandAuthVerifier if a grant key is available.

        Uses *grant_key* when supplied (from a live register response) or falls back to
        ``settings.grant_public_key`` (statically configured). A missing or empty key means
        verification is not yet available and the existing soft-rollout behaviour applies.
        """
        key = grant_key or self._settings.grant_public_key
        if not key:
            return
        try:
            from ..command_auth import CommandAuthVerifier

            verifier = CommandAuthVerifier(key, self._store, self._settings)
            set_command_auth_verifier(verifier)
            log.debug("command_auth verifier initialised")
        except Exception:  # noqa: BLE001 - bad key at startup must not crash the connect
            log.warning("failed to initialise command_auth verifier", exc_info=True)

    async def _replay_pending(self, channel: str, ws: ClientConnection) -> None:
        """Re-send every unacked outbound row for this channel, in seq order.

        The row ``seq`` IS the wire seq, so the cloud's ack clears the exact row via the
        receive loop's ``store.ack_outbound``. At-least-once: a row stays until acked.
        """
        try:
            pending = await self._store.pending_outbound(channel)
        except Exception:  # noqa: BLE001 - store hiccup shouldn't kill the connect
            log.exception("failed to read pending outbound for %s", channel)
            return
        for row in pending:
            frame = wire.build_message(row["msg_type"], row["payload"], row["seq"])
            try:
                await ws.send(wire.dumps(frame))
            except ConnectionClosed:
                raise
            except Exception:  # noqa: BLE001 - stop replay; reconnect retries
                log.debug("replay send failed at seq=%s", row["seq"])
                return

    async def _send_register(self) -> None:
        """Emit ``daemon.register`` with this daemon's self-configured identity (§2.3).

        Routed through the durable uplink so it's at-least-once like any other upstream
        frame; the cloud handler is an idempotent update of the daemon's own row.
        """
        from .. import __version__
        from ..auth import keys as auth_keys

        payload: dict[str, Any] = {
            "name": self._settings.daemon_name or _hostname(),
            "tags": self._settings.tags,
            "platform": self._settings.platform_override or _platform_string(),
            "version": __version__,
        }
        # Register our X25519 public key so the Web UI can seal env-var values to this
        # daemon (§4.6). Read-only: we only report a key that pairing already created —
        # we never generate one here. Omitted if the daemon isn't paired yet.
        pubkey = auth_keys.get_daemon_public_key()
        if pubkey:
            payload["e2e_public_key"] = pubkey
        if self._uplink is not None:
            try:
                await self._uplink.send(
                    "daemon.register", payload, channel=CHANNEL_CONTROL
                )
            except Exception:  # noqa: BLE001 - registration is best-effort on connect
                log.debug("failed to enqueue daemon.register")

    async def _send_reconcile(self) -> None:
        """Emit ``run.reconcile`` listing in-flight runs + their latest checkpoint seq.

        Defensive: if the run/checkpoint tables are empty (or missing in a stripped test
        store) we send an empty list rather than crash the reconnect.
        """
        runs: list[dict[str, Any]] = []
        try:
            rows = await self._store.fetchall(
                "SELECT r.run_id AS run_id,"
                " (SELECT MAX(c.seq) FROM checkpoints c WHERE c.run_id = r.run_id)"
                "   AS checkpoint_seq"
                " FROM run_history r"
                " WHERE r.status IS NULL OR r.status NOT IN"
                "   ('finished','success','failed','cancelled','aborted')"
            )
            for row in rows:
                runs.append(
                    {
                        "run_id": row["run_id"],
                        "checkpoint_seq": row["checkpoint_seq"],
                    }
                )
        except Exception:  # noqa: BLE001 - missing/locked tables -> empty reconcile
            log.debug("reconcile state query failed; sending empty reconcile")
            runs = []
        # Route reconcile through the durable uplink so it too is at-least-once.
        if self._uplink is not None:
            try:
                await self._uplink.send(
                    "run.reconcile", {"runs": runs}, channel=CHANNEL_CONTROL
                )
            except Exception:  # noqa: BLE001
                log.debug("failed to enqueue run.reconcile")

    # ── receive loop ──────────────────────────────────────────────────────
    async def _serve(self, channel: str, ws: ClientConnection) -> None:
        # On the control channel, run a heartbeat/ping task alongside the receive loop.
        hb_task: Optional[asyncio.Task[None]] = None
        if channel == CHANNEL_CONTROL:
            hb_task = asyncio.create_task(self._heartbeat_loop(ws))
        try:
            async for raw in ws:
                await self._on_frame(channel, ws, raw)
        finally:
            if hb_task is not None:
                hb_task.cancel()
                try:
                    await hb_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    async def _on_frame(self, channel: str, ws: ClientConnection, raw: Any) -> None:
        # websockets may yield bytes for binary frames; we only speak text JSON.
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "replace")
        frame = wire.parse_frame(raw)
        if frame is None:
            return
        t = frame.get("type")
        if t == wire.TYPE_COMMAND:
            await self._handle_command(ws, frame)
        elif t == "daemon.registered":
            # Cloud responds to daemon.register with optional grant_public_key_b64.
            # Use it to (re)initialise the command-auth verifier with the live cloud key.
            payload = frame.get("payload") or {}
            grant_key = (
                payload.get("grant_public_key_b64")
                or payload.get("command_verify_key_b64")
            )
            if grant_key:
                self._maybe_init_command_auth_verifier(grant_key)
        elif t == wire.TYPE_ACK:
            # The cloud is acking one of OUR upstream rows: clear it durably.
            seq = frame.get("ack")
            if isinstance(seq, int):
                try:
                    await self._store.ack_outbound(seq)
                except Exception:  # noqa: BLE001
                    log.debug("ack_outbound failed for seq=%s", seq)
        elif t == wire.TYPE_PONG:
            # Liveness confirmed; transport-level ping/pong already guards the socket.
            log.debug("%s pong", channel)
        # Unknown types are ignored (forward-compatible with new cloud frames).

    async def _handle_command(self, ws: ClientConnection, frame: dict[str, Any]) -> None:
        cmd = wire.parse_command(frame)
        if cmd is None:
            return
        daemon_id = await self._kv("daemon_id")
        org_id = await self._kv("org_id")
        ctx = CommandContext(
            command_type=cmd.command_type,
            seq=cmd.seq,
            idempotency_key=cmd.idempotency_key,
            daemon_id=daemon_id,
            org_id=org_id,
        )
        # Dedupe BEFORE dispatch: a redelivered command runs at most once. Either way we
        # always ack (so the cloud stops redelivering this seq).
        try:
            fresh = await should_process(cmd.idempotency_key, cmd.command_type)
            if fresh:
                await dispatch(
                    cmd.command_type,
                    ctx,
                    cmd.payload,
                    command_auth=cmd.command_auth,
                    daemon_id=daemon_id or "",
                    require_auth=getattr(self._settings, "require_command_auth", False),
                )
        except Exception:  # noqa: BLE001 - never let one command kill the loop
            log.exception("command %s handling failed", cmd.command_type)
        finally:
            if cmd.seq is not None:
                try:
                    await ws.send(wire.dumps(wire.build_ack(cmd.seq)))
                except Exception:  # noqa: BLE001 - socket gone; reconnect handles it
                    log.debug("failed to ack command seq=%s", cmd.seq)

    async def _kv(self, key: str) -> Optional[str]:
        try:
            val = await self._store.kv_get(key)
        except Exception:  # noqa: BLE001
            return None
        return str(val) if val is not None else None

    # ── heartbeat / ping ──────────────────────────────────────────────────
    async def _heartbeat_loop(self, ws: ClientConnection) -> None:
        interval = max(1, int(self._settings.heartbeat_interval_seconds))
        _prune_ticks = 0
        try:
            # Send an initial heartbeat right away so cloud presence flips online fast.
            await ws.send(wire.dumps(wire.build_heartbeat()))
            while True:
                await asyncio.sleep(interval)
                # App-level heartbeat drives cloud presence/uptime; the ping expects a
                # pong so we also detect an app-silent-but-tcp-alive cloud.
                await ws.send(wire.dumps(wire.build_heartbeat()))
                await ws.send(wire.dumps(wire.build_ping()))
                # Prune expired command-auth nonces roughly once a minute.
                _prune_ticks += 1
                if _prune_ticks >= max(1, 60 // interval):
                    _prune_ticks = 0
                    try:
                        await self._store.prune_expired_nonces()
                    except Exception:  # noqa: BLE001
                        pass
        except (asyncio.CancelledError, ConnectionClosed):
            raise
        except Exception:  # noqa: BLE001 - don't let heartbeat errors leak
            log.debug("heartbeat loop ended", exc_info=True)

    # ── token refresh (4401) ──────────────────────────────────────────────
    async def _handle_token_expiry(self) -> bool:
        """Refresh the daemon access token after a 4401.

        Returns True if a fresh token was obtained (reconnect immediately), or False
        if the refresh failed (revoked daemon or unreachable token endpoint) so the
        caller backs off instead of hot-looping.
        """
        log.info("cloud closed with 4401; refreshing daemon token")
        new_token = await tokens.refresh(self._settings)
        if new_token is None:
            log.warning(
                "daemon token refresh failed (revoked, or token endpoint unreachable); "
                "backing off before retry"
            )
            return False
        return True

    # ── backoff helper ────────────────────────────────────────────────────
    async def _sleep_with_jitter(self, base: float) -> None:
        # Full jitter: sleep a random duration in [0, base]; bounded interruptibly so
        # stop() doesn't have to wait out a long backoff.
        delay = random.uniform(0.0, max(0.0, base))
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass


class _TokenExpired(Exception):
    """Internal signal: the cloud closed with 4401 — refresh + reconnect (no backoff)."""


def _close_code(exc: BaseException) -> Optional[int]:
    """Best-effort extraction of the WS close code from a ConnectionClosed."""
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    rcvd = getattr(exc, "rcvd", None)
    if rcvd is not None and isinstance(getattr(rcvd, "code", None), int):
        return rcvd.code
    return None


def _hostname() -> str:
    """Best-effort local hostname for the daemon's default registration name."""
    import socket

    try:
        return socket.gethostname() or "daemon"
    except Exception:  # noqa: BLE001 - never let identity detection crash a connect
        return "daemon"


def _platform_string() -> str:
    """A ``<system>-<machine>`` platform tag (e.g. ``darwin-arm64``) for the cloud row."""
    import platform as _platform

    system = (_platform.system() or "").lower() or "unknown"
    machine = (_platform.machine() or "").lower() or "unknown"
    return f"{system}-{machine}"


def _with_token_query(url: str, token: str) -> str:
    """Append ``token=<access>`` as a query param (header is still preferred)."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={token}"


__all__ = ["ConnectionManager"]
