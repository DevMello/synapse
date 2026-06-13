"""Run engine: execute one agent run end to end (§4.3).

The :class:`RunEngine` is the orchestration seam between an inbound ``agent.run``
command and a registered :class:`~synapse_worker.runtime.base.Adapter`. It owns the
cross-cutting concerns that are identical for every agent type:

  * build a :class:`RunContext` whose ``emit`` callback fans a trace event to the local
    TUI event bus AND ships a *redacted* telemetry frame upstream;
  * render the prompt (``{{var}}`` substitution) from the agent dir / ``prompt_vars``;
  * select the adapter by ``manifest.type`` and invoke it;
  * a best-effort, post-hoc ``max_cost_usd`` check (hard mid-run enforcement is the
    ruleset unit's job — §4.6);
  * persist the run lifecycle to ``run_history`` (running -> terminal);
  * emit ``run.finished`` on the control channel with the cloud's exact key shape.

Robustness contract: ``run_agent`` never raises. Any adapter failure, missing adapter,
or persistence hiccup is folded into a ``failed`` terminal state so the control loop and
the scheduler stay alive.
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from ..events import Event, get_event_bus
from ..filtering.base import get_filter_chain
from ..logging import get_logger
from ..paths import get_paths
from ..store import get_store
from ..uplink import CHANNEL_CONTROL, CHANNEL_TELEMETRY, get_uplink
from .base import AgentManifest, RunContext, RunResult, Usage, get_adapter, has_adapter

log = get_logger(__name__)

# Map the adapter-level RunResult.status vocabulary onto the cloud's run.finished
# vocabulary. The cloud reads exactly these strings (default "succeeded").
_STATUS_TO_WIRE = {
    "success": "succeeded",
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
    "paused": "paused",
}

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def render_template(text: str, prompt_vars: dict[str, Any]) -> str:
    """Substitute ``{{var}}`` tokens from ``prompt_vars`` (unknown tokens left as-is)."""

    def _sub(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key in prompt_vars:
            return str(prompt_vars[key])
        return match.group(0)

    return _VAR_RE.sub(_sub, text)


class RunEngine:
    """Executes a single agent run; reused across all inbound runs (stateless)."""

    async def run_agent(
        self,
        *,
        manifest: AgentManifest,
        run_id: str,
        prompt_vars: dict[str, Any],
        env: Optional[dict[str, str]] = None,
        tool_executor: Optional[Any] = None,
    ) -> RunResult:
        prompt_vars = dict(prompt_vars or {})
        env = dict(env or {})
        # Pre-render the prompt so the adapter receives ready-to-send text and the
        # "prompt" trace reflects exactly what was sent.
        prompt_vars.setdefault("prompt", self._render_prompt(manifest, prompt_vars))

        ctx = RunContext(
            run_id=run_id,
            agent_id=manifest.id,
            manifest=manifest,
            prompt_vars=prompt_vars,
            env=env,
            emit=self._make_emit(run_id, manifest.id),
            # §10: a comparison variant injects a draft-mode tool shim so side-effecting
            # tool calls are simulated, not executed. None -> adapter's default executor.
            tool_executor=tool_executor,
        )

        await self._record_start(run_id, manifest.id)

        # No adapter for this type -> graceful failure (never raise out of run_agent).
        if not has_adapter(manifest.type):
            error = f"no adapter registered for agent type {manifest.type!r}"
            log.warning("run %s: %s", run_id, error)
            result = RunResult(status="failed", error=error)
            await self._finish(run_id, result)
            return result

        result: RunResult
        try:
            adapter = get_adapter(manifest.type)
            result = await adapter.run(ctx)
        except Exception as exc:  # noqa: BLE001 - any adapter failure -> failed run
            log.exception("run %s: adapter raised", run_id)
            result = RunResult(status="failed", error=str(exc))
            await self._finish(run_id, result)
            return result

        # Soft, post-hoc cost cap. Hard mid-run enforcement belongs to the ruleset unit
        # (§4.6); here we only flip an over-budget run to failed after the fact.
        cap = manifest.max_cost_usd
        if cap is not None and result.usage.cost_usd > cap and result.status != "failed":
            msg = f"cost ${result.usage.cost_usd:.4f} exceeded cap ${cap:.4f}"
            log.warning("run %s: %s", run_id, msg)
            result = RunResult(
                status="failed",
                usage=result.usage,
                output=result.output,
                error=msg,
            )

        await self._finish(run_id, result)
        return result

    # ── prompt rendering ──────────────────────────────────────────────────
    def _render_prompt(self, manifest: AgentManifest, prompt_vars: dict[str, Any]) -> str:
        """Read the agent's prompt file if present, else fall back to ``prompt_vars``.

        Source precedence: ``<agent_dir>/prompt.md`` (or ``.txt``) -> the raw
        ``prompt_vars["prompt"]`` -> empty string. The result is ``{{var}}``-rendered.
        """
        raw = self._read_prompt_file(manifest.id)
        if raw is None:
            raw = str(prompt_vars.get("prompt", ""))
        return render_template(raw, prompt_vars)

    def _read_prompt_file(self, agent_id: str) -> Optional[str]:
        try:
            agent_dir = get_paths().agent_dir(agent_id)
        except Exception:  # noqa: BLE001 - settings/paths not available in some tests
            return None
        for name in ("prompt.md", "prompt.txt"):
            candidate = agent_dir / name
            if candidate.exists():
                try:
                    return candidate.read_text(encoding="utf-8")
                except OSError:  # pragma: no cover - unreadable file
                    return None
        return None

    # ── emit callback: local fan-out + redacted upstream telemetry ────────
    def _make_emit(self, run_id: str, agent_id: str):
        bus = get_event_bus()
        chain = get_filter_chain()
        uplink = get_uplink()

        async def emit(event) -> None:  # event: TraceEvent
            # (a) Local TUI fan-out — never blocks, never redacted (on-device pane).
            await bus.publish(
                Event(
                    kind="trace",
                    data=event.to_payload(),
                    run_id=run_id,
                    agent_id=agent_id,
                )
            )
            # (b) Upstream telemetry — content MUST pass through the filter chain first
            # so redaction "just works" once that unit lands (pass-through until then).
            content = event.data.get("content")
            if content is None:
                return
            redacted = chain.screen_outbound(str(content)).text
            await uplink.send(
                "telemetry.trace",
                {
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "role": event.data.get("role", event.kind),
                    "content_redacted": redacted,
                },
                channel=CHANNEL_TELEMETRY,
            )

        return emit

    # ── run_history persistence ───────────────────────────────────────────
    async def _record_start(self, run_id: str, agent_id: str) -> None:
        try:
            store = get_store()
            # INSERT on start; if the row somehow exists (retry), reset it to running.
            await store.execute(
                "INSERT INTO run_history (run_id, agent_id, status, started_at)"
                " VALUES (?,?,?,?)"
                " ON CONFLICT(run_id) DO UPDATE SET"
                " agent_id=excluded.agent_id, status='running',"
                " started_at=excluded.started_at",
                (run_id, agent_id, "running", time.time()),
            )
        except Exception:  # noqa: BLE001 - persistence must not abort the run
            log.exception("run %s: failed to record start", run_id)

    async def _finish(self, run_id: str, result: RunResult) -> None:
        usage = result.usage or Usage()
        wire_status = _STATUS_TO_WIRE.get(result.status, result.status)
        await self._record_finish(run_id, wire_status, usage, result.error)
        await self._emit_run_finished(run_id, wire_status, usage)

    async def _record_finish(
        self, run_id: str, status: str, usage: Usage, error: Optional[str]
    ) -> None:
        try:
            store = get_store()
            await store.execute(
                "UPDATE run_history SET status=?, cost_usd=?, tokens_input=?,"
                " tokens_output=?, finished_at=?, detail=? WHERE run_id=?",
                (
                    status,
                    usage.cost_usd,
                    usage.input_tokens,
                    usage.output_tokens,
                    time.time(),
                    error,
                    run_id,
                ),
            )
        except Exception:  # noqa: BLE001
            log.exception("run %s: failed to record finish", run_id)

    async def _emit_run_finished(self, run_id: str, status: str, usage: Usage) -> None:
        try:
            await get_uplink().send(
                "run.finished",
                {
                    "run_id": run_id,
                    "status": status,
                    "cost_usd": usage.cost_usd,
                    "tokens_in": usage.input_tokens,
                    "tokens_out": usage.output_tokens,
                },
                channel=CHANNEL_CONTROL,
            )
        except Exception:  # noqa: BLE001
            log.exception("run %s: failed to emit run.finished", run_id)
