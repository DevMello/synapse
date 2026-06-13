"""Agent command handlers: deploy / run / cancel / update_prompt (§4.3).

``app.build_daemon`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one (a) registers these ``@on_command`` handlers AND (b) — via the
``api_adapter`` import below — registers the ``"api"`` adapter into the runtime registry.

Handlers are deliberately tolerant of payload shape: the cloud is the source of truth for
the wire, but a missing/renamed field must degrade gracefully (skip / failed run) rather
than crash the control loop.

Run execution is fire-and-forget: ``agent.run`` schedules the engine on a background task
so the handler returns promptly (the connection loop acks after dispatch, not after the
run completes). Running tasks are tracked so ``agent.cancel`` can cancel them.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from ..errors import ManifestError
from ..logging import get_logger
from ..paths import get_paths, secure_write
from ..router import CommandContext, on_command
from ..runtime.base import AgentManifest
from ..runtime.engine import RunEngine
from ..store import get_store
from ..uplink import CHANNEL_CONTROL, get_uplink

# Importing the API adapter module registers the "api" adapter at daemon assembly.
from ..runtime import api_adapter  # noqa: F401  (import for side-effect: register_adapter)

log = get_logger(__name__)

# One engine instance shared across handlers (the engine is stateless).
_engine = RunEngine()

# run_id -> asyncio.Task for in-flight runs, so agent.cancel can target them.
_running: dict[str, asyncio.Task] = {}


# ── agent.deploy ────────────────────────────────────────────────────────────
@on_command("agent.deploy")
async def handle_deploy(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Write ``agent.toml`` + prompt files under the agent dir and upsert ``agents``."""
    agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else payload
    agent_id = agent.get("id") or payload.get("agent_id") or payload.get("id")
    if not agent_id:
        log.warning("agent.deploy: missing agent id; ignoring")
        return

    name = agent.get("name", agent_id)
    type_ = agent.get("type", "api")
    platform = agent.get("platform", "any")
    version = int(agent.get("version", payload.get("version", 1)) or 1)

    # The manifest may arrive pre-rendered as TOML text, or as a structured dict.
    manifest_text = _manifest_toml(payload, agent_id, name, type_, platform, version)
    prompt = payload.get("prompt") or agent.get("prompt")

    agent_dir = get_paths().agent_dir(agent_id)
    secure_write(agent_dir / "agent.toml", manifest_text)
    if prompt is not None:
        secure_write(agent_dir / "prompt.md", str(prompt))
        # Keep a versioned copy alongside the active prompt for rollback/history.
        secure_write(agent_dir / f"prompt.v{version}.md", str(prompt))

    await get_store().execute(
        "INSERT INTO agents (id, name, type, platform, version, manifest, updated_at)"
        " VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(id) DO UPDATE SET name=excluded.name, type=excluded.type,"
        " platform=excluded.platform, version=excluded.version,"
        " manifest=excluded.manifest, updated_at=excluded.updated_at",
        (agent_id, name, type_, platform, version, manifest_text, time.time()),
    )
    log.info("agent.deploy: stored agent %s (v%s)", agent_id, version)


