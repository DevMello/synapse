"""Root CLI app — ``synapse``.

A Typer app that auto-discovers ``synapse_worker.cli.cmd_*`` modules. Each such module
exposes a ``register(app: typer.Typer) -> None`` that adds its commands or sub-typer
(``synapse login``, ``synapse env ...``, ``synapse daemon ...``, ``synapse tui``, ...).

The ``[project.scripts] synapse`` entry point points at the ``app`` object below, so the
discovery at import time runs before the CLI is invoked.
"""
from __future__ import annotations

import importlib
import pkgutil

import typer

from .. import __version__
from ..logging import get_logger

log = get_logger(__name__)

app = typer.Typer(
    name="synapse",
    help="Synapse worker daemon — run agents on your machine.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"synapse-worker {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    )
):
    """Synapse worker daemon root options."""


def discover_commands() -> None:
    """Import and mount every ``cli.cmd_*`` module that exposes ``register(app)``."""
    from .. import cli as cli_pkg

    for mod in pkgutil.iter_modules(cli_pkg.__path__):
        if not mod.name.startswith("cmd_"):
            continue
        name = f"{cli_pkg.__name__}.{mod.name}"
        try:
            module = importlib.import_module(name)
        except Exception:  # noqa: BLE001 - a broken/optional command shouldn't kill the CLI
            log.exception("failed to import CLI module %s", name)
            continue
        register = getattr(module, "register", None)
        if callable(register):
            try:
                register(app)
            except Exception:  # noqa: BLE001
                log.exception("failed to register CLI module %s", name)


discover_commands()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
