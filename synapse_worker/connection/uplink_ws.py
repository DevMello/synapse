"""The real outbound uplink: durable-enqueue-then-flush over the WebSocket (§4.1).

Feature units call ``get_uplink().send(...)``; this implementation guarantees the frame
survives a reconnect by writing it to the SQLite outbound queue *first*, then trying to
ship it over a live socket if one exists. The ConnectionManager installs this via
``set_uplink(...)`` only while running (tests rely on the InMemoryUplink default).

CRITICAL invariant: the upstream frame's ``seq`` MUST equal the ``outbound_queue`` row
``seq`` so the cloud's ack (which carries that same seq) lines up with the row the
receive loop marks acked (``store.ack_outbound(seq)``). We therefore use the row id the
store hands back as the wire seq — never a separate counter.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from .. import wire
from ..logging import get_logger
from ..store import LocalStore
from ..uplink import CHANNEL_CONTROL, Uplink

log = get_logger(__name__)

# A bound coroutine that writes one already-serialized text frame to a live socket.
ChannelSender = Callable[[str], Awaitable[None]]


class WebSocketUplink(Uplink):
    """Durable, at-least-once uplink backed by the SQLite outbound queue.

    The manager keeps the ``senders`` map current: a channel maps to a coroutine that
    writes to that channel's live socket, or is absent while that channel is down. When a
    channel is down we still enqueue (so nothing is lost) and the manager replays the row
    on the next (re)connect.
    """

    def __init__(self, store: LocalStore) -> None:
        self._store = store
        # channel -> live sender (set by the manager on connect, cleared on drop).
        self._senders: dict[str, ChannelSender] = {}

    # ── manager wiring ────────────────────────────────────────────────────
    def set_sender(self, channel: str, sender: Optional[ChannelSender]) -> None:
        """Install (or clear, with None) the live sender for one channel."""
        if sender is None:
            self._senders.pop(channel, None)
        else:
            self._senders[channel] = sender

    def is_connected(self) -> bool:
        return bool(self._senders)

    # ── Uplink interface ──────────────────────────────────────────────────
    async def send(
        self,
        msg_type: str,
        payload: dict[str, Any],
        *,
        channel: str = CHANNEL_CONTROL,
        idempotency_key: Optional[str] = None,
    ) -> None:
        # 1) DURABLE first: the row id becomes the wire seq so acks line up.
        seq = await self._store.enqueue_outbound(
            channel, msg_type, payload, idempotency_key=idempotency_key
        )
        # 2) If the channel is live, ship it now. If it isn't (or the send fails),
        #    the row stays unacked and the manager replays it on reconnect — so we
        #    swallow transient send errors rather than raise into the caller.
        sender = self._senders.get(channel)
        if sender is None:
            return
        frame = wire.build_message(msg_type, payload, seq)
        try:
            await sender(wire.dumps(frame))
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:  # noqa: BLE001 - socket died mid-send; replay handles it
            log.debug("immediate uplink send for seq=%s failed; will replay", seq)
