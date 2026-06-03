"""A mock Cloud Backend WebSocket hub for daemon unit tests.

Speaks the exact frames the real hub does (``synapse_cloud/ws_hub``):

  * accepts control (``/ws/daemon``) and telemetry (``/ws/daemon/telemetry``) sockets,
  * pushes ``command`` frames to the daemon and records its ``ack`` replies,
  * records upstream daemon messages (hitl.request, run.finished, memory.delta, ...) and
    acks each by its seq,
  * replies ``pong`` to ``ping`` and records ``heartbeat`` frames,
  * can reject the next connection with close code ``4401`` to exercise token-refresh.

No Supabase, no auth crypto — it only validates the wire contract a daemon unit must
honor. The Connection Manager unit drives it directly; other units that emit upstream
frames can assert against ``cloud.messages``.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed


def _path_of(ws: Any) -> str:
    req = getattr(ws, "request", None)
    if req is not None and getattr(req, "path", None):
        return req.path
    return getattr(ws, "path", "") or ""


class MockCloud:
    def __init__(self) -> None:
        self.control_conns: list[Any] = []
        self.telemetry_conns: list[Any] = []
        self.messages: list[dict[str, Any]] = []     # upstream daemon frames (non-ack)
        self.acks: list[int] = []                      # seqs the daemon acked
        self.heartbeats: int = 0
        self.connect_count: int = 0
        self.reject_next: bool = False                 # close next socket with 4401
        self.reject_all: bool = False                  # close EVERY socket with 4401
        self.last_token: Optional[str] = None
        self._server: Any = None
        self._seq: int = 0
        self.url: str = ""

    async def start(self) -> "MockCloud":
        self._server = await websockets.serve(self._handler, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}"
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ── server side ───────────────────────────────────────────────────────
    async def _handler(self, ws: Any) -> None:
        self.connect_count += 1
        path = _path_of(ws)
        # Capture a presented token (header or ?token=) for refresh assertions.
        try:
            self.last_token = (
                ws.request.headers.get("authorization") if getattr(ws, "request", None) else None
            )
        except Exception:  # noqa: BLE001
            self.last_token = None
        if self.reject_all or self.reject_next:
            self.reject_next = False
            await ws.close(code=4401)
            return
        is_control = "telemetry" not in path
        (self.control_conns if is_control else self.telemetry_conns).append(ws)
        try:
            async for raw in ws:
                await self._on_frame(ws, raw)
        except ConnectionClosed:
            pass
        finally:
            (self.control_conns if is_control else self.telemetry_conns).remove(ws) \
                if ws in (self.control_conns if is_control else self.telemetry_conns) else None

    async def _on_frame(self, ws: Any, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(frame, dict):
            return
        t = frame.get("type")
        if t == "ack":
            seq = frame.get("ack")
            if isinstance(seq, int):
                self.acks.append(seq)
            return
        if t == "ping":
            await ws.send(json.dumps({"type": "pong"}))
            return
        if t == "heartbeat":
            self.heartbeats += 1
            return
        # An upstream daemon message: record + ack by its seq.
        self.messages.append(frame)
        seq = frame.get("seq")
        if isinstance(seq, int):
            await ws.send(json.dumps({"type": "ack", "ack": seq}))

    # ── test helpers ──────────────────────────────────────────────────────
    async def send_command(
        self,
        command_type: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        idempotency_key: Optional[str] = None,
        channel: str = "control",
    ) -> int:
        self._seq += 1
        frame = {
            "type": "command",
            "seq": self._seq,
            "command_type": command_type,
            "payload": payload or {},
            "idempotency_key": idempotency_key,
        }
        conns = self.control_conns if channel == "control" else self.telemetry_conns
        for ws in list(conns):
            await ws.send(json.dumps(frame))
        return self._seq

    def messages_of(self, msg_type: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("type") == msg_type]

    async def wait_for(self, msg_type: str, timeout: float = 3.0) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            found = self.messages_of(msg_type)
            if found:
                return found[-1]
            await asyncio.sleep(0.02)
        raise TimeoutError(f"no upstream {msg_type!r} within {timeout}s")

    async def wait_until(self, predicate, timeout: float = 3.0):
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return True
            await asyncio.sleep(0.02)
        raise TimeoutError("condition not met in time")
