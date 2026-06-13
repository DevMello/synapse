"""Group executor — fan one task out across N models in draft mode (§10.4).

The existing Agent Runtime gains a *group executor*: given a pinned context snapshot it
forks **one variant run per model**, bounded by ``max_parallel_variants`` concurrency, each
a normal :class:`~synapse_worker.runtime.engine.RunEngine` run with the §10.5 draft-mode
shim installed (so nothing real happens). Per §10.3 **only the model varies** — every variant
forks from the same manifest/prompt/env/tools. Each variant's telemetry streams up tagged
with ``run_group_id`` / ``variant_model``; when all settle the group is marked
``ready_for_review`` for the human to pick a winner (§10.7).

A group-level **cost cap** (§10.8) hard-stops any not-yet-started variants once the running
aggregate exceeds the cap (variants already in flight finish — each is also bounded by the
agent's own per-run ``max_cost_usd``).
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
import uuid
from typing import Any, Optional

from ..errors import ManifestError
from ..filtering.base import get_filter_chain
from ..logging import get_logger
from ..paths import get_paths
from ..runtime.base import AgentManifest
from ..runtime.engine import RunEngine
from ..runtime.tools import DefaultToolExecutor
from ..store import get_store
from ..uplink import CHANNEL_CONTROL, get_uplink
from .draft_shim import DraftCollector, DraftToolExecutor

log = get_logger(__name__)

_engine = RunEngine()

# group_id -> the variant tasks, so comparison.cancel can target a whole group.
_groups: dict[str, list[asyncio.Task]] = {}
# Groups a cancel has been requested for, so run_group's normal completion does not
# overwrite the terminal "cancelled" status with "ready_for_review" (cancel/finish race).
_cancelled: set[str] = set()


def _new_run_id() -> str:
    # A real UUID: the cloud persists variant runs into `runs.id` (a uuid column), tagged
    # with run_group_id/variant_model by the inbound comparison.variant_finished handler.
    return str(uuid.uuid4())


def _normalize_model(entry: Any) -> dict[str, Optional[str]]:
    """Accept ``"claude-opus-4-7"`` or ``{"provider":..,"model":..}`` -> a {provider,model}."""
    if isinstance(entry, dict):
        return {"provider": entry.get("provider"), "model": str(entry.get("model") or "")}
    return {"provider": None, "model": str(entry)}


async def run_group(
    *,
    group_id: str,
    agent_id: str,
    daemon_id: str,
    models: list[Any],
    input: Optional[dict[str, Any]] = None,
    group_cost_cap: Optional[float] = None,
    max_parallel_variants: int = 3,
) -> None:
    """Launch the comparison: fork a draft variant per model, then mark the group ready."""
    norm = [_normalize_model(m) for m in models if m]
    await _record_group(group_id, agent_id, [m["model"] for m in norm], group_cost_cap)

    manifest = await _load_manifest(agent_id)
    if manifest is None:
        log.warning("agent.compare %s: agent %s not found", group_id, agent_id)
        await _finish_group(group_id, status="closed", total_cost=0.0)
        return
    if manifest.type != "api":
        # API agents only in v1 (E5).
        log.warning("agent.compare %s: agent %s is not an API agent (E5)", group_id, agent_id)
        await _finish_group(group_id, status="closed", total_cost=0.0)
        return

    # Pin ONE context snapshot; every variant forks from it (§10.3).
    payload = input or {}
    prompt_vars = dict(payload.get("prompt_vars") or {})
    if payload.get("prompt") is not None and "prompt" not in prompt_vars:
        prompt_vars["prompt"] = payload["prompt"]
    env = dict(payload.get("env") or {})

    sem = asyncio.Semaphore(max(1, int(max_parallel_variants or 1)))
    state = {"total": 0.0, "stop": False}
    lock = asyncio.Lock()

    async def _variant(spec: dict[str, Optional[str]]) -> None:
        model = spec["model"] or ""
        async with sem:
            # Group cost cap — skip not-yet-started variants once the aggregate blows the cap.
            if state["stop"]:
                await _record_variant_skip(group_id, model)
                await _emit_variant(group_id, _new_run_id(), model, status="skipped")
                return
            run_id = _new_run_id()
            vman = _fork_manifest(manifest, spec)
            collector = DraftCollector()
            executor = DraftToolExecutor(DefaultToolExecutor(), collector, vman.tools)
            await _record_variant_start(group_id, run_id, model)
            started = time.time()
            try:
                result = await _engine.run_agent(
                    manifest=vman,
                    run_id=run_id,
                    prompt_vars=dict(prompt_vars),
                    env=dict(env),
                    tool_executor=executor,
                )
            except Exception as exc:  # noqa: BLE001 - a variant failure never sinks the group
                log.exception("comparison %s variant %s crashed", group_id, model)
                await _record_variant_finish(group_id, run_id, model, None, collector, str(exc))
                await _emit_variant(group_id, run_id, model, status="failed", error=str(exc))
                return
            latency_ms = int((time.time() - started) * 1000)
            await _record_variant_finish(group_id, run_id, model, result, collector, result.error)
            async with lock:
                state["total"] = round(state["total"] + result.usage.cost_usd, 6)
                if group_cost_cap is not None and state["total"] >= float(group_cost_cap):
                    state["stop"] = True
            await _emit_variant(
                group_id,
                run_id,
                model,
                status="succeeded" if result.status == "success" else "failed",
                result=result,
                collector=collector,
                latency_ms=latency_ms,
            )

    tasks = [asyncio.create_task(_variant(spec)) for spec in norm]
    _groups[group_id] = tasks
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        _groups.pop(group_id, None)

    # If a cancel landed while the variants were settling, it already wrote the terminal
    # "cancelled" status — don't clobber it with "ready_for_review".
    if group_id in _cancelled:
        _cancelled.discard(group_id)
        return
    await _finish_group(group_id, status="ready_for_review", total_cost=state["total"])


async def cancel_group(group_id: str) -> None:
    """Cancel all in-flight variants of a group (comparison.cancel, §10.11)."""
    _cancelled.add(group_id)
    tasks = _groups.get(group_id) or []
    for t in tasks:
        if not t.done():
            t.cancel()
    await _finish_group(group_id, status="cancelled", total_cost=None)
    log.info("comparison.cancel: cancelled group %s", group_id)


# ── manifest forking ────────────────────────────────────────────────────────
def _fork_manifest(manifest: AgentManifest, spec: dict[str, Optional[str]]) -> AgentManifest:
    """Clone the base manifest, overriding ONLY [api].provider/[api].model (§10.3)."""
    vman = copy.deepcopy(manifest)
    api = dict(vman.api or {})
    api["model"] = spec["model"]
    if spec.get("provider"):
        api["provider"] = spec["provider"]
    vman.api = api
    return vman


async def _load_manifest(agent_id: str) -> Optional[AgentManifest]:
    """Load the manifest from the stored ``agent.toml`` (preferred) or the agents row."""
    try:
        agent_dir = get_paths().agent_dir(agent_id)
        toml_path = agent_dir / "agent.toml"
        if toml_path.exists():
            return AgentManifest.from_toml(toml_path.read_text(encoding="utf-8"))
    except (ManifestError, OSError) as exc:
        log.warning("comparison: bad agent.toml for %s: %s", agent_id, exc)
    except Exception:  # noqa: BLE001 - paths/settings may be unavailable in some contexts
        pass
    try:
        row = await get_store().fetchone("SELECT manifest FROM agents WHERE id=?", (agent_id,))
    except Exception:  # noqa: BLE001
        return None
    if row and row.get("manifest"):
        try:
            return AgentManifest.from_toml(row["manifest"])
        except ManifestError:
            return None
    return None


# ── persistence ─────────────────────────────────────────────────────────────
async def _record_group(
    group_id: str, agent_id: str, models: list[Optional[str]], cap: Optional[float]
) -> None:
    try:
        await get_store().execute(
            "INSERT INTO comparison_groups"
            " (group_id, agent_id, models, status, cost_cap, total_cost, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(group_id) DO UPDATE SET agent_id=excluded.agent_id,"
            " models=excluded.models, status='running', cost_cap=excluded.cost_cap,"
            " updated_at=excluded.updated_at",
            (group_id, agent_id, json.dumps(models), "running", cap, 0.0, time.time(), time.time()),
        )
    except Exception:  # noqa: BLE001 - persistence must not abort the comparison
        log.exception("comparison %s: failed to record group", group_id)


async def _finish_group(group_id: str, *, status: str, total_cost: Optional[float]) -> None:
    try:
        if total_cost is None:
            await get_store().execute(
                "UPDATE comparison_groups SET status=?, updated_at=? WHERE group_id=?",
                (status, time.time(), group_id),
            )
        else:
            await get_store().execute(
                "UPDATE comparison_groups SET status=?, total_cost=?, updated_at=? WHERE group_id=?",
                (status, total_cost, time.time(), group_id),
            )
    except Exception:  # noqa: BLE001
        log.exception("comparison %s: failed to finish group", group_id)
    # Group status rides the control channel (§10.11).
    try:
        body = {"group_id": group_id, "status": status}
        if total_cost is not None:
            body["total_cost_usd"] = total_cost
        await get_uplink().send("comparison.group_ready", body, channel=CHANNEL_CONTROL)
    except Exception:  # noqa: BLE001
        log.exception("comparison %s: failed to emit group status", group_id)


async def _record_variant_start(group_id: str, run_id: str, model: str) -> None:
    try:
        await get_store().execute(
            "INSERT INTO comparison_variants (run_id, group_id, model, status, started_at)"
            " VALUES (?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET status='running'",
            (run_id, group_id, model, "running", time.time()),
        )
    except Exception:  # noqa: BLE001
        log.exception("comparison %s: failed to record variant start", group_id)


async def _record_variant_skip(group_id: str, model: str) -> None:
    try:
        await get_store().execute(
            "INSERT INTO comparison_variants (run_id, group_id, model, status, started_at, finished_at)"
            " VALUES (?,?,?,?,?,?)",
            (_new_run_id(), group_id, model, "skipped", time.time(), time.time()),
        )
    except Exception:  # noqa: BLE001
        log.exception("comparison %s: failed to record variant skip", group_id)


async def _record_variant_finish(
    group_id: str,
    run_id: str,
    model: str,
    result: Any,
    collector: DraftCollector,
    error: Optional[str],
) -> None:
    cost = result.usage.cost_usd if result else 0.0
    tin = result.usage.input_tokens if result else 0
    tout = result.usage.output_tokens if result else 0
    output = _redact(result.output if result else "")
    status = "succeeded" if (result and result.status == "success") else "failed"
    try:
        store = get_store()
        await store.execute(
            "UPDATE comparison_variants SET status=?, cost_usd=?, tokens_in=?, tokens_out=?,"
            " output=?, error=?, finished_at=? WHERE run_id=?",
            (status, cost, tin, tout, output, error, time.time(), run_id),
        )
        for pa in collector.proposed_actions:
            await store.execute(
                "INSERT INTO comparison_proposed_actions"
                " (run_id, group_id, name, args_redacted, hitl, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (run_id, group_id, pa.get("name"), json.dumps(pa.get("args_redacted")),
                 1 if pa.get("hitl") else 0, time.time()),
            )
        for h in collector.simulated_hitl:
            await store.execute(
                "INSERT INTO comparison_sim_hitl (run_id, group_id, name, args_redacted, created_at)"
                " VALUES (?,?,?,?,?)",
                (run_id, group_id, h.get("name"), json.dumps(h.get("args_redacted")), time.time()),
            )
    except Exception:  # noqa: BLE001
        log.exception("comparison %s: failed to record variant finish", group_id)


# ── upstream telemetry (tagged with run_group_id / variant_model) ─────────────
async def _emit_variant(
    group_id: str,
    run_id: str,
    model: str,
    *,
    status: str,
    result: Any = None,
    collector: Optional[DraftCollector] = None,
    error: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> None:
    body: dict[str, Any] = {
        "run_group_id": group_id,
        "run_id": run_id,
        "variant_model": model,
        "status": status,
    }
    if result is not None:
        body.update(
            {
                "cost_usd": result.usage.cost_usd,
                "tokens_in": result.usage.input_tokens,
                "tokens_out": result.usage.output_tokens,
                "output_redacted": _redact(result.output),
                "error": result.error,
            }
        )
    if error is not None:
        body["error"] = error
    if latency_ms is not None:
        body["latency_ms"] = latency_ms
    if collector is not None:
        body["proposed_actions"] = collector.proposed_actions
        body["simulated_hitl"] = collector.simulated_hitl
        body["tool_calls"] = collector.tool_calls
    try:
        await get_uplink().send("comparison.variant_finished", body, channel=CHANNEL_CONTROL)
    except Exception:  # noqa: BLE001
        log.exception("comparison %s: failed to emit variant", group_id)


def _redact(text: Optional[str]) -> str:
    if not text:
        return ""
    try:
        return get_filter_chain().screen_outbound(str(text)).text
    except Exception:  # noqa: BLE001 - redaction must not abort recording
        return str(text)
