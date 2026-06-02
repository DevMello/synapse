"""CLI package (Typer).

Each feature unit adds a ``cmd_*.py`` module here exposing ``register(app)``; the root
app in :mod:`cli.main` auto-discovers and mounts them, so nobody edits ``main.py``.
"""
from __future__ import annotations