# ── agent.run ───────────────────────────────────────────────────────────────
@on_command("agent.run")
async def handle_run(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Load the stored manifest and launch the engine on a background task."""
    run_id = payload.get("run_id")
    agent_id = payload.get("agent_id")
    if not run_id or not agent_id:
        log.warning("agent.run: missing run_id/agent_id; ignoring")
        return

    manifest = await _load_manifest(agent_id)
    if manifest is None:
        log.warning("agent.run %s: agent %s not found; reporting failed", run_id, agent_id)
        await _emit_failed(run_id, "agent not found")
        return

    # Optional per-run model override — §10 "run winner for real" pins the WINNING model
    # (and its provider) onto this otherwise-normal run, rather than the agent's default.
    _apply_model_override(manifest, payload)

    prompt_vars = payload.get("prompt_vars") or {}
    env = payload.get("env") or {}

    task = asyncio.create_task(
        _run_and_cleanup(manifest=manifest, run_id=run_id, prompt_vars=prompt_vars, env=env)
    )
    _running[run_id] = task


# ── agent.cancel ────────────────────────────────────────────────────────────
@on_command("agent.cancel")
async def handle_cancel(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Cancel an in-flight run task and persist a ``cancelled`` terminal state."""
    run_id = payload.get("run_id")
    if not run_id:
        log.warning("agent.cancel: missing run_id; ignoring")
        return

    task = _running.pop(run_id, None)
    if task is not None and not task.done():
        task.cancel()

    # Persist the cancellation directly: the cancelled task may not get to run _finish.
    try:
        await get_store().execute(
            "UPDATE run_history SET status=?, finished_at=? WHERE run_id=?",
            ("cancelled", time.time(), run_id),
        )
    except Exception:  # noqa: BLE001 - persistence best-effort
        log.exception("agent.cancel %s: failed to persist status", run_id)

    await _emit_run_finished(run_id, "cancelled")
    log.info("agent.cancel: cancelled run %s", run_id)


# ── agent.update_prompt ─────────────────────────────────────────────────────
@on_command("agent.update_prompt")
async def handle_update_prompt(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Write a new prompt version file and bump ``agents.version``."""
    agent_id = payload.get("agent_id")
    prompt = payload.get("prompt")
    if not agent_id or prompt is None:
        log.warning("agent.update_prompt: missing agent_id/prompt; ignoring")
        return
    version = int(payload.get("version", 0) or 0)

    agent_dir = get_paths().agent_dir(agent_id)
    secure_write(agent_dir / "prompt.md", str(prompt))
    if version:
        secure_write(agent_dir / f"prompt.v{version}.md", str(prompt))

    try:
        if version:
            await get_store().execute(
                "UPDATE agents SET version=?, updated_at=? WHERE id=?",
                (version, time.time(), agent_id),
            )
        else:
            await get_store().execute(
                "UPDATE agents SET updated_at=? WHERE id=?", (time.time(), agent_id)
            )
    except Exception:  # noqa: BLE001
        log.exception("agent.update_prompt %s: failed to bump version", agent_id)
    log.info("agent.update_prompt: agent %s -> v%s", agent_id, version or "(unchanged)")


# ── helpers ─────────────────────────────────────────────────────────────────
async def _run_and_cleanup(
    *, manifest: AgentManifest, run_id: str, prompt_vars: dict, env: dict
) -> None:
    try:
        await _engine.run_agent(
            manifest=manifest, run_id=run_id, prompt_vars=prompt_vars, env=env
        )
    finally:
        # Drop our handle once the run settles (cancel may have already popped it).
        _running.pop(run_id, None)


async def _load_manifest(agent_id: str) -> Optional[AgentManifest]:
    """Load the manifest from the stored ``agent.toml`` (preferred) or the agents row."""
    agent_dir = get_paths().agent_dir(agent_id)
    toml_path = agent_dir / "agent.toml"
    if toml_path.exists():
        try:
            return AgentManifest.from_toml(toml_path.read_text(encoding="utf-8"))
        except (ManifestError, OSError) as exc:
            log.warning("agent %s: bad agent.toml: %s", agent_id, exc)

    # Fallback to the stored manifest text in the agents table.
    try:
        row = await get_store().fetchone(
            "SELECT manifest FROM agents WHERE id=?", (agent_id,)
        )
    except Exception:  # noqa: BLE001
        return None
    if row and row.get("manifest"):
        try:
            return AgentManifest.from_toml(row["manifest"])
        except ManifestError:
            return None
    return None


def _apply_model_override(manifest: AgentManifest, payload: dict[str, Any]) -> None:
    """Pin a different model/provider onto this run when the payload carries one.

    Used by the §10 "run winner for real" promotion: the winning model (and its provider,
    which may differ from the agent's default) is re-run live. Only applies to API agents —
    ``model`` is a first-class field there (E5). The manifest is freshly loaded per run, so
    mutating it in place corrupts nothing shared.
    """
    model = payload.get("variant_model")
    if not model or manifest.type != "api":
        return
    api = dict(manifest.api or {})
    api["model"] = model
    provider = payload.get("variant_provider")
    if provider:
        api["provider"] = provider
    manifest.api = api


def _manifest_toml(
    payload: dict[str, Any],
    agent_id: str,
    name: str,
    type_: str,
    platform: str,
    version: int,
) -> str:
    """Return TOML manifest text from the payload, or synthesize a minimal one."""
    manifest = payload.get("manifest")
    if isinstance(manifest, str) and manifest.strip():
        return manifest
    if isinstance(manifest, dict):
        return _dict_to_toml(manifest)
    # Synthesize a minimal but valid agent.toml so the engine can load it later.
    api = payload.get("api") or {}
    lines = [
        "[agent]",
        f'id = "{agent_id}"',
        f'name = "{name}"',
        f'type = "{type_}"',
        f'platform = "{platform}"',
        f"version = {version}",
    ]
    if api:
        lines.append("")
        lines.append("[api]")
        for k, v in api.items():
            lines.append(f"{k} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def _dict_to_toml(manifest: dict[str, Any]) -> str:
    """Minimal dict->TOML for the manifest tables we care about (one nesting level)."""
    lines: list[str] = []
    scalars = {k: v for k, v in manifest.items() if not isinstance(v, dict)}
    if scalars:
        for k, v in scalars.items():
            lines.append(f"{k} = {_toml_value(v)}")
    for section, body in manifest.items():
        if not isinstance(body, dict):
            continue
        lines.append("")
        lines.append(f"[{section}]")
        for k, v in body.items():
            if isinstance(v, dict):
                continue  # skip deeper nesting (not needed for the manifest seam)
            lines.append(f"{k} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    # Strings: escape backslash + double-quote for a basic TOML string.
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


async def _emit_failed(run_id: str, reason: str) -> None:
    try:
        await get_store().execute(
            "INSERT INTO run_history (run_id, status, started_at, finished_at, detail)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(run_id) DO UPDATE SET status='failed',"
            " finished_at=excluded.finished_at, detail=excluded.detail",
            (run_id, "failed", time.time(), time.time(), reason),
        )
    except Exception:  # noqa: BLE001
        log.exception("run %s: failed to persist failed state", run_id)
    await _emit_run_finished(run_id, "failed")


async def _emit_run_finished(run_id: str, status: str) -> None:
    try:
        await get_uplink().send(
            "run.finished",
            {"run_id": run_id, "status": status, "cost_usd": 0.0,
             "tokens_in": 0, "tokens_out": 0},
            channel=CHANNEL_CONTROL,
        )
    except Exception:  # noqa: BLE001
        log.exception("run %s: failed to emit run.finished", run_id)
