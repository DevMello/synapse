"""``synapse plugin ...`` — daemon-tier capability management (§4.11).

The *daemon* tier of the two-tier model: provision/enable a capability on THIS host. None
of these commands attach anything to an agent (that's ``synapse agent attach``).

  * ``synapse plugin search <q>`` — browse a local catalog stub (no network).
  * ``synapse plugin install <name|path>`` — provision on the daemon. A local path is read
    via ``PluginManifest.from_toml`` (its ``plugin.toml``); a bare name installs a catalog
    entry. Both run the same in-process provisioning the cloud command uses.
  * ``synapse plugin list`` — capabilities available on this daemon + their status.
  * ``synapse plugin remove <name>`` — tear down on the daemon (detaches everywhere).

All work runs inside the command (no import-time side effects), and the async provisioning
runs via a short-lived event loop bound to a tmp store connection — the CLI doesn't share
the daemon's running store.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Optional

import typer

from ..config import get_settings
from ..logging import get_logger
from ..paths import paths_for
from ..plugins.base import PluginManifest
from ..plugins.runtime import get_plugin_runtime
from ..store import LocalStore, set_store

log = get_logger(__name__)

plugin_app = typer.Typer(
    name="plugin",
    help="Manage capability packs provisioned on this daemon (daemon tier).",
    no_args_is_help=True,
)

# A tiny offline catalog so ``search`` returns something useful without a network call.
# The real catalog lives in the cloud marketplace; this is a local convenience stub.
_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("browser-use", "composite", "Playwright-driven browser automation"),
    ("terminal-use", "composite", "Sandboxed shell tool with ruleset gating"),
    ("file-explorer", "script", "Scoped filesystem browse/read/write tools"),
    ("github", "mcp", "GitHub MCP server"),
    ("slack", "mcp", "Slack MCP server"),
    ("postgres", "mcp", "Postgres MCP server"),
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
    """Open a short-lived store, install it as the singleton, run, then close.

    Provisioning + listing touch the ``capabilities`` table via ``get_store()``; the CLI
    isn't the daemon, so it opens its own connection on this loop (WAL keeps it safe).
    """
    paths = paths_for(get_settings())
    paths.ensure_layout()
    store = await LocalStore(paths.db_path).connect()
    set_store(store)
    try:
        return await coro_factory()
    finally:
        await store.close()


@plugin_app.command("search")
def search(query: str = typer.Argument("", help="Search term (matches name/description).")) -> None:
    """Browse the (local) plugin catalog."""
    q = query.strip().lower()
    hits = [
        (name, kind, desc)
        for (name, kind, desc) in _CATALOG
        if not q or q in name.lower() or q in desc.lower()
    ]
    if not hits:
        typer.echo(f"No catalog matches for {query!r}.")
        return
    for name, kind, desc in hits:
        typer.echo(f"  {name:<16} {kind:<10} {desc}")


@plugin_app.command("install")
def install(
    target: str = typer.Argument(..., help="Plugin name (catalog) or path to a plugin dir/plugin.toml."),
) -> None:
    """Provision a capability on this daemon (NOT attached to any agent yet)."""
    manifest, kind = _load_install_target(target)

    cap_id = f"cap_{uuid.uuid4().hex[:12]}"
    exposed = [t.name for t in manifest.provides_tool] + [m.name for m in manifest.provides_mcp]
    endpoint = manifest.provides_mcp[0].command if manifest.provides_mcp else None

    async def _do():
        return await get_plugin_runtime().install(
            daemon_capability_id=cap_id,
            kind=kind,
            manifest=manifest,
            exposed_tools=exposed,
            endpoint=endpoint,
        )

    result = _run_async(_with_store(_do))
    if result is not None and result.status == "ready":
        typer.secho(
            f"Provisioned {manifest.name} ({kind}) -> {cap_id}",
            fg=typer.colors.GREEN,
            bold=True,
        )
    else:
        err = getattr(result, "error", None) or "unknown error"
        typer.secho(f"Failed to provision {manifest.name}: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@plugin_app.command("list")
def list_() -> None:
    """List capabilities available on this daemon and their status."""

    async def _do():
        from ..store import get_store

        return await get_store().fetchall(
            "SELECT id, name, kind, status FROM capabilities ORDER BY name"
        )

    rows = _run_async(_with_store(_do)) or []
    if not rows:
        typer.echo("No capabilities provisioned on this daemon.")
        return
    typer.echo(f"{'NAME':<18}{'KIND':<12}{'STATUS':<12}ID")
    for r in rows:
        typer.echo(
            f"{str(r['name']):<18}{str(r['kind']):<12}{str(r['status']):<12}{r['id']}"
        )


@plugin_app.command("remove")
def remove(name: str = typer.Argument(..., help="Capability name to tear down.")) -> None:
    """Tear down a capability on this daemon (detaches it from every agent)."""

    async def _do():
        from ..store import get_store

        row = await get_store().fetchone(
            "SELECT id FROM capabilities WHERE name=?", (name,)
        )
        if row is None:
            return None
        await get_plugin_runtime().remove(row["id"])
        return row["id"]

    cap_id = _run_async(_with_store(_do))
    if cap_id is None:
        typer.secho(f"No capability named {name!r} on this daemon.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"Removed {name} ({cap_id}).", fg=typer.colors.GREEN, bold=True)


def _load_install_target(target: str) -> tuple[PluginManifest, str]:
    """Resolve an install target to a (manifest, kind).

    A path (to a dir containing ``plugin.toml`` or to the file itself) is parsed via
    ``PluginManifest.from_toml``. Otherwise the target is a catalog name and we synthesize a
    minimal manifest from the catalog entry (no network — the real fetch is cloud-side).
    """
    path = Path(target)
    toml_path: Optional[Path] = None
    if path.is_dir() and (path / "plugin.toml").is_file():
        toml_path = path / "plugin.toml"
    elif path.is_file() and path.name == "plugin.toml":
        toml_path = path
    elif path.suffix == ".toml" and path.is_file():
        toml_path = path

    if toml_path is not None:
        manifest = PluginManifest.from_toml(toml_path.read_text(encoding="utf-8"))
        return manifest, manifest.kind

    # Catalog name → synthesize a minimal manifest carrying the catalog's kind.
    entry = next((e for e in _CATALOG if e[0] == target), None)
    kind = entry[1] if entry else "mcp"
    data = {"plugin": {"id": target, "name": target, "version": "0.0.0", "kind": kind}}
    return PluginManifest.from_dict(data), kind


def register(app: typer.Typer) -> None:
    app.add_typer(plugin_app, name="plugin")
