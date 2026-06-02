"""Daemon pane (§4.9).

Shows the daemon's own vitals: version, uptime, CPU/memory/disk usage, active runs, and
queue depth — sourced from :func:`synapse_worker.health.collect`. A periodic refresh
keeps the numbers live without coupling to the heartbeat unit.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from ..app import register_pane

# How often (seconds) to re-sample health while the pane is visible.
_REFRESH_INTERVAL = 2.0


def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class DaemonPane(Container):
    """Connection status / uptime / resource usage / version."""

    DEFAULT_CSS = """
    DaemonPane { height: 1fr; padding: 1 2; }
    """

    def compose(self) -> ComposeResult:
        yield Static(id="daemon-info")

    def on_mount(self) -> None:
        self.refresh_info()
        # set_interval is a Textual primitive; the timer is auto-cancelled on unmount.
        self.set_interval(_REFRESH_INTERVAL, self.refresh_info)

    def refresh_info(self) -> None:
        info = self.query_one("#daemon-info", Static)
        info.update(self._info_text())

    def _info_text(self) -> str:
        # NOTE: do NOT name this ``_render`` — that clobbers Textual's internal
        # ``Widget._render()`` (which must return a Visual), causing a render-time
        # ``'str' object has no attribute 'render_strips'`` crash.
        try:
            from ... import __version__
            from ...health import collect

            snap = collect()
            version = __version__
        except Exception:  # noqa: BLE001 - never let a sampling hiccup crash the pane
            return "daemon health unavailable"

        lines = [
            f"Version:      {version}",
            f"Status:       running",
            f"Uptime:       {_fmt_uptime(snap.uptime_seconds)}",
            f"CPU:          {snap.cpu_percent:.1f}%",
            f"Memory:       {snap.mem_mb:.1f} MB",
            f"Disk:         {snap.disk_percent:.1f}%",
            f"Active runs:  {snap.active_runs}",
            f"Queue depth:  {snap.queue_depth}",
        ]
        return "\n".join(lines)


@register_pane("daemon", "Daemon", order=50)
def build_daemon_pane() -> DaemonPane:
    return DaemonPane()
