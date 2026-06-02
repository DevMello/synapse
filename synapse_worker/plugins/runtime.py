"""Plugin provisioning lifecycle + MCP process management (§4.11).

This is the *daemon-tier* engine behind ``plugin.install`` / ``mcp.configure``: it takes a
provisioning request (a manifest, plus the cloud's ``daemon_capability_id`` / ``kind`` /
``exposed_tools`` / ``endpoint`` / ``args``) and:

  1. **Checks platform** compatibility against this host.
  2. **Verifies** a supplied checksum (same gate as self-updates) — a mismatch fails hard
     BEFORE anything is created/run, so a tampered pack never executes.
  3. **Provisions in isolation** under ``~/.synapse/plugins/{name}/``:
       * ``composite`` / ``script`` / ``workspace`` → a dedicated venv (``python -m venv``;
         ``uv venv`` is an equivalent the operator may prefer), then ``deps`` install and
         the ``post_install`` steps.
       * ``mcp`` → no venv; just record an MCP server spec (transport/command from the
         ``endpoint`` / ``args``) the :class:`McpProcess` manager can later spawn.
  4. **Registers** the capability in the foundation ``PluginRegistry`` /
     ``CapabilityRegistry`` and the ``capabilities`` table, flipping
     ``installing → ready | failed``.

The heavy steps (venv create, dep install, ``post_install``) all funnel through
:meth:`PluginRuntime._provision`, which the unit tests monkeypatch so CI never builds a
real venv or hits the network.

MCP processes are managed (not spoken-to): :class:`McpProcess` spawns the stdio server as
a subprocess via ``asyncio.create_subprocess_exec`` and exposes ``start``/``stop``/health.
We do NOT implement an MCP client here — the runtime only owns the process lifecycle.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..capabilities.registry import Capability, get_capability_registry
from ..errors import CapabilityError
from ..logging import get_logger
from ..paths import get_paths
from ..plugins.base import PluginManifest, get_plugin_registry
from ..store import get_store

log = get_logger(__name__)

# Kinds that get a real isolated venv/workspace. ``mcp`` is the odd one out: it only
# registers a server spec to spawn on demand.
_VENV_KINDS = frozenset({"composite", "script", "workspace"})


# ── checksum gate ─────────────────────────────────────────────────────────────
def verify_checksum(data: bytes, expected: str) -> bool:
    """Return True iff ``sha256(data)`` matches ``expected``.

    Mirrors the self-update integrity gate: an artifact with a declared checksum must hash
    to it before we trust/run it. ``expected`` may carry a ``sha256:`` prefix. An empty
    ``expected`` means "no checksum supplied" — callers decide whether that's acceptable
    (provisioning treats a *supplied-but-mismatched* checksum as fatal, absence as OK).
    """
    want = expected.strip().lower()
    if want.startswith("sha256:"):
        want = want.split(":", 1)[1]
    if not want:
        return True
    return hashlib.sha256(data).hexdigest() == want


# ── MCP process manager ───────────────────────────────────────────────────────
@dataclass
class McpServerSpec:
    """A spawnable MCP server: transport + the argv to launch it."""

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: Optional[str] = None
    env: dict[str, str] = field(default_factory=dict)

    def argv(self) -> list[str]:
        """The full argv: ``command`` shell-split (platform-aware) then extended by args."""
        base = shlex.split(self.command, posix=(sys.platform != "win32")) if self.command else []
        return base + list(self.args)


class McpProcess:
    """Owns the lifecycle of one MCP server subprocess (stdio transport).

    We manage the process — start it, watch that it's alive, stop it — but do not speak the
    MCP protocol to it; a real client lives in the runtime that wires the server into an
    agent. Kept deliberately small so a slow/garbage server can never block the daemon.
    """

    def __init__(self, spec: McpServerSpec) -> None:
        self.spec = spec
        self._proc: Optional[asyncio.subprocess.Process] = None

    async def start(self) -> None:
        if self.is_running():
            return
        argv = self.spec.argv()
        if not argv:
            raise CapabilityError(f"mcp server {self.spec.name!r} has no command to spawn")
        # Inherit the daemon's env plus any spec overrides; stdio transport keeps the pipes
        # so a future client can attach. We never block on output here.
        import os

        env = {**os.environ, **self.spec.env}
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.spec.cwd,
            env=env,
        )
        log.info("mcp %s: started (pid=%s)", self.spec.name, self._proc.pid)

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc is not None else None

    async def stop(self, timeout: float = 5.0) -> None:
        """Terminate the process, escalating to kill if it doesn't exit in ``timeout``."""
        if self._proc is None:
            return
        if self._proc.returncode is None:
            try:
                self._proc.terminate()
            except ProcessLookupError:  # already gone
                self._proc = None
                return
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        log.info("mcp %s: stopped", self.spec.name)
        self._proc = None


