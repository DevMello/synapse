"""``synapse version`` + ``synapse health`` (§6, §7).

Two read-only, offline commands:

  * ``synapse version`` — prints ``synapse-worker {__version__}`` (the packaged version).
  * ``synapse health``  — prints a local :func:`synapse_worker.health.collect` snapshot as
    readable text (the same fields the daemon's health service ships upstream), so an
    operator can sanity-check resource sampling without a running daemon or cloud link.

Both are pure functions of the local process: no network, no store, no import-time side
effects. Mounted by the root CLI's ``cmd_*`` auto-discovery via :func:`register`.
"""
from __future__ import annotations

import typer

from .. import __version__
from .. import health as _health


def version() -> None:
    """Print the worker package version."""
    typer.echo(f"synapse-worker {__version__}")


def health() -> None:
    """Print a local health snapshot (CPU, mem, disk, uptime, version)."""
    snap = _health.collect()
    typer.echo(f"synapse-worker {snap.version}")
    typer.echo(f"  uptime_seconds: {snap.uptime_seconds}")
    typer.echo(f"  cpu_percent:    {snap.cpu_percent}")
    typer.echo(f"  mem_mb:         {snap.mem_mb}")
    typer.echo(f"  disk_percent:   {snap.disk_percent}")
    typer.echo(f"  active_runs:    {snap.active_runs}")
    typer.echo(f"  queue_depth:    {snap.queue_depth}")


def register(app: typer.Typer) -> None:
    app.command("version")(version)
    app.command("health")(health)
