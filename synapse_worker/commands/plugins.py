"""Plugin / capability command handlers (cloud → daemon, §4.11).

``app.build_daemon`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one registers the five ``@on_command`` handlers that drive the two-tier capability
model:

  * ``plugin.install`` / ``mcp.configure`` — **daemon tier**: provision a capability on this
    host (its venv/process/sandbox). Reports ``capability.status`` upstream as it goes
    ``installing → ready | failed``.
  * ``plugin.remove`` — **daemon tier** teardown: stop the process, rmtree the venv, drop it
    from every registry + table (detaches from ALL agents).
  * ``capability.attach`` / ``capability.detach`` — **agent tier**: a lightweight per-agent
    toggle over an already-provisioned capability. The Ruleset Engine (Unit 8) consults the
    capability registry, so attaching is what makes the capability callable by the agent.

Every handler is tolerant of payload shape: the cloud is the wire source of truth, but a
missing/renamed field must degrade gracefully rather than crash the control loop.

Authoritative payloads (see ``synapse_cloud/routers/capabilities.py``)::

    plugin.install / mcp.configure:
      {"daemon_capability_id", "kind", "plugin_id", "plugin_version",
       "exposed_tools": [...], "endpoint", "args": {...}}
    plugin.remove:      {"daemon_capability_id"}
    capability.attach:  {"agent_id"?, "daemon_capability_id"}
    capability.detach:  {"agent_id"?, "daemon_capability_id"}
"""
from __future__ import annotations

import time
from typing import Any, Optional

from ..logging import get_logger
from ..plugins.base import PluginManifest
from ..plugins.runtime import get_plugin_runtime
from ..router import CommandContext, on_command
from ..ruleset.base import get_ruleset
from ..store import get_store
from ..uplink import CHANNEL_CONTROL, get_uplink

log = get_logger(__name__)

# capability name -> its declared [permissions] block, captured at provision time so
# capability.attach can apply them to the TARGET agent's ruleset policy (never global).
_PERMISSIONS: dict[str, dict[str, Any]] = {}


