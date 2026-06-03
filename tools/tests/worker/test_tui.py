"""Tests for the Textual TUI unit (§4.9).

Self-contained and headless: every test drives the app through Textual's
``App.run_test()`` pilot — no real terminal, no network. The ``store`` fixture provides a
connected :class:`LocalStore` installed as the singleton so panes can read live rows.
"""
from __future__ import annotations

import time

import pytest

# asyncio_mode = "auto" (see pyproject) — async tests run without an explicit marker.
from synapse_worker.events import Event, get_event_bus, reset_event_bus
from synapse_worker.tui import panes as _panes  # noqa: F401 - registers panes on import
from synapse_worker.tui.app import registered_panes
from synapse_worker.tui.runtime_app import build_app


@pytest.fixture(autouse=True)
def _fresh_bus():
    # The bus is a module singleton not reset by the shared conftest; give each test a
    # clean one so subscriber counts / queued events don't leak across tests.
    reset_event_bus()
    yield
    reset_event_bus()


def test_panes_registered() -> None:
    keys = {p.key for p in registered_panes()}
    assert {"agents", "live", "logs", "approvals", "daemon"} <= keys


async def test_all_panes_mount(store) -> None:
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import TabPane

        titles = {tp.id for tp in app.query(TabPane)}
        assert {
            "tab-agents",
            "tab-live",
            "tab-logs",
            "tab-approvals",
            "tab-daemon",
        } <= titles


async def test_live_pane_renders_published_event(store) -> None:
    from textual.widgets import RichLog, TabbedContent

    from synapse_worker.tui.panes.live import LivePane

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Activate the Live tab so its RichLog is laid out (an inactive TabPane's widget
        # has zero size and never populates `.lines`).
        app.query_one(TabbedContent).active = "tab-live"
        await pilot.pause()
        # Publish a trace event on the same loop the app is running on.
        await get_event_bus().publish(
            Event(kind="trace", data={"text": "hello-trace-line"}, run_id="run12345")
        )
        await pilot.pause()
        await pilot.pause()

        live = app.query_one(LivePane)
        log = live.query_one(RichLog)
        rendered = "\n".join(str(line) for line in log.lines)
        assert "hello-trace-line" in rendered


async def test_approvals_lists_pending_row(store) -> None:
    await store.execute(
        "INSERT INTO hitl_state (id, run_id, status, action, created_at)"
        " VALUES (?,?,?,?,?)",
        ("gate-1", "run-1", "pending", "send_email", time.time()),
    )
    from synapse_worker.tui.panes.approvals import ApprovalsPane

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(ApprovalsPane)
        await pane.refresh_rows()
        await pilot.pause()
        from textual.widgets import DataTable

        table = pane.query_one(DataTable)
        assert table.row_count == 1


async def test_approve_resolves_pending_row(store) -> None:
    await store.execute(
        "INSERT INTO hitl_state (id, run_id, status, action, created_at)"
        " VALUES (?,?,?,?,?)",
        ("gate-2", "run-2", "pending", "deploy", time.time()),
    )
    from synapse_worker.tui.panes.approvals import ApprovalsPane

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(ApprovalsPane)
        await pane.refresh_rows()
        await pilot.pause()
        # Resolve the highlighted gate directly via the action handler.
        await pane.action_approve()
        await pilot.pause()

    row = await store.fetchone(
        "SELECT status, actor FROM hitl_state WHERE id=?", ("gate-2",)
    )
    assert row is not None
    assert row["status"] == "approved"
    assert row["actor"] == "tui"


def test_tui_command_registered() -> None:
    from typer.testing import CliRunner

    from synapse_worker.cli.main import app

    result = CliRunner().invoke(app, ["tui", "--help"])
    assert result.exit_code == 0
