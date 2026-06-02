"""``synapse agent ...`` — agent-tier capability selection (§4.11).

The *agent* tier of the two-tier model: choose which of the daemon's already-provisioned
capabilities a given agent may use. A lightweight per-agent toggle — no provisioning, no
teardown. The Ruleset Engine consults the capability registry at run time, so attaching is
what makes a capability callable by that agent.

  * ``synapse agent attach <cap> --agent <id>`` — include a capability for the agent.
  * ``synapse agent detach <cap> --agent <id>`` — exclude it (capability stays provisioned).
  * ``synapse agent capabilities --agent <id>`` — what the agent currently has attached,
    including the auto-attached built-in defaults.

Attach/detach mutate BOTH the in-memory capability registry and the durable
``agent_capabilities`` table so the selection survives a restart.
"""
from __future__ import annotations

import asyncio
import time

import typer

from ..capabilities.registry import (
    DEFAULT_CAPABILITIES,
    get_capability_registry,
)
from ..config import get_settings
from ..logging import get_logger
from ..paths import paths_for
from ..store import LocalStore, get_store, set_store

log = get_logger(__name__)

agent_app = typer.Typer(
    name="agent",
    help="Select which provisioned capabilities each agent may use (agent tier).",
    no_args_is_help=True,
)


def _run_async(coro):
    """Run a coroutine to completion from the sync CLI (own loop, even under pytest)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import threading

    box: dict[str, object] = {}

    def _worker() -> None:
        try:
            box["result"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread
            box["error"] = exc

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box.get("result")


async def _with_store(coro_factory):
    """Open a short-lived store as the singleton, run, then close (WAL-safe)."""
    paths = paths_for(get_settings())
    paths.ensure_layout()
    store = await LocalStore(paths.db_path).connect()
    set_store(store)
    try:
        return await coro_factory()
    finally:
        await store.close()


@agent_app.command("attach")
def attach(
    capability: str = typer.Argument(..., help="Capability name to attach."),
    agent: str = typer.Option(..., "--agent", help="Agent id to attach it to."),
) -> None:
    """Include a provisioned capability for an agent."""

    async def _do():
        # The registry attaches even if not yet marked available — but warn the operator if
        # the capability isn't provisioned/default, since it won't be callable until it is.
        reg = get_capability_registry()
        if capability not in DEFAULT_CAPABILITIES and not reg.is_available(capability):
            row = await get_store().fetchone(
                "SELECT id FROM capabilities WHERE name=?", (capability,)
            )
            if row is None:
                return False
        reg.attach(agent, capability)
        await get_store().execute(
            "INSERT INTO agent_capabilities (agent_id, capability, enabled, updated_at)"
            " VALUES (?,?,1,?)"
            " ON CONFLICT(agent_id, capability) DO UPDATE SET enabled=1,"
            " updated_at=excluded.updated_at",
            (agent, capability, time.time()),
        )
        return True

    ok = _run_async(_with_store(_do))
    if not ok:
        typer.secho(
            f"Capability {capability!r} is not provisioned on this daemon "
            f"(run `synapse plugin install {capability}` first).",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)
    typer.secho(f"Attached {capability} to agent {agent}.", fg=typer.colors.GREEN, bold=True)


@agent_app.command("detach")
def detach(
    capability: str = typer.Argument(..., help="Capability name to detach."),
    agent: str = typer.Option(..., "--agent", help="Agent id to detach it from."),
) -> None:
    """Exclude a capability from an agent (no teardown)."""

    async def _do():
        get_capability_registry().detach(agent, capability)
        await get_store().execute(
            "DELETE FROM agent_capabilities WHERE agent_id=? AND capability=?",
            (agent, capability),
        )

    _run_async(_with_store(_do))
    typer.secho(f"Detached {capability} from agent {agent}.", fg=typer.colors.GREEN, bold=True)


@agent_app.command("capabilities")
def capabilities(
    agent: str = typer.Option(..., "--agent", help="Agent id to inspect."),
) -> None:
    """Show the capabilities currently attached to an agent (incl. defaults)."""

    async def _do():
        # Rehydrate the registry from the durable table so the CLI reflects persisted state
        # even though it didn't run the attach in this process.
        rows = await get_store().fetchall(
            "SELECT capability FROM agent_capabilities WHERE agent_id=? AND enabled=1",
            (agent,),
        )
        reg = get_capability_registry()
        for r in rows:
            reg.attach(agent, r["capability"])
        return sorted(reg.attached(agent))

    attached = _run_async(_with_store(_do)) or []
    if not attached:
        typer.echo(f"Agent {agent} has no capabilities attached.")
        return
    typer.echo(f"Capabilities attached to {agent}:")
    for name in attached:
        tag = " (default)" if name in DEFAULT_CAPABILITIES else ""
        typer.echo(f"  {name}{tag}")


def register(app: typer.Typer) -> None:
    app.add_typer(agent_app, name="agent")
