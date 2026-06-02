"""``synapse tui`` — open the live terminal dashboard (§4.9).

Thin wrapper: it defers to :func:`synapse_worker.tui.app.run_tui`, which discovers the
panes and builds the Textual app. Textual is imported lazily inside ``run_tui`` so adding
this command costs nothing at CLI import time.
"""
from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def tui() -> None:
        """Open the live terminal dashboard."""
        from synapse_worker.tui.app import run_tui

        run_tui()
