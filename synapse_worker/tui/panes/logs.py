"""Logs pane (§4.9).

A searchable view over recent trace/log events. It subscribes to the event bus like the
Live pane but keeps a bounded in-memory buffer and re-renders it through a substring
filter typed into the input. Redaction markers (e.g. ``«redacted»`` / ``[REDACTED]``)
that the on-device filter chain inserts are preserved verbatim so the operator can see
*where* secrets were scrubbed.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Optional

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Input, RichLog

from ..app import register_pane

# Cap the retained history so a long-running session can't grow unbounded.
_MAX_LINES = 1000


def _format_event(event: Any) -> str:
    kind = getattr(event, "kind", "?")
    data = getattr(event, "data", None) or {}
    text = data.get("text") or data.get("message") or data.get("delta") or str(data)
    return f"<{kind}> {text}".strip()


class LogsPane(Container):
    """Buffered, filterable log view fed by the event bus."""

    DEFAULT_CSS = """
    LogsPane { height: 1fr; }
    LogsPane Input { dock: top; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._buffer: deque[str] = deque(maxlen=_MAX_LINES)
        self._filter: str = ""
        self._queue: Optional[Any] = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="filter logs… (substring)", id="logs-filter")
        yield RichLog(id="logs-view", highlight=False, markup=False, wrap=True)

    async def on_mount(self) -> None:
        try:
            from ...events import get_event_bus

            self._queue = get_event_bus().subscribe()
        except Exception:  # noqa: BLE001
            return
        # Textual worker so the reader is cancelled cleanly on unmount.
        self.run_worker(self._pump(), name="logs-pump", exit_on_error=False)

    async def _pump(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            line = _format_event(event)
            self._buffer.append(line)
            if self._matches(line):
                self.query_one("#logs-view", RichLog).write(line)

    def _matches(self, line: str) -> bool:
        return self._filter in line.lower() if self._filter else True

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "logs-filter":
            return
        self._filter = event.value.strip().lower()
        self._rerender()

    def _rerender(self) -> None:
        """Replay the buffer through the active filter into a cleared view."""
        view = self.query_one("#logs-view", RichLog)
        view.clear()
        for line in self._buffer:
            if self._matches(line):
                view.write(line)

    async def on_unmount(self) -> None:
        # Do NOT touch self._task — that's the widget's OWN message-loop task; cancelling
        # it during unmount makes Textual's teardown gather raise CancelledError. The
        # event-bus reader is a Textual worker, which Textual cancels for us on unmount.
        if self._queue is not None:
            try:
                from ...events import get_event_bus

                get_event_bus().unsubscribe(self._queue)
            except Exception:  # noqa: BLE001
                pass


@register_pane("logs", "Logs", order=30)
def build_logs_pane() -> LogsPane:
    return LogsPane()
