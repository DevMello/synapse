"""LIVE end-to-end smoke test: the real synapse-worker daemon against the real cloud.

Run as:  python -m tools.tests.live_cloud_smoke

Unlike ``tools/tests/ws_smoke.py`` (which drives a raw ``websockets`` client), this boots the
**actual** ``synapse_worker`` daemon stack — its ``ConnectionManager``, the durable
``WebSocketUplink``, the command router, and the real command handlers — and connects it
to the **real Cloud Backend** running under uvicorn against **real Supabase**. It proves
the full loop with production code on both ends:

  A. Handshake + presence — the daemon opens BOTH channels (control + telemetry) with its
     Bearer token; the cloud upserts a presence row and marks the daemon ``online``.
  B. Cloud -> daemon command — the cloud pushes ``daemon.ping`` via the command bus; the
     daemon's ConnectionManager receives it, the REAL ``router.dispatch`` runs the handler,
     and the daemon ACKs (the cloud's pending buffer clears).
  C. Daemon -> cloud upstream — the daemon emits a frame through its REAL uplink
     (``hitl.request``); it travels the live socket and the cloud persists a
     ``hitl_requests`` row in Supabase (DB-observable proof of the upstream path).

Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env (skips cleanly otherwise).
Prints PASS/FAIL and exits non-zero on failure. Seeds a throwaway org and deletes it
(cascade) on teardown.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid

PORT = 8112

# Both apps read the environment at import time, so configure BEFORE importing either.
os.environ.setdefault("SYNAPSE_ENV", "test")            # cloud: real DB, fake side-effects
os.environ.setdefault("SYNAPSE_WORKER_ENV", "test")     # daemon: in-memory keystore default
os.environ["SYNAPSE_CLOUD_BASE_URL"] = f"http://127.0.0.1:{PORT}"
os.environ["SYNAPSE_HOME"] = tempfile.mkdtemp(prefix="syn-live-")

import uvicorn  # noqa: E402

from synapse_cloud.config import get_settings as cloud_settings  # noqa: E402
from synapse_cloud.db import service_db  # noqa: E402
from synapse_cloud.security import encode_daemon_access_token  # noqa: E402


class _Server:
    """Run uvicorn as a task in this event loop (lifespan installs the WS hub + bus)."""

    def __init__(self) -> None:
        config = uvicorn.Config(
            "synapse_cloud.app:app", host="127.0.0.1", port=PORT, log_level="warning"
        )
        self.server = uvicorn.Server(config)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self.server.serve())
        for _ in range(100):
            if self.server.started:
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("uvicorn did not start")

    async def stop(self) -> None:
        self.server.should_exit = True
        if self._task is not None:
            await self._task


async def _seed_org_and_daemon() -> tuple[str, str, str]:
    db = await service_db()
    suffix = uuid.uuid4().hex[:12]
    org = (
        await db.table("organizations").insert({"name": f"live-org-{suffix}"}).execute()
    ).data[0]
    org_id = org["id"]
    daemon = (
        await db.table("daemons")
        .insert({"org_id": org_id, "name": f"live-daemon-{suffix}", "status": "offline"})
        .execute()
    ).data[0]
    token = encode_daemon_access_token(daemon["id"], org_id)
    return org_id, daemon["id"], token


async def _cleanup(org_id: str) -> None:
    db = await service_db()
    try:
        await db.table("organizations").delete().eq("id", org_id).execute()
    except Exception:  # noqa: BLE001
        pass


async def _poll(fn, *, timeout: float = 10.0, interval: float = 0.1):
    """Poll an async predicate until it returns truthy or the timeout lapses."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        val = await fn()
        if val:
            return val
        await asyncio.sleep(interval)
    return None


