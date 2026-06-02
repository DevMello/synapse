"""Approvals pane (§4.9 HITL).

Lists pending HITL gates (``hitl_state`` rows with ``status='pending'``) and lets the
operator approve/deny the highlighted one with a keystroke. Resolving a gate updates the
row (status + decision + actor + resolved_at) and publishes a ``hitl`` event so other
panes/subscribers react. If the dedicated gatekeeper (:mod:`synapse_worker.hitl`) is
present we hand off to it; otherwise the row update IS the resolution (best-effort, per
the unit spec).
"""
from __future__ import annotations

import time
from typing import Any, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable, Label

from ..app import register_pane


class ApprovalsPane(Container):
    """Pending HITL gates with approve/deny keybindings."""

    DEFAULT_CSS = """
    ApprovalsPane { height: 1fr; }
    ApprovalsPane .empty { color: $text-muted; padding: 1 2; }
    """

    # These bindings are active while the pane (and its table) holds focus.
    BINDINGS = [
        Binding("a", "approve", "Approve"),
        Binding("d", "deny", "Deny"),
    ]

    def compose(self) -> ComposeResult:
        yield Label("No pending approvals.", classes="empty", id="approvals-empty")
        table = DataTable(id="approvals-table", zebra_stripes=True, cursor_type="row")
        table.display = False
        yield table

    async def on_mount(self) -> None:
        table = self.query_one("#approvals-table", DataTable)
        table.add_columns("ID", "Run", "Action", "Requested")
        await self.refresh_rows()

    async def refresh_rows(self) -> None:
        rows = await self._load()
        table = self.query_one("#approvals-table", DataTable)
        empty = self.query_one("#approvals-empty", Label)
        table.clear()
        if not rows:
            table.display = False
            empty.display = True
            return
        empty.display = False
        table.display = True
        for r in rows:
            # The row key is the hitl_state id so action handlers can resolve it.
            table.add_row(
                r["id"],
                (r.get("run_id") or "—"),
                (r.get("action") or "—"),
                _short_ts(r.get("created_at")),
                key=r["id"],
            )

    async def _load(self) -> list[dict[str, Any]]:
        store = _try_store()
        if store is None:
            return []
        try:
            return await store.fetchall(
                "SELECT id, run_id, action, created_at FROM hitl_state"
                " WHERE status='pending' ORDER BY created_at",
            )
        except Exception:  # noqa: BLE001
            return []

    # ── keybinding actions ────────────────────────────────────────────────
    async def action_approve(self) -> None:
        await self._resolve("approved")

    async def action_deny(self) -> None:
        await self._resolve("denied")

    async def _resolve(self, decision: str) -> None:
        gate_id = self._selected_id()
        if gate_id is None:
            return
        store = _try_store()
        if store is None:
            return

        # Best-effort hand-off to the gatekeeper if this build ships one.
        handled = await _delegate_to_gatekeeper(gate_id, decision)
        if not handled:
            try:
                await store.execute(
                    "UPDATE hitl_state SET status=?, decision=?, actor=?, resolved_at=?"
                    " WHERE id=?",
                    (decision, decision, "tui", time.time(), gate_id),
                )
            except Exception:  # noqa: BLE001
                return

        await _publish_resolution(gate_id, decision)
        await self.refresh_rows()

    def _selected_id(self) -> Optional[str]:
        table = self.query_one("#approvals-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:  # noqa: BLE001 - no selection
            return None
        return row_key.value


def _short_ts(ts: Any) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (ValueError, OverflowError, OSError, TypeError):
        return "—"


def _try_store():
    try:
        from ...store import get_store

        return get_store()
    except Exception:  # noqa: BLE001 - store not initialised
        return None


async def _delegate_to_gatekeeper(gate_id: str, decision: str) -> bool:
    """Hand off to ``synapse_worker.hitl`` if it exists. Returns True if it handled it."""
    try:
        from ... import hitl  # type: ignore
    except Exception:  # noqa: BLE001 - no gatekeeper in this build
        return False
    resolver = getattr(hitl, "resolve", None) or getattr(hitl, "resolve_gate", None)
    if not callable(resolver):
        return False
    try:
        result = resolver(gate_id, decision)
        if hasattr(result, "__await__"):
            await result
        return True
    except Exception:  # noqa: BLE001 - fall back to the direct row update
        return False


async def _publish_resolution(gate_id: str, decision: str) -> None:
    try:
        from ...events import Event, get_event_bus

        await get_event_bus().publish(
            Event(kind="hitl", data={"id": gate_id, "decision": decision})
        )
    except Exception:  # noqa: BLE001 - publishing is advisory
        pass


@register_pane("approvals", "Approvals", order=40)
def build_approvals_pane() -> ApprovalsPane:
    return ApprovalsPane()
