"""Command handler drop-in package.

Each feature unit adds a module here (e.g. ``agents.py``, ``env.py``, ``hitl.py``) that
registers handlers with ``@on_command("<type>")``. ``app.build_daemon`` auto-imports
every module in this package at startup, so handlers wire themselves in without anyone
editing ``app.py`` or ``router.py``.
"""
from __future__ import annotations
