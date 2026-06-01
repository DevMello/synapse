"""End-to-end smoke test for the WebSocket daemon hub.

Run as:  python -m tests.ws_smoke

It boots the real app under uvicorn (so the lifespan installs the WebSocket hub +
real command bus), seeds an org + daemon in Supabase, mints a daemon access token,
opens a real ``/ws/daemon`` connection with the ``websockets`` lib, then:

  1. asserts presence is upserted + daemon marked online;
  2. has the cloud send a command via ``get_command_bus().send(...)`` and asserts
     the JSON CloudMessage arrives over the socket with the idempotency key;
  3. confirms the command is buffered pending an ack, sends the ack, and confirms
     the pending buffer clears.

Prints PASS/FAIL and exits non-zero on failure.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

os.environ.setdefault("SYNAPSE_ENV", "test")

import uvicorn  # noqa: E402
import websockets  # noqa: E402

from synapse_cloud.config import get_settings  # noqa: E402
from synapse_cloud.db import service_db  # noqa: E402
from synapse_cloud.security import encode_daemon_access_token  # noqa: E402

PORT = 8111
BASE_WS = f"ws://127.0.0.1:{PORT}"


class _Server:
    """Run uvicorn in a background thread-free task within this event loop."""

    def __init__(self) -> None:
        config = uvicorn.Config(
            "synapse_cloud.app:app", host="127.0.0.1", port=PORT, log_level="warning"
        )
        self.server = uvicorn.Server(config)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self.server.serve())
        # Wait until uvicorn reports it's serving.
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
    """Create an org + daemon directly in Supabase. Returns (org_id, daemon_id, token)."""
    db = await service_db()
    suffix = uuid.uuid4().hex[:12]
    org = (
        await db.table("organizations")
        .insert({"name": f"smoke-org-{suffix}"})
        .execute()
    ).data[0]
    org_id = org["id"]
    daemon = (
        await db.table("daemons")
        .insert({"org_id": org_id, "name": f"smoke-daemon-{suffix}", "status": "offline"})
        .execute()
    ).data[0]
    daemon_id = daemon["id"]
    token = encode_daemon_access_token(daemon_id, org_id)
    return org_id, daemon_id, token


async def _cleanup(org_id: str) -> None:
    db = await service_db()
    try:
        await db.table("organizations").delete().eq("id", org_id).execute()
    except Exception:  # noqa: BLE001
        pass


async def _run() -> None:
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_role_key):
        raise SystemExit("smoke test requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env")

    server = _Server()
    await server.start()
    org_id = daemon_id = token = None
    try:
        org_id, daemon_id, token = await _seed_org_and_daemon()

        async with websockets.connect(f"{BASE_WS}/ws/daemon?token={token}") as ws:
            # 1) presence + online status
            ping = json.dumps({"type": "ping"})
            await ws.send(ping)
            pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert pong == {"type": "pong"}, f"expected pong, got {pong}"

            db = await service_db()
            pres = (
                await db.table("daemon_presence")
                .select("daemon_id")
                .eq("daemon_id", daemon_id)
                .execute()
            ).data
            assert len(pres) == 1, "presence row not upserted"
            status = (
                await db.table("daemons").select("status").eq("id", daemon_id).execute()
            ).data
            assert status[0]["status"] == "online", "daemon not marked online"

            # 2) cloud sends a command -> CloudMessage arrives over the socket
            from synapse_cloud.command_bus import get_command_bus

            bus = get_command_bus()
            result = await bus.send(
                daemon_id,
                "agent.run",
                {"run_id": "run-smoke", "agent_id": "agent-smoke"},
                idempotency_key="idem-smoke",
            )
            assert result.delivered is True, f"command not delivered: {result}"

            cmd = None
            for _ in range(10):
                frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                if frame.get("type") == "command":
                    cmd = frame
                    break
            assert cmd is not None, "CloudMessage command frame never arrived"
            assert cmd["command_type"] == "agent.run", cmd
            assert cmd["payload"]["run_id"] == "run-smoke", cmd
            assert cmd["idempotency_key"] == "idem-smoke", cmd
            seq = cmd["seq"]

            # 3) command buffered pending ack; ack clears it
            from synapse_cloud import ws_hub

            conn = ws_hub.get_registry().get(daemon_id)
            assert conn is not None and seq in conn.pending, "command not buffered pending ack"

            await ws.send(json.dumps({"type": "ack", "ack": seq}))
            # round-trip a ping so we know the ack has been processed server-side
            await ws.send(ping)
            for _ in range(10):
                frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                if frame.get("type") == "pong":
                    break
            assert seq not in conn.pending, "ack did not clear pending buffer"

        print("PASS: ws_smoke — presence, command delivery, and ack all verified")
    finally:
        if org_id:
            await _cleanup(org_id)
        await server.stop()


def main() -> int:
    try:
        asyncio.run(_run())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    except SystemExit as exc:
        print(f"FAIL: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"FAIL: {exc!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
