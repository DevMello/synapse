"""CLI adapter — wraps an arbitrary command-line agent (§4.3).

The ``cli`` adapter runs *any* command-line agent (Claude Code, aider, gemini, a bare
shell script) as a subprocess, streams its stdout/stderr into the live reasoning trace,
enforces the manifest's timeout, and attaches local token/cost accounting (ccusage).

It satisfies the :class:`~synapse_worker.runtime.base.Adapter` protocol so the runtime
engine (sibling unit) can ``get_adapter("cli")`` and drive it identically to the API
adapter. This module is self-contained: importing it registers the adapter; it does not
import the engine.

Security posture (on-device guarantee):

  * The child process starts from a **minimal, scrubbed** environment — we do NOT inherit
    the daemon's whole ``os.environ`` (which may hold the daemon's own cloud tokens, key
    material, etc.). Only a tiny OS whitelist (PATH, HOME, LANG, ...) plus the explicitly
    injected ``ctx.env`` secrets/vars reach the agent. See :func:`_build_child_env`.
  * Raw env values are never logged.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
from typing import Any, Optional

from ..logging import get_logger
from . import ccusage
from .base import Adapter, RunContext, RunResult, Usage, register_adapter

log = get_logger(__name__)

# Minimal OS env whitelist inherited by every child. These are needed for the binary to
# resolve and behave (locate the executable via PATH, find the home dir, locale), but
# carry no daemon secrets. Everything else from the parent is dropped; the agent's own
# secrets arrive explicitly via ``ctx.env``.
_ENV_WHITELIST = (
    "PATH",
    "HOME",
    "USERPROFILE",   # Windows home
    "SYSTEMROOT",    # Windows: required for many binaries to start
    "SYSTEMDRIVE",
    "TEMP",
    "TMP",
    "WINDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATHEXT",       # Windows: how the shell resolves executable extensions
    "COMSPEC",
)


class CliAdapter:
    """Adapter that runs a command-line agent as a scrubbed subprocess."""

    async def run(self, ctx: RunContext) -> RunResult:
        cli = ctx.manifest.cli or {}
        command_tmpl = cli.get("command")
        if not command_tmpl:
            return RunResult(status="failed", error="manifest.cli.command is required")

        # Render {{var}} placeholders from prompt_vars (e.g. {{prompt}}).
        command = _render(command_tmpl, ctx.prompt_vars)
        args = [_render(a, ctx.prompt_vars) for a in cli.get("args", [])]
        cwd = _render(cli["cwd"], ctx.prompt_vars) if cli.get("cwd") else None
        env = _build_child_env(ctx.env)
        timeout = ctx.manifest.timeout_sec

        log.info(
            "cli run %s: spawning %s (%d args, cwd=%s, timeout=%s)",
            ctx.run_id,
            command,
            len(args),
            cwd or "<inherit>",
            timeout,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                command,
                *args,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **_new_process_group_kwargs(),
            )
        except (OSError, ValueError) as exc:
            return RunResult(status="failed", error=f"spawn failed: {exc}")

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        async def pump(stream: asyncio.StreamReader, name: str, sink: list[str]) -> None:
            # tool_result for stdout (the agent's product), log for stderr (diagnostics).
            kind = "tool_result" if name == "stdout" else "log"
            async for line in _iter_lines(stream):
                sink.append(line)
                await ctx.trace(kind, stream=name, content=line)

        pumps = asyncio.gather(
            pump(proc.stdout, "stdout", stdout_lines),
            pump(proc.stderr, "stderr", stderr_lines),
        )

        timed_out = False
        try:
            if timeout:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            else:
                await proc.wait()
        except asyncio.TimeoutError:
            timed_out = True
            await _terminate(proc)

        # Drain whatever the pumps captured before/after exit (cancel on timeout so a
        # wedged stream can't hang us after we've already killed the process).
        try:
            if timed_out:
                pumps.cancel()
            await pumps
        except (asyncio.CancelledError, OSError):
            # Cancelled drain (timeout path) or a torn-down pipe — both are benign here.
            pass

        if timed_out:
            await ctx.trace("error", reason="timeout", timeout_sec=timeout)
            return RunResult(
                status="failed",
                error=f"timeout after {timeout}s",
                usage=ccusage.read_usage(_tool_name(command)),
                output="\n".join(stdout_lines),
            )

        exit_code = proc.returncode
        stdout_text = "\n".join(stdout_lines)

        # Structured output: if the agent was asked for JSON (or its stdout parses as JSON)
        # keep the parsed object as the run output; otherwise keep the raw text.
        output, parsed = _extract_output(args, stdout_text)

        # Usage: prefer an exact usage block the CLI emitted itself; else ccusage; else
        # estimated. Cost-unavailable degrades to estimated — never wrong, never raises.
        usage = _resolve_usage(_tool_name(command), parsed)

        status = "succeeded" if exit_code == 0 else "failed"
        error = None if exit_code == 0 else f"exit code {exit_code}"
        if error and stderr_lines:
            error = f"{error}: {stderr_lines[-1]}"

        await ctx.trace("status", status=status, exit_code=exit_code)
        return RunResult(status=status, usage=usage, output=output, error=error)


# Chunk size for the line splitter below. Independent of asyncio's 64 KiB readline buffer
# limit — we never call readline(), so an oversized line can't raise.
_READ_CHUNK = 65536


async def _iter_lines(stream: asyncio.StreamReader):
    """Yield decoded, newline-stripped lines from a stream of arbitrary line length.

    We deliberately avoid ``StreamReader.readline``, which raises ``LimitOverrunError``
    once a single line exceeds the 64 KiB buffer — very reachable for an agent emitting a
    large ``--output-format json`` blob on one line. Instead we pull fixed-size chunks and
    split on ``\\n`` ourselves, so line length is unbounded and never crashes the run.
    """
    buf = b""
    while True:
        chunk = await stream.read(_READ_CHUNK)
        if not chunk:
            break
        buf += chunk
        while True:
            nl = buf.find(b"\n")
            if nl < 0:
                break
            line, buf = buf[:nl], buf[nl + 1 :]
            yield line.decode("utf-8", errors="replace").rstrip("\r")
    if buf:  # trailing data with no final newline
        yield buf.decode("utf-8", errors="replace").rstrip("\r")


# ── helpers ─────────────────────────────────────────────────────────────────
def _render(value: str, prompt_vars: dict[str, Any]) -> str:
    """Substitute ``{{var}}`` placeholders from ``prompt_vars`` (missing -> empty)."""
    if not isinstance(value, str) or "{{" not in value:
        return value
    out = value
    for key, val in prompt_vars.items():
        out = out.replace("{{" + str(key) + "}}", "" if val is None else str(val))
    return out


def _build_child_env(injected: dict[str, str]) -> dict[str, str]:
    """Compose the child's environment: minimal OS whitelist + injected vars.

    We deliberately start from an (almost) empty env rather than ``os.environ.copy()`` so
    the agent can't read the daemon's own secrets. Injected ``ctx.env`` values win over
    whitelisted ones (the run may legitimately override e.g. HOME or LANG).
    """
    env: dict[str, str] = {}
    for key in _ENV_WHITELIST:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    # Injected secrets/vars from the run context (already decrypted by the engine).
    for key, val in (injected or {}).items():
        if val is not None:
            env[str(key)] = str(val)
    return env


def _new_process_group_kwargs() -> dict[str, Any]:
    """Spawn the child in its own process group so we can kill the whole tree on timeout.

    POSIX: ``start_new_session=True`` -> the child leads a new session/process group, so
    ``killpg`` reaps grandchildren too. Windows: a new process group via the creation flag
    so ``CTRL_BREAK``/terminate targets the group.
    """
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """Kill a (possibly multi-process) child group started by this adapter."""
    if proc.returncode is not None:
        return
    try:
        if os.name != "nt" and proc.pid is not None:
            # Kill the whole process group (start_new_session made the child the leader).
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
        else:
            proc.kill()
    except ProcessLookupError:
        return
    # Reap so we don't leak a zombie / unawaited transport.
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except (asyncio.TimeoutError, ProcessLookupError):
        pass


def _extract_output(args: list[str], stdout_text: str) -> tuple[str, Optional[Any]]:
    """Return ``(output, parsed_json_or_None)``.

    When ``--output-format json`` was requested (or stdout happens to be valid JSON) we
    parse it; the textual ``output`` is preserved either way so trace/telemetry keep the
    raw bytes while ``parsed`` feeds usage extraction.
    """
    wants_json = _wants_json(args)
    text = stdout_text.strip()
    if (wants_json or _looks_like_json(text)) and text:
        try:
            return stdout_text, json.loads(text)
        except (ValueError, TypeError):
            # Asked for JSON but didn't get it — keep raw text, no parsed object.
            return stdout_text, None
    return stdout_text, None


def _wants_json(args: list[str]) -> bool:
    """True if ``--output-format json`` (in either ``=`` or space form) is present."""
    for i, a in enumerate(args):
        low = a.lower()
        if low == "--output-format" and i + 1 < len(args) and args[i + 1].lower() == "json":
            return True
        if low in ("--output-format=json", "--json", "--format=json"):
            return True
    return False


def _looks_like_json(text: str) -> bool:
    return bool(text) and text[0] in "{["


def _resolve_usage(tool: str, parsed: Optional[Any]) -> Usage:
    """Exact usage from the CLI's own JSON if present, else ccusage, else estimated."""
    if parsed is not None:
        exact = ccusage.usage_from_cli_json(parsed)
        if exact is not None:
            return exact
    return ccusage.read_usage(tool)


def _tool_name(command: str) -> str:
    """Derive the agent CLI family from the command (basename, no extension)."""
    base = os.path.basename(command or "")
    stem, _ext = os.path.splitext(base)
    return (stem or base).lower()


# ── registration ────────────────────────────────────────────────────────────
# Importing this module registers the adapter (auto-discovery imports commands.* which
# imports this); the engine then resolves it via get_adapter("cli").
register_adapter("cli", lambda: CliAdapter())

# Assert at import time that the concrete adapter satisfies the protocol.
_adapter_check: Adapter = CliAdapter()
