"""Agents pane (§4.9).

Lists every agent with its current status, last run, and next scheduled run. The data
is joined on demand from the durable store's ``agents``, ``run_history``, and
``schedules`` tables — never cached at import time, so the pane reflects live state each
time it is mounted/refreshed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Label

from ..app import register_pane


def _fmt_ts(ts: Any) -> str:
    """Render an epoch-seconds value as a short UTC timestamp, or ``—`` if absent."""
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OverflowError, OSError, TypeError):
        return "—"


class AgentsPane(Container):
    """Container that renders the agents table; refreshes itself on mount."""

    DEFAULT_CSS = """
    AgentsPane { height: 1fr; }
    AgentsPane .empty { color: $text-muted; padding: 1 2; }
    """

    def compose(self) -> ComposeResult:
        # The empty-state label is shown until/if there are no rows to display.
        yield Label("No agents registered.", classes="empty", id="agents-empty")
        table = DataTable(id="agents-table", zebra_stripes=True)
        table.display = False
        yield table

    async def on_mount(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        table.add_columns("Agent", "Type", "Status", "Last run", "Next run")
        await self.refresh_rows()

    async def refresh_rows(self) -> None:
        """(Re)load the agent rows from the store, joining last/next run info.

        Resilient: if the store is uninitialised or empty the pane shows its empty
        state rather than raising.
        """
        rows = await self._load()
        table = self.query_one("#agents-table", DataTable)
        empty = self.query_one("#agents-empty", Label)
        table.clear()
        if not rows:
            table.display = False
            empty.display = True
            return
        empty.display = False
        table.display = True
        for r in rows:
            table.add_row(
                r["name"],
                r["type"],
                r["status"],
                r["last_run"],
                r["next_run"],
            )

    async def _load(self) -> list[dict[str, Any]]:
        try:
            from ...store import get_store

            store = get_store()
        except Exception:  # noqa: BLE001 - store not initialised yet
            return []
        try:
            agents = await store.fetchall(
                "SELECT id, name, type FROM agents ORDER BY name"
            )
        except Exception:  # noqa: BLE001 - table missing / db closed
            return []

        out: list[dict[str, Any]] = []
        for a in agents:
            last = await store.fetchone(
                "SELECT status, finished_at, started_at FROM run_history"
                " WHERE agent_id=? ORDER BY COALESCE(finished_at, started_at) DESC LIMIT 1",
                (a["id"],),
            )
            sched = await store.fetchone(
                "SELECT kind, expr FROM schedules WHERE agent_id=? ORDER BY updated_at DESC LIMIT 1",
                (a["id"],),
            )
            out.append(
                {
                    "name": a.get("name") or a["id"],
                    "type": a.get("type") or "—",
                    "status": (last or {}).get("status") or "idle",
                    "last_run": _fmt_ts((last or {}).get("finished_at") or (last or {}).get("started_at")),
                    # Schedules use cron/interval exprs; we surface the expr rather than
                    # computing the next fire time (that lives in the scheduler unit).
                    "next_run": f"{sched['kind']}: {sched['expr']}" if sched else "—",
                }
            )
        return out


@register_pane("agents", "Agents", order=10)
def build_agents_pane() -> AgentsPane:
    return AgentsPane()
