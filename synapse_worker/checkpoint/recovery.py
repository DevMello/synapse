"""Resume logic, org-recovery-key E2E sync, and boot-time auto-resume (§4.12).

Three concerns layered over the :class:`CheckpointJournal`:

  * **Resume planning** (:func:`plan_resume`) — read the journal and decide, per step,
    whether it's already done (skip), interrupted-but-safe (re-run), or interrupted-and-
    dangerous (gate for HITL). Honors the agent's resume policy.
  * **Cloud sync** (:func:`sync_checkpoint`) — seal each new checkpoint to the *org
    recovery public key* and emit ``run.checkpoint`` upstream. Zero-knowledge: the cloud
    stores opaque ciphertext + plaintext metadata only. Incremental + best-effort.
  * **Auto-resume on boot** (:func:`auto_resume_all`) — find interrupted runs in
    ``run_history`` and produce resume plans, registered as a background service that
    runs once then idles.

Crypto reuses the env-var sealed-box pattern (§4.10): the org recovery keypair lives in
the keystore under service ``"synapse:daemon"`` (keys ``org_recovery_public_key`` /
``org_recovery_private_key``). If a key is unset we skip gracefully and log once — the
daemon must keep running and never crash on a missing recovery key.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .. import crypto
from ..logging import get_logger
from ..store import LocalStore, get_store
from ..uplink import CHANNEL_CONTROL, get_uplink
from .journal import STATUS_COMMITTED, CheckpointJournal

log = get_logger(__name__)

# Keystore coordinates for the org recovery keypair (written by the auth unit).
KEYSTORE_SERVICE = "synapse:daemon"
ORG_PUBLIC_KEY = "org_recovery_public_key"
ORG_PRIVATE_KEY = "org_recovery_private_key"

# Resume policies (§4.12). Read from the manifest defensively; default auto-resume.
POLICY_AUTO = "auto-resume"
POLICY_APPROVAL = "resume-with-approval"
POLICY_RESTART = "restart"
POLICY_ABORT = "abort"

# Per-step resume decisions.
DECISION_SKIP = "skip"        # intent + result present -> already done
DECISION_RERUN = "rerun"      # interrupted, tool idempotent -> safe to replay
DECISION_GATE = "gate"        # interrupted, NOT idempotent -> pause for HITL

# Run-disposition for the whole plan (drives what the engine does next).
RESUME = "resume"
RESTART = "restart"
ABORT = "abort"

# Run statuses that mean "this run is finished" (not a resume candidate).
_TERMINAL = {"finished", "success", "failed", "cancelled", "aborted"}

# Track which missing-key warnings we've already emitted so we log at most once.
_warned: set[str] = set()


def _warn_once(token: str, msg: str, *args: Any) -> None:
    if token not in _warned:
        _warned.add(token)
        log.warning(msg, *args)


def reset_warnings() -> None:  # test helper
    _warned.clear()


@dataclass
class StepDecision:
    """One step's resume disposition, derived from its journal row."""

    seq: int
    step_cursor: Optional[int]
    decision: str  # skip | rerun | gate
    idempotency_key: Optional[str] = None
    reason: str = ""


@dataclass
class ResumePlan:
    """The plan for resuming a single run from its journal."""

    run_id: str
    disposition: str = RESUME  # resume | restart | abort
    policy: str = POLICY_AUTO
    resume_cursor: int = 0       # the step cursor to continue from
    steps: list[StepDecision] = field(default_factory=list)
    requires_approval: bool = False  # any gated step OR resume-with-approval policy

    @property
    def gated(self) -> list[StepDecision]:
        return [s for s in self.steps if s.decision == DECISION_GATE]

    @property
    def rerun(self) -> list[StepDecision]:
        return [s for s in self.steps if s.decision == DECISION_RERUN]

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "disposition": self.disposition,
            "policy": self.policy,
            "resume_cursor": self.resume_cursor,
            "requires_approval": self.requires_approval,
            "steps": [
                {
                    "seq": s.seq,
                    "step_cursor": s.step_cursor,
                    "decision": s.decision,
                    "reason": s.reason,
                }
                for s in self.steps
            ],
        }


