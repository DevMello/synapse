"""OS detection + install/start/stop/status orchestration (tui-daemon.md §2).

This is the side-effecting layer that sits on top of the pure generators in
:mod:`synapse_worker.service.units`. It:

  1. detects the host OS (:func:`detect_platform`),
  2. resolves how the service should launch the daemon (:func:`resolve_exec`),
  3. renders the right native unit and (when ``dry_run`` is False) WRITES it to the
     correct path and runs the enable/start commands via subprocess.

**Safety:** every real mutation — writing a unit file, registering a Windows service,
running ``systemctl``/``launchctl``/``sc`` — is guarded behind ``dry_run``. With
``dry_run=True`` (what the tests use) the functions return the *would-be* target path and
rendered content without touching the host. The CLI defaults to ``dry_run=False``.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Sequence

from ..logging import get_logger
from ..paths import get_paths, restrict_file, secure_write
from . import units

log = get_logger(__name__)

Platform = Literal["linux", "macos", "windows"]


@dataclass
class ServicePlan:
    """The outcome of an install/op — what we did, or (dry-run) what we *would* do.

    ``target_path`` is the unit/plist path on disk (None for the Windows service, which is
    registered with the SCM rather than written as a file). ``content`` is the rendered
    unit text (or a stringified spec for Windows). ``commands`` are the subprocess argv
    lists that register/enable/start it. ``dry_run`` records whether anything actually ran.
    """

    platform: Platform
    action: str
    target_path: Optional[Path] = None
    content: str = ""
    commands: list[list[str]] = field(default_factory=list)
    dry_run: bool = True
    wrote: bool = False
    ran: bool = False
    detail: str = ""


def detect_platform() -> Platform:
    """Return the host OS family as one of ``"linux" | "macos" | "windows"``."""
    if sys.platform.startswith("win") or platform.system() == "Windows":
        return "windows"
    if sys.platform == "darwin" or platform.system() == "Darwin":
        return "macos"
    # Everything else (Linux, *BSD) is treated as systemd-capable Linux for §2 purposes.
    return "linux"


def resolve_exec() -> tuple[str, list[str]]:
    """Resolve how the service should launch the daemon.

    Prefer the installed ``synapse`` console script (so the service runs the same entry a
    user would type) with args ``["daemon", "run"]``; otherwise fall back to the current
    interpreter running the CLI module directly. The fallback guarantees the unit is
    launchable even before the package's console script is on PATH.
    """
    console = shutil.which("synapse")
    if console:
        return console, list(units.DAEMON_RUN_ARGS)
    return sys.executable, ["-m", "synapse_worker.cli.main", *units.DAEMON_RUN_ARGS]


# --- target paths -----------------------------------------------------------------


def systemd_unit_path(system: bool = False) -> Path:
    """Where the systemd unit is written (system vs. per-user)."""
    if system:
        return Path("/etc/systemd/system") / f"{units.SERVICE_NAME}.service"
    return Path.home() / ".config" / "systemd" / "user" / f"{units.SERVICE_NAME}.service"


def launchd_plist_path(system: bool = False) -> Path:
    """Where the launchd plist is written (LaunchDaemon vs. LaunchAgent)."""
    fname = f"{units.LAUNCHD_LABEL}.plist"
    if system:
        return Path("/Library/LaunchDaemons") / fname
    return Path.home() / "Library" / "LaunchAgents" / fname


# --- render + plan ----------------------------------------------------------------


def build_plan(*, system: bool = False, dry_run: bool = True) -> ServicePlan:
    """Render the native unit and the commands to register it, WITHOUT running anything.

    This is the pure-ish planning core install() delegates to; it never writes or spawns,
    so it's safe to call from tests and from the CLI's preview path.
    """
    plat = detect_platform()
    exec_path, args = resolve_exec()
    working_dir = str(get_paths().home)

    if plat == "linux":
        content = units.systemd_unit(
            exec_path=exec_path, args=args, user=not system, working_dir=working_dir
        )
        target = systemd_unit_path(system=system)
        ctl = ["systemctl"] if system else ["systemctl", "--user"]
        commands = [
            [*ctl, "daemon-reload"],
            [*ctl, "enable", "--now", f"{units.SERVICE_NAME}.service"],
        ]
        return ServicePlan(
            platform=plat,
            action="install",
            target_path=target,
            content=content,
            commands=commands,
            dry_run=dry_run,
        )

    if plat == "macos":
        content = units.launchd_plist(
            exec_path=exec_path, args=args, agent=not system, working_dir=working_dir
        )
        target = launchd_plist_path(system=system)
        commands = [
            ["launchctl", "load", "-w", str(target)],
        ]
        return ServicePlan(
            platform=plat,
            action="install",
            target_path=target,
            content=content,
            commands=commands,
            dry_run=dry_run,
        )

    # windows
    spec = units.windows_service_spec(exec_path=exec_path, args=args)
    commands = [
        [
            "sc.exe",
            "create",
            str(spec["name"]),
            f"binPath= {spec['bin_path']}",
            "start= auto",
            f"DisplayName= {spec['display_name']}",
        ],
        ["sc.exe", "failure", str(spec["name"]), "reset=", "86400", "actions=", "restart/5000"],
        ["sc.exe", "start", str(spec["name"])],
    ]
    return ServicePlan(
        platform=plat,
        action="install",
        target_path=None,
        content=_format_spec(spec),
        commands=commands,
        dry_run=dry_run,
    )


def _format_spec(spec: dict) -> str:
    return "\n".join(f"{k} = {v}" for k, v in spec.items())


# --- side-effecting ops -----------------------------------------------------------


def install(*, system: bool = False, dry_run: bool = False) -> ServicePlan:
    """Generate + register the host service. Guarded by ``dry_run``.

    ``dry_run=True`` returns the would-be target path + rendered content and runs nothing
    (what tests use). ``dry_run=False`` (CLI default) writes the unit with owner-only perms
    and runs the enable/start commands.
    """
    plan = build_plan(system=system, dry_run=dry_run)
    if dry_run:
        plan.detail = "dry-run: nothing written or registered"
        return plan

    # Linux/macOS: write the rendered unit/plist to disk first (owner-only perms).
    if plan.target_path is not None:
        plan.target_path.parent.mkdir(parents=True, exist_ok=True)
        secure_write(plan.target_path, plan.content)
        restrict_file(plan.target_path)
        plan.wrote = True
        log.info("wrote service unit to %s", plan.target_path)

    plan.ran = _run_commands(plan.commands)
    plan.detail = "installed" if plan.ran else "wrote unit but registration command failed"
    return plan


def _op(action: str, *, dry_run: bool = False) -> ServicePlan:
    """Shared start/stop/status dispatch — render the op's commands, run unless dry-run."""
    plat = detect_platform()
    plan = ServicePlan(platform=plat, action=action, dry_run=dry_run)
    plan.commands = _op_commands(plat, action)
    if dry_run:
        plan.detail = f"dry-run: would {action}"
        return plan
    plan.ran = _run_commands(plan.commands)
    plan.detail = action
    return plan


