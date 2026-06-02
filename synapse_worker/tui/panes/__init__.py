"""Concrete TUI panes (§4.9).

Importing this package imports every pane module, which runs each ``@register_pane``
decorator so the shell can mount them. The foundation's ``run_tui`` discovers panes by
importing modules whose name starts with ``panes`` — importing this package therefore
pulls in the whole set.

The submodules are imported for their *registration side effect*; nothing here is meant
to be imported by name.
"""
from __future__ import annotations

# WHY: importing each module triggers its @register_pane decorator. Import order is
# irrelevant — the registry sorts PaneSpecs by their declared ``order``.
from . import agents, approvals, daemon, live, logs  # noqa: F401