# ── daemon tier: provision ────────────────────────────────────────────────────
@on_command("plugin.install")
async def handle_plugin_install(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Provision a composite/script/workspace capability on this daemon."""
    await _provision(payload)


@on_command("mcp.configure")
async def handle_mcp_configure(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Register/provision an ``mcp`` capability (a spawnable MCP server) on this daemon.

    Shares the provisioning path with ``plugin.install``; the kind drives the difference
    (mcp → register a server spec; venv kinds → build a venv).
    """
    payload = dict(payload)
    payload.setdefault("kind", "mcp")
    await _provision(payload)


async def _provision(payload: dict[str, Any]) -> None:
    cap_id = payload.get("daemon_capability_id") or payload.get("id")
    if not cap_id:
        log.warning("plugin.install: missing daemon_capability_id; ignoring")
        return

    kind = str(payload.get("kind") or "mcp")
    exposed_tools = _str_list(payload.get("exposed_tools"))
    endpoint = payload.get("endpoint") if isinstance(payload.get("endpoint"), str) else None
    args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    checksum = payload.get("checksum") if isinstance(payload.get("checksum"), str) else None

    manifest = _resolve_manifest(payload, kind=kind, endpoint=endpoint, args=args)

    # Report "installing" upstream immediately so the Web UI shows progress before the
    # (possibly slow) provisioning runs.
    await _emit_status(cap_id, "installing", exposed_tools)

    result = await get_plugin_runtime().install(
        daemon_capability_id=cap_id,
        kind=kind,
        manifest=manifest,
        exposed_tools=exposed_tools,
        endpoint=endpoint,
        args=args,
        checksum=checksum,
    )

    # Stash the pack's declared permissions so capability.attach can apply them to the
    # TARGET agent's policy (§4.11 step 5). We deliberately do NOT mutate any global/default
    # policy here — permissions are per-agent and applied only when the pack is attached.
    perms = manifest.permissions if isinstance(manifest.permissions, dict) else {}
    if perms:
        _PERMISSIONS[manifest.name] = perms

    await _emit_status(cap_id, result.status, result.exposed_tools)
    log.info(
        "plugin.install %s: %s (%s)", cap_id, result.status, result.error or "ok"
    )


# ── daemon tier: teardown ─────────────────────────────────────────────────────
@on_command("plugin.remove")
async def handle_plugin_remove(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Tear a capability down on this daemon (detaches it from EVERY agent)."""
    cap_id = payload.get("daemon_capability_id") or payload.get("id")
    if not cap_id:
        log.warning("plugin.remove: missing daemon_capability_id; ignoring")
        return
    name = await get_plugin_runtime().remove(cap_id)
    log.info("plugin.remove %s: removed (%s)", cap_id, name or "unknown")


# ── agent tier: attach / detach ───────────────────────────────────────────────
@on_command("capability.attach")
async def handle_capability_attach(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Attach an already-provisioned capability to one agent (makes it callable)."""
    agent_id, cap_id = _attach_targets(ctx, payload)
    if not agent_id or not cap_id:
        log.warning("capability.attach: missing agent_id/capability; ignoring")
        return

    name = await _cap_name(cap_id)
    from ..capabilities.registry import get_capability_registry

    # Attach under the capability *name* (what the Ruleset Engine checks); fall back to the
    # raw id if we can't resolve a name (still toggles the per-agent set).
    cap_name = name or cap_id
    get_capability_registry().attach(agent_id, cap_name)
    await _upsert_attachment(agent_id, cap_name, enabled=True)
    # Apply the pack's declared permissions to THIS agent's policy (§4.11 step 5).
    _apply_permissions(agent_id, cap_name)
    log.info("capability.attach: agent %s -> %s", agent_id, cap_name)


@on_command("capability.detach")
async def handle_capability_detach(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Detach a capability from one agent. No teardown — the pack stays provisioned."""
    agent_id, cap_id = _attach_targets(ctx, payload)
    if not agent_id or not cap_id:
        log.warning("capability.detach: missing agent_id/capability; ignoring")
        return

    name = await _cap_name(cap_id)
    from ..capabilities.registry import get_capability_registry

    get_capability_registry().detach(agent_id, name or cap_id)
    try:
        await get_store().execute(
            "DELETE FROM agent_capabilities WHERE agent_id=? AND capability=?",
            (agent_id, name or cap_id),
        )
    except Exception:  # noqa: BLE001
        log.exception("capability.detach: failed to delete row")
    log.info("capability.detach: agent %s -/-> %s", agent_id, name or cap_id)


# ── helpers ───────────────────────────────────────────────────────────────────
def _str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _resolve_manifest(
    payload: dict[str, Any],
    *,
    kind: str,
    endpoint: Optional[str],
    args: dict[str, Any],
) -> PluginManifest:
    """Get a :class:`PluginManifest` for this provision request.

    The cloud sends provisioning metadata, not always a full manifest, so we either parse a
    supplied manifest (``args.manifest`` as a dict or ``args.plugin_toml`` as TOML text) or
    synthesize a minimal-but-valid one from the request fields. Synthesis is defensive: it
    must produce something the registry/runtime can act on for any payload.
    """
    raw_manifest = args.get("manifest")
    if isinstance(raw_manifest, dict):
        try:
            return PluginManifest.from_dict(raw_manifest)
        except Exception:  # noqa: BLE001 - fall through to synthesis
            log.warning("plugin.install: bad args.manifest; synthesizing")
    toml_text = args.get("plugin_toml")
    if isinstance(toml_text, str) and toml_text.strip():
        try:
            return PluginManifest.from_toml(toml_text)
        except Exception:  # noqa: BLE001
            log.warning("plugin.install: bad args.plugin_toml; synthesizing")

    name = (
        payload.get("plugin_id")
        or args.get("name")
        or payload.get("daemon_capability_id")
        or "plugin"
    )
    return _synthesize_manifest(
        name=str(name),
        version=str(payload.get("plugin_version") or "0.0.0"),
        kind=kind,
        exposed_tools=_str_list(payload.get("exposed_tools")),
        endpoint=endpoint,
        deps=args.get("deps"),
        post_install=args.get("post_install"),
        permissions=args.get("permissions"),
    )


def _synthesize_manifest(
    *,
    name: str,
    version: str,
    kind: str,
    exposed_tools: list[str],
    endpoint: Optional[str],
    deps: Any,
    post_install: Any,
    permissions: Any,
) -> PluginManifest:
    """Build a minimal manifest dict and parse it (so we exercise one construction path)."""
    data: dict[str, Any] = {
        "plugin": {"id": name, "name": name, "version": version, "kind": kind},
        "install": {},
    }
    if isinstance(deps, list):
        data["install"]["deps"] = [str(d) for d in deps]
    if isinstance(post_install, list):
        data["install"]["post_install"] = [str(c) for c in post_install]
    if isinstance(permissions, dict):
        data["permissions"] = permissions
    provides: dict[str, Any] = {}
    if kind == "mcp" and endpoint:
        provides["mcp"] = [{"name": name, "transport": "stdio", "command": endpoint}]
    if exposed_tools:
        provides["tool"] = [{"name": t} for t in exposed_tools]
    if provides:
        data["provides"] = provides
    return PluginManifest.from_dict(data)


def _apply_permissions(agent_id: str, cap_name: str) -> None:
    """Apply a pack's declared permissions to ONE agent's ruleset policy, if supported.

    The foundation ships a PermissiveRuleset with no ``set_agent_policy``; Unit 8's engine
    adds one. We guard on the attribute so this is a no-op when the engine isn't installed.
    Crucially we scope to ``agent_id`` (never the global default), so attaching a pack to
    one agent can't loosen or clobber policy for any other agent.
    """
    perms = _PERMISSIONS.get(cap_name)
    if not perms:
        return
    ruleset = get_ruleset()
    setter = getattr(ruleset, "set_agent_policy", None)
    if not callable(setter):
        return
    policy: dict[str, Any] = {}
    if isinstance(perms.get("network"), list) and "*" not in perms["network"]:
        policy["network"] = {"allow": [str(h) for h in perms["network"]]}
    if isinstance(perms.get("filesystem"), list):
        policy["write_paths"] = {"allow": [str(p) for p in perms["filesystem"]]}
    if not policy:
        return
    try:
        setter(agent_id, policy)
    except Exception:  # noqa: BLE001 - never let a policy hint break attach
        log.exception("capability.attach: failed to apply permissions to ruleset")


def _attach_targets(
    ctx: CommandContext, payload: dict[str, Any]
) -> tuple[Optional[str], Optional[str]]:
    """Resolve (agent_id, capability_id) from the payload, the ctx, or the idem key.

    The cloud puts ``agent_id`` in the payload, but it's also encoded in the idempotency
    key ``capability.attach:{agent_id}:{cap_id}`` (and may surface via ``ctx.agent_id`` on
    some envelopes). We try all three so a renamed field still resolves a target.
    """
    cap_id = payload.get("daemon_capability_id") or payload.get("capability") or payload.get("id")
    agent_id = payload.get("agent_id") or getattr(ctx, "agent_id", None)

    if (not agent_id or not cap_id) and ctx.idempotency_key:
        # Format: "<command>:<agent_id>:<cap_id>"  (command may itself contain a dot).
        parts = ctx.idempotency_key.split(":")
        if len(parts) >= 3:
            agent_id = agent_id or parts[-2]
            cap_id = cap_id or parts[-1]
    return (str(agent_id) if agent_id else None, str(cap_id) if cap_id else None)


async def _cap_name(cap_id: str) -> Optional[str]:
    """Resolve a capability's name from the ``capabilities`` table (by id)."""
    try:
        row = await get_store().fetchone(
            "SELECT name FROM capabilities WHERE id=?", (cap_id,)
        )
    except Exception:  # noqa: BLE001
        return None
    return row.get("name") if row else None


async def _upsert_attachment(agent_id: str, capability: str, *, enabled: bool) -> None:
    try:
        await get_store().execute(
            "INSERT INTO agent_capabilities (agent_id, capability, enabled, updated_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(agent_id, capability) DO UPDATE SET enabled=excluded.enabled,"
            " updated_at=excluded.updated_at",
            (agent_id, capability, 1 if enabled else 0, time.time()),
        )
    except Exception:  # noqa: BLE001
        log.exception("capability.attach: failed to upsert agent_capabilities row")


async def _emit_status(
    cap_id: str, status: str, exposed_tools: list[str]
) -> None:
    """Report provisioning progress upstream (control channel)."""
    try:
        await get_uplink().send(
            "capability.status",
            {
                "daemon_capability_id": cap_id,
                "status": status,
                "exposed_tools": list(exposed_tools),
            },
            channel=CHANNEL_CONTROL,
        )
    except Exception:  # noqa: BLE001 - reporting is best-effort
        log.exception("capability %s: failed to emit capability.status", cap_id)