# ── provisioning result ───────────────────────────────────────────────────────
@dataclass
class ProvisionResult:
    capability_id: str
    name: str
    kind: str
    status: str  # ready | failed
    exposed_tools: list[str] = field(default_factory=list)
    error: Optional[str] = None
    plugin_dir: Optional[Path] = None


# ── the runtime ───────────────────────────────────────────────────────────────
class PluginRuntime:
    """Provisions capabilities on the daemon and tracks their MCP processes.

    One instance is shared by the command handlers (a module singleton, below). It owns:
      * the in-flight MCP processes (by capability id), so ``plugin.remove`` can stop them;
      * the provisioning steps, which are mocked wholesale in tests via :meth:`_provision`.
    """

    def __init__(self) -> None:
        # daemon_capability_id -> McpProcess (only for kind='mcp' that we've spawned).
        self._processes: dict[str, McpProcess] = {}
        # daemon_capability_id -> the resolved manifest name (for registry teardown).
        self._names: dict[str, str] = {}
        # daemon_capability_id -> McpServerSpec (so a later start() can spawn it).
        self._specs: dict[str, McpServerSpec] = {}

    # ── public lifecycle ──────────────────────────────────────────────────────
    async def install(
        self,
        *,
        daemon_capability_id: str,
        kind: str,
        manifest: PluginManifest,
        exposed_tools: list[str],
        endpoint: Optional[str] = None,
        args: Optional[dict[str, Any]] = None,
        checksum: Optional[str] = None,
        checksum_data: Optional[bytes] = None,
        platform: Optional[str] = None,
    ) -> ProvisionResult:
        """Provision a capability end-to-end and return the terminal result.

        Records ``installing`` first, then either provisions (venv kinds) or registers an
        MCP spec, and finally marks ``ready``. Any failure marks ``failed`` and returns a
        result carrying the error — provisioning never raises into the control loop.
        """
        args = args or {}
        name = manifest.name
        self._names[daemon_capability_id] = name

        # Mark installing in BOTH the durable table and the in-memory registries up front,
        # so the Web UI sees progress even before the (possibly slow) provisioning runs.
        await self._record_status(
            daemon_capability_id, kind, name, "installing", manifest=manifest
        )
        get_plugin_registry().add(manifest, status="installing")
        get_capability_registry().mark_available(
            Capability(name=name, kind=kind, status="installing", tools=list(exposed_tools))
        )

        try:
            # 1. Platform gate — a pack that doesn't support this OS never provisions.
            host = platform or _host_platform()
            if not manifest.supports_platform(host):
                raise CapabilityError(
                    f"plugin {name!r} does not support platform {host!r}"
                )

            # 2. Integrity gate (same posture as self-updates): a SUPPLIED checksum that
            # doesn't match is fatal. Absence is allowed (nothing to verify against).
            if checksum and checksum_data is not None:
                if not verify_checksum(checksum_data, checksum):
                    raise CapabilityError(f"plugin {name!r} checksum mismatch")

            # 3. Provision: venv kinds build/install; mcp registers a spawnable spec.
            if kind in _VENV_KINDS:
                await self._provision(name=name, manifest=manifest)
            elif kind == "mcp":
                spec = self._mcp_spec(name, manifest, endpoint, args)
                self._specs[daemon_capability_id] = spec
            else:
                raise CapabilityError(f"unknown capability kind {kind!r}")

        except Exception as exc:  # noqa: BLE001 - turn any failure into a failed status
            log.exception("plugin.install %s: provisioning failed", name)
            await self._record_status(
                daemon_capability_id, kind, name, "failed", manifest=manifest
            )
            get_plugin_registry().set_status(name, "failed", error=str(exc))
            cap = get_capability_registry().get(name)
            if cap is not None:
                cap.status = "failed"
            return ProvisionResult(
                capability_id=daemon_capability_id,
                name=name,
                kind=kind,
                status="failed",
                exposed_tools=list(exposed_tools),
                error=str(exc),
            )

        # 4. Success: flip to ready in the table + both registries.
        await self._record_status(
            daemon_capability_id, kind, name, "ready", manifest=manifest
        )
        get_plugin_registry().set_status(name, "ready")
        cap = get_capability_registry().get(name)
        if cap is not None:
            cap.status = "ready"
        return ProvisionResult(
            capability_id=daemon_capability_id,
            name=name,
            kind=kind,
            status="ready",
            exposed_tools=list(exposed_tools),
            plugin_dir=get_paths().plugin_dir(name),
        )

    async def remove(self, daemon_capability_id: str) -> Optional[str]:
        """Tear down a provisioned capability: stop its MCP process, rmtree its dir, and
        drop it from the registries + the ``capabilities`` table. Returns the name removed.

        Best-effort throughout — a missing dir / already-dead process is fine.
        """
        name = self._names.get(daemon_capability_id)

        # Stop a running MCP process and forget its spec.
        proc = self._processes.pop(daemon_capability_id, None)
        if proc is not None:
            try:
                await proc.stop()
            except Exception:  # noqa: BLE001 - teardown is best-effort
                log.exception("plugin.remove %s: failed to stop mcp process", daemon_capability_id)
        self._specs.pop(daemon_capability_id, None)

        # If we don't know the name (e.g. restart lost in-memory state), look it up.
        if name is None:
            row = await self._row(daemon_capability_id)
            if row is not None:
                name = row.get("name")

        # rmtree the plugin dir (venv/workspace), if any.
        if name:
            plugin_dir = get_paths().plugin_dir(name)
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir, ignore_errors=True)
            get_plugin_registry().remove(name)
            get_capability_registry().remove_available(name)

        # Drop the capability row and any agent attachments (detaches from ALL agents).
        try:
            await get_store().execute(
                "DELETE FROM capabilities WHERE id=?", (daemon_capability_id,)
            )
            if name:
                await get_store().execute(
                    "DELETE FROM agent_capabilities WHERE capability=?", (name,)
                )
        except Exception:  # noqa: BLE001
            log.exception("plugin.remove %s: failed to delete rows", daemon_capability_id)

        self._names.pop(daemon_capability_id, None)
        return name

    # ── MCP process control ───────────────────────────────────────────────────
    async def start_mcp(self, daemon_capability_id: str) -> Optional[McpProcess]:
        """Spawn (or return the already-running) MCP process for a capability."""
        spec = self._specs.get(daemon_capability_id)
        if spec is None:
            return None
        proc = self._processes.get(daemon_capability_id)
        if proc is None:
            proc = McpProcess(spec)
            self._processes[daemon_capability_id] = proc
        await proc.start()
        return proc

    async def stop_mcp(self, daemon_capability_id: str) -> None:
        proc = self._processes.get(daemon_capability_id)
        if proc is not None:
            await proc.stop()

    def mcp_process(self, daemon_capability_id: str) -> Optional[McpProcess]:
        return self._processes.get(daemon_capability_id)

    def spec_for(self, daemon_capability_id: str) -> Optional[McpServerSpec]:
        return self._specs.get(daemon_capability_id)

    # ── provisioning internals (mocked in tests) ──────────────────────────────
    async def _provision(self, *, name: str, manifest: PluginManifest) -> None:
        """Create the isolated venv, install ``deps``, run ``post_install``.

        Heavy + side-effecting (filesystem + subprocess + network). Tests monkeypatch THIS
        method so no real venv is built and nothing is downloaded. Kept as one seam so the
        public ``install`` flow (status tracking, registries) is exercised end-to-end.
        """
        plugin_dir = get_paths().plugin_dir(name)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        venv_dir = plugin_dir / ".venv"

        install = manifest.install if isinstance(manifest.install, dict) else {}
        deps = [str(d) for d in (install.get("deps") or [])]
        post_install = [str(c) for c in (install.get("post_install") or [])]

        # 1. Create the venv (uv is an equivalent; stdlib venv keeps us dep-free).
        await _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=plugin_dir)

        # 2. Install deps into the venv's pip.
        if deps:
            await _run([str(_venv_python(venv_dir)), "-m", "pip", "install", *deps], cwd=plugin_dir)

        # 3. Run post_install steps (already inside the provisioned dir).
        for step in post_install:
            await _run(shlex.split(step, posix=(sys.platform != "win32")), cwd=plugin_dir)

    def _mcp_spec(
        self,
        name: str,
        manifest: PluginManifest,
        endpoint: Optional[str],
        args: dict[str, Any],
    ) -> McpServerSpec:
        """Build the spawnable MCP spec from the manifest + the cloud's endpoint/args.

        Precedence for the launch command: explicit ``endpoint`` → the manifest's first
        ``provides.mcp.command``. ``args`` may carry extra argv (``args.args``), a transport
        override, a cwd, and an env map. Defensive about every field's type.
        """
        command = (endpoint or "").strip()
        transport = "stdio"
        if not command and manifest.provides_mcp:
            command = manifest.provides_mcp[0].command
            transport = manifest.provides_mcp[0].transport or "stdio"
        if isinstance(args.get("transport"), str):
            transport = args["transport"]
        extra = args.get("args")
        argv_extra = [str(a) for a in extra] if isinstance(extra, list) else []
        env = args.get("env")
        env_map = {str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {}
        cwd = args.get("cwd") if isinstance(args.get("cwd"), str) else None
        return McpServerSpec(
            name=name,
            transport=transport,
            command=command,
            args=argv_extra,
            cwd=cwd,
            env=env_map,
        )

    # ── persistence ───────────────────────────────────────────────────────────
    async def _record_status(
        self,
        daemon_capability_id: str,
        kind: str,
        name: str,
        status: str,
        *,
        manifest: Optional[PluginManifest] = None,
    ) -> None:
        """Upsert the ``capabilities`` row (id keyed by daemon_capability_id)."""
        manifest_json = json.dumps(manifest.raw, separators=(",", ":")) if manifest else None
        try:
            await get_store().execute(
                "INSERT INTO capabilities (id, kind, name, status, manifest, updated_at)"
                " VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, name=excluded.name,"
                " status=excluded.status, manifest=excluded.manifest,"
                " updated_at=excluded.updated_at",
                (daemon_capability_id, kind, name, status, manifest_json, time.time()),
            )
        except Exception:  # noqa: BLE001 - persistence best-effort; never sink the control loop
            log.exception(
                "capability %s: failed to persist status %s", daemon_capability_id, status
            )

    async def _row(self, daemon_capability_id: str) -> Optional[dict[str, Any]]:
        try:
            return await get_store().fetchone(
                "SELECT * FROM capabilities WHERE id=?", (daemon_capability_id,)
            )
        except Exception:  # noqa: BLE001
            return None


# ── helpers ───────────────────────────────────────────────────────────────────
def _host_platform() -> str:
    """This host's plugin-manifest platform token (windows | macos | linux)."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _venv_python(venv_dir: Path) -> Path:
    """The python executable inside a provisioned venv (OS-specific layout)."""
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


async def _run(argv: list[str], *, cwd: Optional[Path] = None) -> None:
    """Run a provisioning subprocess to completion, raising on a non-zero exit.

    Output is captured (so it can't garble the daemon's stdout) and surfaced in the error.
    """
    if not argv:
        return
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd) if cwd else None,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        tail = (out or b"").decode("utf-8", "replace")[-2000:]
        raise CapabilityError(
            f"provisioning step failed ({' '.join(argv[:2])}...): exit {proc.returncode}\n{tail}"
        )


# ── singleton seam ────────────────────────────────────────────────────────────
_runtime: PluginRuntime = PluginRuntime()


def get_plugin_runtime() -> PluginRuntime:
    return _runtime


def reset_plugin_runtime() -> None:  # test helper
    global _runtime
    _runtime = PluginRuntime()


__all__ = [
    "PluginRuntime",
    "McpProcess",
    "McpServerSpec",
    "ProvisionResult",
    "verify_checksum",
    "get_plugin_runtime",
    "reset_plugin_runtime",
]