async def _run() -> None:
    if not (cloud_settings().supabase_url and cloud_settings().supabase_service_role_key):
        raise SystemExit("live smoke requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env")

    server = _Server()
    await server.start()
    org_id = None
    mgr = None
    mgr_task = None
    ok = False
    try:
        org_id, daemon_id, token = await _seed_org_and_daemon()

        # ── build the REAL daemon stack, pointed at the live cloud ──────────────
        from synapse_worker.config import reset_settings_cache
        reset_settings_cache()
        from synapse_worker.app import build_daemon
        from synapse_worker.connection.manager import ConnectionManager
        from synapse_worker.crypto import get_keystore
        from synapse_worker.router import on_command
        from synapse_worker.uplink import get_uplink

        daemon = build_daemon()
        await daemon.store.connect()
        await daemon.store.kv_set("daemon_id", daemon_id)
        await daemon.store.kv_set("org_id", org_id)
        # Seed the daemon's access token where ConnectionManager/tokens.load_tokens reads it.
        get_keystore().set("synapse:daemon", "access_token", token)

        # Probe handler (in addition to the real daemon.ping handler) to confirm dispatch.
        dispatched = asyncio.Event()

        @on_command("daemon.ping")
        async def _probe(ctx, payload):  # noqa: ANN001
            dispatched.set()

        mgr = ConnectionManager(daemon)
        mgr_task = asyncio.create_task(mgr.run())

        db = await service_db()

        # ── A. handshake + presence ────────────────────────────────────────────
        online = await _poll(
            lambda: db.table("daemons").select("status").eq("id", daemon_id).execute(),
            timeout=15.0,
        )
        # Re-query for the actual status (the lambda returns the response object).
        async def _is_online():
            rows = (await db.table("daemons").select("status").eq("id", daemon_id).execute()).data
            return rows and rows[0]["status"] == "online"

        assert await _poll(_is_online, timeout=15.0), "daemon never marked online"
        async def _has_presence():
            rows = (await db.table("daemon_presence").select("daemon_id").eq("daemon_id", daemon_id).execute()).data
            return bool(rows)

        assert await _poll(_has_presence, timeout=10.0), "presence row not upserted"
        print("  A. PASS — daemon connected; presence + online status verified in Supabase")

        # ── B. cloud -> daemon command -> dispatch + ack ───────────────────────
        from synapse_cloud import ws_hub
        from synapse_cloud.command_bus import get_command_bus

        res = await get_command_bus().send(
            daemon_id, "daemon.ping", {"id": "live-probe"}, idempotency_key="live-ping-1"
        )
        assert res.delivered is True, f"command not delivered: {res}"
        await asyncio.wait_for(dispatched.wait(), timeout=10.0)

        conn = ws_hub.get_registry().get(daemon_id)
        assert conn is not None, "cloud has no live connection for the daemon"
        cleared = await _poll(lambda: asyncio.sleep(0, result=(not conn.pending)), timeout=10.0)
        assert cleared, "daemon did not ack the command (pending buffer never cleared)"
        print("  B. PASS — cloud->daemon command dispatched by the real router and ACKed")

        # ── C. daemon -> cloud upstream via the REAL uplink -> Supabase row ─────
        # Emit a telemetry metric through the daemon's durable WebSocketUplink and assert
        # the real cloud handler persisted it to the metrics table (DB-observable proof of
        # the daemon->cloud->Supabase path). A unique name avoids collisions.
        metric_name = f"daemon.smoke.{uuid.uuid4().hex[:8]}"
        await get_uplink().send(
            "telemetry.metric",
            {"name": metric_name, "value": 42.5, "labels": {"src": "live-smoke"}},
            channel="telemetry",
        )

        async def _metric_row():
            rows = (
                await db.table("metrics").select("name,value").eq("org_id", org_id)
                .eq("name", metric_name).execute()
            ).data
            return rows[0] if rows else None

        row = await _poll(_metric_row, timeout=15.0)
        assert row is not None, "daemon's upstream telemetry.metric never persisted in Supabase"
        assert float(row["value"]) == 42.5, row
        print("  C. PASS — daemon->cloud upstream frame persisted by the real cloud handler")

        print("PASS: live_cloud_smoke — real daemon <-> real cloud loop verified end to end")
        ok = True
    except (AssertionError, SystemExit) as exc:
        print(f"FAIL: {exc}")
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
    finally:
        if mgr is not None:
            await mgr.stop()
        if mgr_task is not None:
            mgr_task.cancel()
            try:
                await mgr_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if org_id:
            await _cleanup(org_id)
        await server.stop()
        # Force a clean, prompt exit: lingering Supabase/uvicorn background tasks can keep
        # asyncio.run's loop-shutdown from returning, so terminate now that cleanup is done.
        sys.stdout.flush()
        os._exit(0 if ok else 1)


def main() -> int:
    try:
        asyncio.run(_run())  # os._exit() fires inside, so this never returns
    except Exception as exc:  # noqa: BLE001 - pre-server-start failures only
        import traceback
        traceback.print_exc()
        print(f"FAIL: {exc!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
