"""``synapse init`` — interactive daemon setup, writes ~/.synapse/config.toml (§2).

Prompts for daemon name, tags, workdir, and max concurrent runs, then writes a
``[daemon]`` config.toml with owner-only perms (``paths.secure_write``) — the same table
``Settings`` reads. Every prompt is skippable via an option (``--name``/``--tags``/...)
and ``--yes`` accepts defaults non-interactively, so the command works in CI and service
installers as well as at a human terminal. No network, no import-time side effects.
"""
from __future__ import annotations

import socket
from typing import Optional

import typer

from ..config import get_settings
from ..logging import get_logger
from ..paths import paths_for, secure_write

log = get_logger(__name__)


def _toml_escape(value: str) -> str:
    # Minimal TOML basic-string escaping for the few fields we write.
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_config(
    name: str, tags: list[str], workdir: str, max_concurrent_runs: int
) -> str:
    tags_arr = ", ".join(f'"{_toml_escape(t)}"' for t in tags)
    lines = [
        "# Synapse worker config — written by `synapse init`.",
        "# Process env (SYNAPSE_*) overrides these values.",
        "[daemon]",
        f'daemon_name = "{_toml_escape(name)}"',
        f"daemon_tags = \"{_toml_escape(','.join(tags))}\"",
        f"tags = [{tags_arr}]",
        f'workdir = "{_toml_escape(workdir)}"',
        f"max_concurrent_runs = {int(max_concurrent_runs)}",
        "",
    ]
    return "\n".join(lines)


def init(
    name: Optional[str] = typer.Option(None, "--name", help="Daemon display name."),
    tags: Optional[str] = typer.Option(
        None, "--tags", help="Comma-separated tags (e.g. gpu,prod)."
    ),
    workdir: Optional[str] = typer.Option(
        None, "--workdir", help="Default working directory for agent runs."
    ),
    max_concurrent_runs: Optional[int] = typer.Option(
        None, "--max-concurrent-runs", help="Maximum simultaneous agent runs."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Accept defaults without prompting (non-interactive)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing config.toml."
    ),
) -> None:
    """Set up this daemon's local config (~/.synapse/config.toml)."""
    settings = get_settings()
    paths = paths_for(settings)

    if paths.config_path.exists() and not force:
        typer.secho(
            f"{paths.config_path} already exists (use --force to overwrite).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)

    # Defaults: option > existing setting > sensible fallback.
    default_name = name or settings.daemon_name or socket.gethostname()
    default_tags = tags if tags is not None else settings.daemon_tags
    default_workdir = workdir or settings.workdir or str(settings.home_dir / "work")
    default_mcr = (
        max_concurrent_runs
        if max_concurrent_runs is not None
        else settings.max_concurrent_runs
    )

    if yes:
        final_name = default_name
        final_tags = default_tags
        final_workdir = default_workdir
        final_mcr = default_mcr
    else:
        final_name = name or typer.prompt("Daemon name", default=default_name)
        final_tags = (
            tags
            if tags is not None
            else typer.prompt("Tags (comma-separated)", default=default_tags or "")
        )
        final_workdir = workdir or typer.prompt("Working directory", default=default_workdir)
        final_mcr = (
            max_concurrent_runs
            if max_concurrent_runs is not None
            else typer.prompt("Max concurrent runs", default=default_mcr, type=int)
        )

    tag_list = [t.strip() for t in str(final_tags).split(",") if t.strip()]
    content = _render_config(final_name, tag_list, final_workdir, int(final_mcr))

    # secure_write creates ~/.synapse 0700 and the file 0600 from the start.
    secure_write(paths.config_path, content)

    typer.secho(f"Wrote {paths.config_path}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  name:                {final_name}")
    typer.echo(f"  tags:                {', '.join(tag_list) or '(none)'}")
    typer.echo(f"  workdir:             {final_workdir}")
    typer.echo(f"  max_concurrent_runs: {final_mcr}")


def register(app: typer.Typer) -> None:
    app.command("init")(init)
