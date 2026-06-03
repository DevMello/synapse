"""``synapse daemon ...`` — run the daemon and manage it as a host service (§2).

  * ``synapse daemon run``     — actually RUN the daemon (blocking async loop). This is
    the entry the installed service unit invokes.
  * ``synapse daemon install`` — generate + register the native service unit for this OS
    (systemd / launchd / Windows Service). ``--system`` installs a system-wide unit.
  * ``synapse daemon start``   — start the installed service.
  * ``synapse daemon stop``    — stop it.
  * ``synapse daemon status``  — query its status.

All work runs inside the command (no import-time side effects). The service-registration
ops delegate to :mod:`synapse_worker.service.manager`; ``--dry-run`` previews exactly what
would be written/registered without mutating the host.
"""
from __future__ import annotations

import typer

from ..logging import get_logger
from ..service import manager

log = get_logger(__name__)

daemon_app = typer.Typer(
    name="daemon",
    help="Run the worker daemon and manage it as a host service.",
    no_args_is_help=True,
)


@daemon_app.command("run")
def run() -> None:
    """Run the daemon in the foreground (blocks until stopped).

    This is what the installed service unit launches. It opens durable state, starts the
    connection/scheduler/heartbeat services, and blocks until cancelled.
    """
    import asyncio

    from ..app import run_daemon

    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        typer.echo("daemon stopped.")


@daemon_app.command("install")
def install(
    system: bool = typer.Option(
        False, "--system", help="Install a system-wide unit instead of a per-user one."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print what would be registered without touching the host."
    ),
) -> None:
    """Generate and register the native service unit for this OS (§2)."""
    plan = manager.install(system=system, dry_run=dry_run)
    typer.secho(
        f"[{plan.platform}] {'(dry-run) ' if plan.dry_run else ''}service install",
        fg=typer.colors.CYAN,
        bold=True,
    )
    if plan.target_path is not None:
        typer.echo(f"  unit path: {plan.target_path}")
    if plan.content:
        typer.echo("  --- rendered unit ---")
        for line in plan.content.splitlines():
            typer.echo(f"  {line}")
    if plan.commands:
        typer.echo("  --- commands ---")
        for cmd in plan.commands:
            typer.echo(f"  $ {' '.join(cmd)}")
    typer.echo(f"  {plan.detail}")
    if not plan.dry_run and not plan.ran:
        raise typer.Exit(code=1)


@daemon_app.command("start")
def start(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without running."),
) -> None:
    """Start the installed service."""
    _emit(manager.start(dry_run=dry_run))


@daemon_app.command("stop")
def stop(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without running."),
) -> None:
    """Stop the installed service."""
    _emit(manager.stop(dry_run=dry_run))


@daemon_app.command("status")
def status(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without running."),
) -> None:
    """Query the installed service's status."""
    _emit(manager.status(dry_run=dry_run))


def _emit(plan: manager.ServicePlan) -> None:
    typer.secho(f"[{plan.platform}] daemon {plan.action}", fg=typer.colors.CYAN, bold=True)
    for cmd in plan.commands:
        typer.echo(f"  $ {' '.join(cmd)}")
    typer.echo(f"  {plan.detail}")
    if not plan.dry_run and not plan.ran:
        raise typer.Exit(code=1)


def register(app: typer.Typer) -> None:
    app.add_typer(daemon_app, name="daemon")
