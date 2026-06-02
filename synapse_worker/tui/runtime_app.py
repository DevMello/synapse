"""Textual ``App`` assembly (§4.9).

The foundation's :func:`synapse_worker.tui.app.run_tui` imports the panes (running their
``@register_pane`` decorators) and then calls :func:`build_app` here. We construct a
single ``TabbedContent`` shell, one tab per registered pane in ``order``, with a header,
footer, and a quit binding.

All data loading happens inside each pane's ``on_mount``/workers — ``build_app`` itself
does no I/O, so importing/constructing the app is cheap and side-effect free.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from .app import PaneSpec, registered_panes


class SynapseTUI(App):
    """The live terminal dashboard for the worker daemon."""

    TITLE = "Synapse Worker"

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self, panes: list[PaneSpec]) -> None:
        super().__init__()
        # Snapshot the registry at construction so the layout is stable for this app
        # instance even if more panes register later.
        self._panes = panes

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            for spec in self._panes:
                # One TabPane per registered pane; the factory builds the widget. A
                # factory that raises shouldn't sink the whole dashboard.
                with TabPane(spec.title, id=f"tab-{spec.key}"):
                    try:
                        yield spec.factory()
                    except Exception:  # noqa: BLE001
                        from textual.widgets import Static

                        yield Static(f"{spec.title} pane failed to load")
        yield Footer()


def build_app() -> App:
    """Construct the dashboard App from the registered panes.

    Panes are expected to already be imported (the foundation's ``run_tui`` does that);
    we also import the panes package here defensively so direct callers/tests of
    ``build_app`` get the full set without a separate import step.
    """
    try:
        from . import panes  # noqa: F401 - registration side effect
    except Exception:  # noqa: BLE001 - a broken pane module shouldn't break the shell
        pass
    return SynapseTUI(registered_panes())