# ── idempotency / payload helpers ───────────────────────────────────────────
def _has_result(payload: dict[str, Any]) -> bool:
    """A step is *complete* once its committed result is recorded.

    We accept either an explicit ``result`` key or an explicit ``committed`` flag so the
    runtime's exact payload shape can evolve without breaking resume.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("result") is not None:
        return True
    tool = payload.get("tool_call")
    if isinstance(tool, dict) and tool.get("result") is not None:
        return True
    return False


def _step_is_idempotent(payload: dict[str, Any]) -> bool:
    """Whether the in-flight tool call is declared idempotent (safe to replay).

    Read defensively from a few likely locations in the checkpoint payload; default
    ``False`` (the safe choice — an unknown side effect is gated, never blindly repeated).
    """
    if not isinstance(payload, dict):
        return False
    if "idempotent" in payload:
        return bool(payload.get("idempotent"))
    tool = payload.get("tool_call")
    if isinstance(tool, dict) and "idempotent" in tool:
        return bool(tool.get("idempotent"))
    return False


def _idem_key(payload: dict[str, Any]) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    if payload.get("idempotency_key"):
        return str(payload["idempotency_key"])
    tool = payload.get("tool_call")
    if isinstance(tool, dict) and tool.get("idempotency_key"):
        return str(tool["idempotency_key"])
    return None


async def _resume_policy_for(run_id: str, store: LocalStore) -> str:
    """Resolve the agent's resume policy for ``run_id`` (default ``auto-resume``).

    Looks up the run's agent and reads its stored manifest, honoring a ``[resume].policy``
    or ``[limits].resume_policy`` key. Read defensively — a missing manifest/field falls
    back to auto-resume so recovery still works for minimally-described agents.
    """
    try:
        run = await store.fetchone(
            "SELECT agent_id FROM run_history WHERE run_id=?", (run_id,)
        )
        if not run or not run.get("agent_id"):
            return POLICY_AUTO
        agent = await store.fetchone(
            "SELECT manifest FROM agents WHERE id=?", (run["agent_id"],)
        )
        if not agent or not agent.get("manifest"):
            return POLICY_AUTO
        return _policy_from_manifest_text(agent["manifest"])
    except Exception:  # noqa: BLE001 - policy lookup must never break resume
        return POLICY_AUTO


def _policy_from_manifest_text(text: str) -> str:
    """Extract a resume policy from agent.toml text (``[resume]`` or ``[limits]``)."""
    try:
        from ..runtime.base import tomllib

        if tomllib is None:  # pragma: no cover - py<3.11
            return POLICY_AUTO
        data = tomllib.loads(text)
    except Exception:  # noqa: BLE001
        return POLICY_AUTO
    resume = data.get("resume") if isinstance(data, dict) else None
    if isinstance(resume, dict) and resume.get("policy"):
        return _normalize_policy(resume["policy"])
    limits = data.get("limits") if isinstance(data, dict) else None
    if isinstance(limits, dict) and limits.get("resume_policy"):
        return _normalize_policy(limits["resume_policy"])
    return POLICY_AUTO


def _normalize_policy(value: Any) -> str:
    p = str(value).strip().lower().replace("_", "-")
    return p if p in (POLICY_AUTO, POLICY_APPROVAL, POLICY_RESTART, POLICY_ABORT) else POLICY_AUTO


# ── resume planning ─────────────────────────────────────────────────────────
async def plan_resume(
    run_id: str,
    *,
    store: Optional[LocalStore] = None,
    journal: Optional[CheckpointJournal] = None,
    policy: Optional[str] = None,
) -> ResumePlan:
    """Derive a :class:`ResumePlan` for ``run_id`` from its checkpoint journal (§4.12).

    Per step:
      * intent AND result      -> SKIP   (already done; no re-run, no duplicate effect)
      * intent but NO result   -> idempotent ? RERUN : GATE (HITL "did this happen?")

    The agent's resume policy shapes the whole-run disposition:
      * ``restart`` -> disposition RESTART (throw the journal away, start fresh)
      * ``abort``   -> disposition ABORT
      * ``resume-with-approval`` -> resume but requires_approval=True
      * ``auto-resume`` (default) -> resume; requires_approval only if a step is gated.
    """
    st = store if store is not None else get_store()
    jrnl = journal if journal is not None else CheckpointJournal(st)
    eff_policy = policy if policy is not None else await _resume_policy_for(run_id, st)

    plan = ResumePlan(run_id=run_id, policy=eff_policy)

    if eff_policy == POLICY_RESTART:
        plan.disposition = RESTART
        plan.resume_cursor = 0
        return plan
    if eff_policy == POLICY_ABORT:
        plan.disposition = ABORT
        return plan

    # The write-ahead protocol writes TWO rows per tool call: an `intent` row
    # (status in_flight) BEFORE the call, then a `result` row (status committed) AFTER.
    # Both share the same `step_cursor`. We must therefore decide per *logical step*
    # (grouped by step_cursor), not per row: a step is DONE if ANY of its rows carries a
    # result/committed status — otherwise the intent row of a completed call would be
    # spuriously gated/re-run. Rows with no step_cursor are treated as their own step
    # (keyed by seq) so a minimally-described journal still works.
    history = await jrnl.history(run_id)
    groups: "dict[Any, list[dict[str, Any]]]" = {}
    order: list[Any] = []
    for row in history:
        cursor = row.get("step_cursor")
        key = cursor if isinstance(cursor, int) else ("seq", int(row["seq"]))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    for key in order:
        rows = groups[key]
        # Representative seq/cursor for the step: the latest row carries the freshest state.
        last = rows[-1]
        cursor = last.get("step_cursor")
        seq = int(last["seq"])
        done = any(
            _has_result(r.get("payload") or {}) or r.get("status") == STATUS_COMMITTED
            for r in rows
        )

        if done:
            plan.steps.append(
                StepDecision(seq=seq, step_cursor=cursor, decision=DECISION_SKIP,
                             reason="result recorded")
            )
            # Advance the resume cursor past every completed step.
            if isinstance(cursor, int):
                plan.resume_cursor = max(plan.resume_cursor, cursor)
            continue

        # Intent recorded but no result anywhere for this step -> crash mid-tool.
        # Idempotency is the safety gate (declaration taken from any row in the step).
        idempotent = any(_step_is_idempotent(r.get("payload") or {}) for r in rows)
        idem_key = next((_idem_key(r.get("payload") or {}) for r in rows if _idem_key(r.get("payload") or {})), None)
        if idempotent:
            plan.steps.append(
                StepDecision(seq=seq, step_cursor=cursor, decision=DECISION_RERUN,
                             idempotency_key=idem_key,
                             reason="idempotent tool; safe to replay")
            )
        else:
            plan.steps.append(
                StepDecision(seq=seq, step_cursor=cursor, decision=DECISION_GATE,
                             idempotency_key=idem_key,
                             reason="non-idempotent in-flight tool; HITL required")
            )

    plan.requires_approval = bool(plan.gated) or eff_policy == POLICY_APPROVAL
    return plan


# ── cloud sync (E2E, zero-knowledge) ────────────────────────────────────────
async def sync_checkpoint(
    run_id: str,
    agent_id: str,
    *,
    store: Optional[LocalStore] = None,
    journal: Optional[CheckpointJournal] = None,
) -> int:
    """Seal + emit every *new* checkpoint for ``run_id`` upstream. Returns the count sent.

    Incremental: we track the last-synced seq per run in ``kv`` and only ship rows with a
    higher seq. Best-effort: if the org recovery public key is unset, or sealing/sending
    fails, we log and return 0 without raising — checkpoints stay durable locally and a
    later call retries from the same watermark.
    """
    st = store if store is not None else get_store()
    jrnl = journal if journal is not None else CheckpointJournal(st)

    pub = crypto.get_keystore().get(KEYSTORE_SERVICE, ORG_PUBLIC_KEY)
    if not pub:
        # No org recovery key configured (key not yet provisioned). Skip gracefully.
        _warn_once(
            "no-org-pub",
            "org recovery public key unset; skipping checkpoint cloud sync (logged once)",
        )
        return 0

    watermark_key = f"checkpoint:synced_seq:{run_id}"
    last_synced = int(await st.kv_get(watermark_key) or 0)
    new_rows = await jrnl.since(run_id, last_synced)
    if not new_rows:
        return 0

    uplink = get_uplink()
    sent = 0
    for row in new_rows:
        seq = int(row["seq"])
        payload = row.get("payload") or {}
        try:
            # Seal the FULL session-state payload to the org recovery key. Only opaque
            # ciphertext leaves the box; the metadata below is non-sensitive (§4.12).
            blob = crypto.seal(pub, _plaintext_bytes(payload))
        except Exception:  # noqa: BLE001 - a bad key shouldn't kill the run
            _warn_once("seal-fail", "failed to seal checkpoint for cloud sync (logged once)")
            return sent
        frame = {
            "run_id": run_id,
            "agent_id": agent_id,
            "seq": seq,
            "step_cursor": row.get("step_cursor"),
            "status": row.get("status"),
            "cost_so_far_usd": _cost_of(payload),
            "payload_b64": blob,
        }
        try:
            await uplink.send("run.checkpoint", frame, channel=CHANNEL_CONTROL)
        except Exception:  # noqa: BLE001 - best-effort while online; retry next call
            log.debug("run.checkpoint send failed at seq=%s; will retry", seq)
            return sent
        # Advance the watermark only after a successful enqueue so a failure replays it.
        await st.kv_set(watermark_key, seq)
        sent += 1
    return sent


def _plaintext_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _cost_of(payload: dict[str, Any]) -> float:
    """Pull cumulative cost out of the checkpoint's accounting block (default 0.0)."""
    if not isinstance(payload, dict):
        return 0.0
    for key in ("cost_so_far_usd", "cost_usd"):
        if payload.get(key) is not None:
            try:
                return float(payload[key])
            except (TypeError, ValueError):
                return 0.0
    acct = payload.get("accounting")
    if isinstance(acct, dict) and acct.get("cost_usd") is not None:
        try:
            return float(acct["cost_usd"])
        except (TypeError, ValueError):
            return 0.0
    return 0.0


