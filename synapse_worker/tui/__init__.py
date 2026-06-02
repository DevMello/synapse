"""Textual TUI package.

The app shell + pane registry live in :mod:`tui.app`. The TUI unit adds concrete panes
(Agents/Live/Logs/Approvals/Daemon) under ``tui/panes/`` and registers them with
``@register_pane``.
"""
from __future__ import annotations
