"""``synapse env set/list/rm`` — local env-var management (§4.10).

Lets an operator set env vars on this machine directly, without going through the Web UI.
Values are stored ONLY in the OS keyring (never echoed, never written to disk in
plaintext); only NAMES are reported upstream so the dashboard can show "set locally" and
``synapse env list`` can enumerate without unlocking the keychain.

  * ``synapse env set NAME=VALUE --agent <id>`` — store + report the NAME upstream
    (``env.local``). ``--shared`` uses the shared namespace; ``--plain`` marks a
    non-secret (still keyring-stored, just not registered with the redaction filter).
  * ``synapse env list --agent <id>``           — NAMES only (never values).
  * ``synapse env rm NAME --agent <id>``        — delete + report removal upstream.

Network/store work runs only when a command is invoked (no import-time side effects).
"""
from __future__ import annotations

import asyncio
from typing import Optional

import typer

from ..config import get_settings
from ..logging import get_logger
from ..paths import paths_for
from ..store import LocalStore
from ..uplink import CHANNEL_CONTROL, get_uplink
from ..vault import EnvVault

log = get_logger(__name__)

env_app = typer.Typer(
    name="env",
    help="Manage agent/shared environment variables (values stay in the OS keyring).",
    no_args_is_help=True,
    add_completion=False,
)


def _run_async(coro):
    """Run a coroutine to completion from the sync CLI (mirrors cmd_login).

    Normally there's no running loop (``asyncio.run``). Under a host loop (e.g. a test
    invoking the command inside pytest-asyncio) we run it on a worker thread so we don't
    trip ``asyncio.run() cannot be called from a running event loop``.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import threading

    box: list = []
    error: list[BaseException] = []

    def _worker() -> None:
        try:
            box.append(asyncio.run(coro))
        except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread
            error.append(exc)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    if error:
        raise error[0]
    return box[0] if box else None


async def _open_store() -> LocalStore:
    """Open a short-lived store on the durable db (its own loop, like cmd_login)."""
    paths = paths_for(get_settings())
    paths.ensure_layout()
    return await LocalStore(paths.db_path).connect()


def _parse_assignment(assignment: str) -> tuple[str, str]:
    if "=" not in assignment:
        typer.secho(
            "Expected NAME=VALUE (e.g. OPENAI_API_KEY=sk-...).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    name, value = assignment.split("=", 1)
    name = name.strip()
    if not name:
        typer.secho("Empty variable name.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    return name, value


@env_app.command("set")
def env_set(
    assignment: str = typer.Argument(..., metavar="NAME=VALUE", help="Variable to set."),
    agent: Optional[str] = typer.Option(
        None, "--agent", help="Agent id to scope the variable to."
    ),
    shared: bool = typer.Option(
        False, "--shared", help="Store in the shared namespace (all agents)."
    ),
    plain: bool = typer.Option(
        False, "--plain", help="Mark as non-secret (skip log redaction registration)."
    ),
) -> None:
    """Set an env var locally (value -> keyring; NAME reported upstream)."""
    if not shared and not agent:
        typer.secho("--agent <id> or --shared is required.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    name, value = _parse_assignment(assignment)

    async def _do() -> None:
        store = await _open_store()
        try:
            vault = EnvVault(store=store)
            await vault.store_value(
                name,
                value,
                agent_id=agent,
                shared=shared,
                origin="local",
                register_redaction=not plain,
            )
            # Report the NAME ONLY upstream so the Web UI shows it as "set locally".
            await get_uplink().send(
                "env.local",
                {"name": name, "agent_id": agent or ""},
                channel=CHANNEL_CONTROL,
            )
        finally:
            await store.close()

    _run_async(_do())
    scope = "shared" if shared else f"agent {agent}"
    typer.secho(f"Set {name} ({scope}).", fg=typer.colors.GREEN)


@env_app.command("list")
def env_list(
    agent: Optional[str] = typer.Option(
        None, "--agent", help="Agent id to list variables for."
    ),
    shared: bool = typer.Option(
        False, "--shared", help="List the shared namespace instead."
    ),
) -> None:
    """List env var NAMES (never values)."""
    if not shared and not agent:
        typer.secho("--agent <id> or --shared is required.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    async def _do() -> list[dict[str, str]]:
        store = await _open_store()
        try:
            vault = EnvVault(store=store)
            return await vault.list_names(agent_id=agent, shared=shared)
        finally:
            await store.close()

    rows = _run_async(_do()) or []
    if not rows:
        typer.echo("(no variables set)")
        return
    for row in rows:
        typer.echo(f"  {row['name']}  [{row.get('origin') or 'local'}]")


@env_app.command("rm")
def env_rm(
    name: str = typer.Argument(..., help="Variable name to remove."),
    agent: Optional[str] = typer.Option(
        None, "--agent", help="Agent id the variable is scoped to."
    ),
    shared: bool = typer.Option(
        False, "--shared", help="Remove from the shared namespace."
    ),
) -> None:
    """Remove an env var (keyring + metadata) and report removal upstream."""
    if not shared and not agent:
        typer.secho("--agent <id> or --shared is required.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    async def _do() -> None:
        store = await _open_store()
        try:
            vault = EnvVault(store=store)
            await vault.delete_value(name, agent_id=agent, shared=shared)
            # Tell the cloud the local var is gone so the dashboard stops showing it.
            await get_uplink().send(
                "env.local",
                {"name": name, "agent_id": agent or "", "removed": True},
                channel=CHANNEL_CONTROL,
            )
        finally:
            await store.close()

    _run_async(_do())
    typer.secho(f"Removed {name}.", fg=typer.colors.GREEN)


def register(app: typer.Typer) -> None:
    app.add_typer(env_app, name="env")
