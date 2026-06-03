"""Pure service-unit generators (tui-daemon.md §2).

Every function here is a deterministic ``params -> str|dict`` renderer with **no side
effects**: no filesystem, no subprocess, no platform detection. That keeps them trivial
to unit-test (the manager layer owns all the I/O). Each one renders the host's native
auto-restart-on-crash + start-on-boot service definition whose entry point invokes
``synapse daemon run`` (the daemon's service entrypoint).

  * :func:`systemd_unit`        — Linux systemd ``.service`` file.
  * :func:`launchd_plist`       — macOS launchd LaunchAgent/LaunchDaemon ``.plist`` XML.
  * :func:`windows_service_spec`— Windows Service definition (for pywin32 / NSSM).

``exec_path`` is the resolved launcher. The manager passes either the ``synapse`` console
script (preferred) plus ``["daemon", "run"]``, or ``sys.executable`` plus
``["-m", "synapse_worker.cli.main", "daemon", "run"]`` as a fallback.
"""
from __future__ import annotations

from typing import Sequence
from xml.sax.saxutils import escape

# Stable identifiers used across all three platforms so install/start/stop/status can
# always find the unit they wrote.
SERVICE_NAME = "synapse-worker"
SERVICE_DISPLAY = "Synapse Worker Daemon"
SERVICE_DESCRIPTION = "Synapse worker daemon — runs agents on this machine."
# launchd labels use reverse-DNS; this matches the plist filename the manager writes.
LAUNCHD_LABEL = "dev.synapse.worker"

# The args appended to ``exec_path`` to actually run the daemon. Kept here (not in the
# manager) so the generators are self-contained and testable in isolation.
DAEMON_RUN_ARGS: tuple[str, ...] = ("daemon", "run")


def _quote_exec_start(exec_path: str, args: Sequence[str]) -> str:
    """Render an ExecStart line, quoting any token that contains whitespace.

    systemd splits ExecStart on whitespace unless tokens are double-quoted, so a path
    like ``C:\\Program Files\\...`` (or a spaced launcher) must be wrapped.
    """
    parts = [exec_path, *args]
    rendered = []
    for p in parts:
        if any(ch.isspace() for ch in p):
            rendered.append(f'"{p}"')
        else:
            rendered.append(p)
    return " ".join(rendered)


def systemd_unit(
    *,
    exec_path: str,
    args: Sequence[str] = DAEMON_RUN_ARGS,
    user: bool = True,
    working_dir: str = "~/.synapse",
    description: str = SERVICE_DESCRIPTION,
    restart_sec: int = 5,
) -> str:
    """Render a systemd ``.service`` unit that auto-restarts and starts on boot.

    ``user=True`` renders a *user* unit (``WantedBy=default.target``, installed under
    ``~/.config/systemd/user``); ``user=False`` renders a *system* unit
    (``WantedBy=multi-user.target``, plus a ``User=``-less root service under
    ``/etc/systemd/system``). ``Restart=always`` is what delivers the §2 "auto-restarts
    on crash" guarantee; the ``WantedBy`` install target delivers "on boot".
    """
    wanted_by = "default.target" if user else "multi-user.target"
    exec_start = _quote_exec_start(exec_path, args)
    lines = [
        "[Unit]",
        f"Description={description}",
        # Only meaningful for system units, harmless for user units: order after the
        # network so the daemon's outbound WebSocket can connect immediately.
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={exec_start}",
        f"WorkingDirectory={working_dir}",
        # Auto-restart on crash (§2): always restart, with a small backoff.
        "Restart=always",
        f"RestartSec={restart_sec}",
        # Surface the daemon's stderr/stdout into the journal.
        "StandardOutput=journal",
        "StandardError=journal",
        "",
        "[Install]",
        f"WantedBy={wanted_by}",
        "",
    ]
    return "\n".join(lines)


def launchd_plist(
    *,
    exec_path: str,
    args: Sequence[str] = DAEMON_RUN_ARGS,
    agent: bool = True,
    label: str = LAUNCHD_LABEL,
    working_dir: str = "~/.synapse",
) -> str:
    """Render a launchd ``.plist`` XML for a LaunchAgent (or LaunchDaemon).

    ``KeepAlive=true`` delivers the §2 "auto-restart on crash" guarantee; ``RunAtLoad``
    starts it as soon as the agent/daemon is loaded (and, being installed under
    ``LaunchAgents``/``LaunchDaemons``, on login/boot). The ``agent`` flag is informational
    here (both kinds share the same plist shape); the manager uses it to choose the install
    directory. Returns a complete XML document.
    """
    program_args = "\n".join(
        f"        <string>{escape(a)}</string>" for a in (exec_path, *args)
    )
    # NB: the plist is otherwise identical for agents vs daemons; the distinction is the
    # directory it lands in (~/Library/LaunchAgents vs /Library/LaunchDaemons).
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{escape(label)}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"{program_args}\n"
        "    </array>\n"
        "    <key>WorkingDirectory</key>\n"
        f"    <string>{escape(working_dir)}</string>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>KeepAlive</key>\n"
        "    <true/>\n"
        "    <key>ProcessType</key>\n"
        "    <string>Background</string>\n"
        "</dict>\n"
        "</plist>\n"
    )


def windows_service_spec(
    *,
    exec_path: str,
    args: Sequence[str] = DAEMON_RUN_ARGS,
    name: str = SERVICE_NAME,
    display_name: str = SERVICE_DISPLAY,
    description: str = SERVICE_DESCRIPTION,
) -> dict[str, object]:
    """Render a Windows-service definition for pywin32 / an NSSM-style shim.

    Returns a plain dict (no pywin32 import — that's guarded in the manager): the service
    name, display name, the full ``binPath`` (exe + args), ``start="auto"`` for start-on-
    boot, and ``Restart`` recovery settings for auto-restart-on-crash (§2). NSSM consumes
    ``bin_path``/``app_directory``/``app_parameters`` directly; ``sc.exe``/pywin32 consume
    ``bin_path``/``start``.
    """
    quoted = [exec_path, *args]
    # sc.exe / NSSM want a single binPath string; quote the exe so spaced install paths
    # (``C:\Program Files\...``) survive.
    exe_token = f'"{exec_path}"' if any(ch.isspace() for ch in exec_path) else exec_path
    bin_path = " ".join([exe_token, *args])
    return {
        "name": name,
        "display_name": display_name,
        "description": description,
        "bin_path": bin_path,
        "exec_path": exec_path,
        "app_parameters": " ".join(args),
        "arguments": list(args),
        "command": quoted,
        # auto-start on boot.
        "start": "auto",
        "start_type": "auto",
        # Auto-restart on crash: restart on every failure with a short delay.
        "restart_on_failure": True,
        "reset_period_sec": 86400,
        "restart_delay_ms": 5000,
        "failure_action": "restart",
    }