# ── cloud recovery: decrypt a last-known-good checkpoint ─────────────────────
def open_recovery_blob(ciphertext_b64: str) -> Optional[dict[str, Any]]:
    """Decrypt a sealed checkpoint blob with the org recovery PRIVATE key.

    Returns the restored session-state payload, or ``None`` if the private key is unset
    or decryption/parsing fails (caller logs + degrades; we never raise into dispatch).
    """
    priv = crypto.get_keystore().get(KEYSTORE_SERVICE, ORG_PRIVATE_KEY)
    if not priv:
        _warn_once(
            "no-org-priv",
            "org recovery private key unset; cannot decrypt recovery blob (logged once)",
        )
        return None
    try:
        plaintext = crypto.seal_open(priv, ciphertext_b64)
        data = json.loads(plaintext.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 - tamper / wrong key / bad json
        log.warning("failed to open recovery checkpoint blob")
        return None


# ── boot-time auto-resume ────────────────────────────────────────────────────
async def auto_resume_all(
    store: Optional[LocalStore] = None,
) -> list[ResumePlan]:
    """Find interrupted runs and produce a resume plan for each (§4.12 boot path).

    An *interrupted* run is one whose ``run_history`` status is still active (running /
    not terminal) but which has no live process — true on a fresh boot, where nothing is
    running yet. We never spawn work here; we only compute plans (the engine acts on
    them). Returns the plans so the caller/TUI can surface them.
    """
    st = store if store is not None else get_store()
    plans: list[ResumePlan] = []
    try:
        rows = await st.fetchall(
            "SELECT run_id FROM run_history"
            " WHERE status IS NULL OR status NOT IN"
            "   ('finished','success','failed','cancelled','aborted')"
        )
    except Exception:  # noqa: BLE001 - missing/locked table -> nothing to resume
        log.debug("auto_resume_all: run_history query failed; nothing to resume")
        return plans

    journal = CheckpointJournal(st)
    for row in rows:
        run_id = row["run_id"]
        if not run_id:
            continue
        try:
            plan = await plan_resume(run_id, store=st, journal=journal)
        except Exception:  # noqa: BLE001 - one bad run can't block the rest
            log.exception("auto_resume_all: failed to plan resume for run %s", run_id)
            continue
        plans.append(plan)
    log.info("auto_resume_all: planned resume for %d interrupted run(s)", len(plans))
    return plans