def _op_commands(plat: Platform, action: str) -> list[list[str]]:
    """The subprocess argv lists for a start/stop/status op on a given platform."""
    name = units.SERVICE_NAME
    if plat == "linux":
        verb = {"start": "start", "stop": "stop", "status": "status"}[action]
        return [["systemctl", "--user", verb, f"{name}.service"]]
    if plat == "macos":
        path = str(launchd_plist_path(system=False))
        if action == "start":
            return [["launchctl", "load", "-w", path]]
        if action == "stop":
            return [["launchctl", "unload", "-w", path]]
        return [["launchctl", "list", units.LAUNCHD_LABEL]]
    # windows
    verb = {"start": "start", "stop": "stop", "status": "query"}[action]
    return [["sc.exe", verb, name]]


def start(*, dry_run: bool = False) -> ServicePlan:
    return _op("start", dry_run=dry_run)


def stop(*, dry_run: bool = False) -> ServicePlan:
    return _op("stop", dry_run=dry_run)


def status(*, dry_run: bool = False) -> ServicePlan:
    return _op("status", dry_run=dry_run)


def _run_commands(commands: Sequence[Sequence[str]]) -> bool:
    """Run each command, logging failures. Returns True iff all succeeded.

    Best-effort: a missing ``systemctl``/``launchctl``/``sc`` (or a non-zero exit) is
    logged, not raised, so a partial environment doesn't crash the CLI.
    """
    ok = True
    for cmd in commands:
        try:
            proc = subprocess.run(
                list(cmd), capture_output=True, text=True, check=False
            )
        except (OSError, ValueError) as exc:  # tool not found / bad argv
            log.error("service command failed to spawn %s: %s", cmd, exc)
            ok = False
            continue
        if proc.returncode != 0:
            log.error(
                "service command exited %d: %s\n%s",
                proc.returncode,
                " ".join(cmd),
                proc.stderr.strip(),
            )
            ok = False
    return ok
