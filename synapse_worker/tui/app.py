"""Textual TUI shell + pane registry (§4.9).

The pane registry is import-light (no Textual import needed to *register* a pane), so
the TUI unit's panes can declare themselves via ``@register_pane`` and the rest of the
daemon never pulls in Textual. The actual Textual ``App`` is built lazily in
:func:`run_tui` so importing this module is cheap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(order=True)
class PaneSpec:
    order: int
    key: str = field(compare=False)
    title: str = field(compare=False)
    factory: Callable[[], Any] = field(compare=False)


_panes: list[PaneSpec] = []


def register_pane(key: str, title: str, *, order: int = 100):
    """Decorator: register a Textual widget factory as a named TUI pane.

        @register_pane("agents", "Agents", order=10)
        def build_agents_pane():
            return AgentsPane()
    """

    def deco(factory: Callable[[], Any]) -> Callable[[], Any]:
        _panes.append(PaneSpec(order=order, key=key, title=title, factory=factory))
        _panes.sort()
        return factory

    return deco


def registered_panes() -> list[PaneSpec]:
    return list(_panes)


def reset_panes() -> None:  # test helper
    _panes.clear()


def run_tui() -> None:
    """Launch the Textual dashboard. Imports Textual lazily."""
    # Ensure panes are discovered (the TUI unit registers them on import).
    try:
        import importlib
        import pkgutil

        from .. import tui as tui_pkg

        for mod in pkgutil.iter_modules(tui_pkg.__path__):
            if mod.name.startswith("panes"):
                importlib.import_module(f"{tui_pkg.__name__}.{mod.name}")
    except Exception:  # noqa: BLE001
        pass

    try:
        from .runtime_app import build_app  # provided by the TUI unit
    except Exception as exc:  # noqa: BLE001 - TUI unit not installed yet
        raise RuntimeError(
            "the Textual TUI is not available in this build (TUI unit not installed)"
        ) from exc

    build_app().run()
