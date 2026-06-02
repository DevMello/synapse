"""Live pane (§4.9).

Streams the reasoning trace of the active run. It subscribes to the in-process event
bus on mount and appends each incoming :class:`Event` to a scrolling log. The bus is the
runtime's local fan-out (distinct from the cloud uplink), so this stays fully decoupled
from the runtime — we only read events.
"""
from __future__ import annotations

from typing import Any, Optional

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import RichLog

from ..app import register_pane


def _format_event(event: Any) -> str:
    """One readable line per event. Trace text is surfaced; other kinds show their data."""
    kind = getattr(event, "kind", "?")
    run_id = getattr(event, "run_id", None)
    data = getattr(event, "data", None) or {}
    prefix = f"[{run_id[:8]}]" if isinstance(run_id, str) and run_id else ""
    if kind == "trace":
        text = data.get("text") or data.get("message") or data.get("delta") or ""
        return f"{prefix} {text}".strip()
    return f"{prefix} <{kind}> {data}".strip()


class LivePane(Container):
    """Renders streaming events; owns a background reader task on the event bus."""

    DEFAULT_CSS = """
    LivePane { height: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._queue: Optional[Any] = None

    def compose(self) -> ComposeResult:
        yield RichLog(id="live-log", highlight=False, markup=False, wrap=True)

    async def on_mount(self) -> None:
        log = self.query_one("#live-log", RichLog)
        try:
            from ...events import get_event_bus

            self._queue = get_event_bus().subscribe()
        except Exception:  # noqa: BLE001 - bus unavailable; pane stays inert but alive
            log.write("(no event bus available)")
            return
        log.write("Waiting for live trace…")
        # A Textual worker (not a raw asyncio task) so the pump is cancelled cleanly when
        # the pane unmounts — Textual swallows the CancelledError for us.
        self.run_worker(self._pump(), name="live-pump", exit_on_error=False)

    async def _pump(self) -> None:
        """Drain the subscription queue, appending each event to the log."""
        assert self._queue is not None
        log = self.query_one("#live-log", RichLog)
        while True:
            event = await self._queue.get()
            log.write(_format_event(event))

    async def on_unmount(self) -> None:
        # Drop our subscription so we don't leak a queue across app restarts (tests).
        if self._queue is not None:
            try:
                from ...events import get_event_bus

                get_event_bus().unsubscribe(self._queue)
            except Exception:  # noqa: BLE001
                pass


@register_pane("live", "Live", order=20)
def build_live_pane() -> LivePane:
    return LivePane()
