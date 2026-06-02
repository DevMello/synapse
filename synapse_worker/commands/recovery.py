"""``run.recover`` command handler + boot auto-resume service (§4.12).

``app.build_daemon`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this file registers:

  * the ``@on_command("run.recover")`` handler — the cloud asks this daemon to *adopt and
    resume* an interrupted run from its last-known-good (E2E-encrypted) checkpoint, and
  * the ``checkpoint_recovery`` background service — on boot it runs ``auto_resume_all``
    once (to plan resumes for any run interrupted by a process crash) then idles, so it
    never blocks the daemon's task group.

``run.recover`` payload (cloud is the wire source of truth; read defensively)::

    {
      "run_id":          "<run id>",          # REQUIRED
      "agent_id":        "<agent id>",
      "agent_version":   <int>,               # optional
      "seq":             <int>,               # optional, seq of the supplied checkpoint
      "step_cursor":     <int>,               # optional
      "payload_b64":     "<sealed base64>",   # inline last-known-good ciphertext, OR
      "blob_b64":        "<sealed base64>",   # alias the cloud may use, OR
      "payload_blob_ref":"<url|ref>"          # a reference to fetch from cloud storage
    }

Restore is **safety-preserving**: we decrypt the blob with the org recovery PRIVATE key,
write it back into the local journal at its original seq, then build a resume plan that
honors the idempotency/HITL check (§4.12) — a non-idempotent in-flight tool is *gated*,
never blindly repeated.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from ..checkpoint.journal import CheckpointJournal
from ..checkpoint.recovery import (
    auto_resume_all,
    open_recovery_blob,
    plan_resume,
)
from ..logging import get_logger
from ..router import CommandContext, on_command
from ..services import register_service
from ..store import get_store

log = get_logger(__name__)


@on_command("run.recover")
async def handle_run_recover(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Adopt + resume an interrupted run from its last-known-good checkpoint.

    Idempotent and crash-safe: a missing run_id, an unset org recovery key, or a blob we
    can't fetch all degrade to a logged no-op rather than raising into the control loop.
    """
    run_id = payload.get("run_id") or getattr(ctx, "run_id", None)
    if not run_id:
        log.warning("run.recover: missing run_id; ignoring")
        return
    agent_id = payload.get("agent_id") or getattr(ctx, "agent_id", None) or ""

    store = get_store()
    journal = CheckpointJournal(store)

    # 1. Obtain the last-known-good checkpoint payload.
    restored = await _restore_checkpoint(run_id, payload, journal)

    # 2. Make sure run_history has a row so reconcile/resume can see this adopted run.
    await _ensure_run_row(run_id, agent_id, payload)

    # 3. Build a resume plan honoring the idempotency/HITL safety check.
    plan = await plan_resume(run_id, store=store, journal=journal)

    log.info(
        "run.recover: adopted run=%s agent=%s (restored=%s, disposition=%s, gated=%d)",
        run_id,
        agent_id,
        bool(restored),
        plan.disposition,
        len(plan.gated),
    )
    # Surface the plan so the cloud/TUI knows what we'll do. Best-effort.
    try:
        from ..uplink import CHANNEL_CONTROL, get_uplink

        await get_uplink().send(
            "run.recover.ack",
            {"run_id": run_id, "agent_id": agent_id, "plan": plan.to_payload()},
            channel=CHANNEL_CONTROL,
        )
    except Exception:  # noqa: BLE001 - ack is informational; never fail recovery on it
        log.debug("run.recover: failed to emit recover ack for run %s", run_id)


async def _restore_checkpoint(
    run_id: str, payload: dict[str, Any], journal: CheckpointJournal
) -> bool:
    """Decrypt + write the last-known-good checkpoint into the local journal.

    Returns True if a checkpoint was restored. Inline ciphertext (``payload_b64`` /
    ``blob_b64``) is decrypted directly; a bare ``payload_blob_ref`` is fetched on a
    best-effort seam (see :func:`_fetch_blob_ref`).
    """
    blob_b64 = payload.get("payload_b64") or payload.get("blob_b64")
    if not blob_b64:
        ref = payload.get("payload_blob_ref")
        if ref:
            blob_b64 = await _fetch_blob_ref(str(ref))
    if not blob_b64:
        log.info("run.recover: no inline/fetchable checkpoint blob for run %s", run_id)
        return False

    session_state = open_recovery_blob(str(blob_b64))
    if session_state is None:
        return False  # unset private key or undecryptable — already logged

    seq = _coerce_int(payload.get("seq"))
    step_cursor = _coerce_int(payload.get("step_cursor"))
    if step_cursor is None:
        step_cursor = _coerce_int(session_state.get("step_cursor")) or 0
    status = str(session_state.get("status") or "committed")

    # Preserve the originating seq so reconcile/dedupe stay aligned with the cloud.
    if seq is not None:
        await journal.append_at(run_id, seq, step_cursor, status, session_state)
    else:
        await journal.append(run_id, step_cursor, status, session_state)
    return True


async def _fetch_blob_ref(ref: str) -> Optional[str]:
    """Best-effort fetch of a checkpoint blob referenced by ``payload_blob_ref``.

    Documented seam: when the ref is an http(s) URL we GET it (the cloud may hand back a
    signed URL to its opaque-ciphertext store). Anything else (an opaque storage key the
    daemon would resolve via the cloud API) is logged as needing a fetch and skipped —
    wiring that resolution is the cloud-storage unit's job, not this one's. We never raise.
    """
    if not (ref.startswith("http://") or ref.startswith("https://")):
        log.info(
            "run.recover: payload_blob_ref %r is not a URL; blob fetch deferred to cloud-storage seam",
            ref,
        )
        return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(ref)
            resp.raise_for_status()
            return resp.text.strip()
    except Exception:  # noqa: BLE001 - network/import failure -> degrade gracefully
        log.warning("run.recover: failed to fetch checkpoint blob from ref")
        return None


async def _ensure_run_row(
    run_id: str, agent_id: str, payload: dict[str, Any]
) -> None:
    """Insert a minimal ``run_history`` row for an adopted run if none exists.

    Marks it ``running`` so reconcile/auto-resume treat it as in-flight. Best-effort —
    a failure here must not abort the recovery.
    """
    try:
        store = get_store()
        existing = await store.fetchone(
            "SELECT run_id FROM run_history WHERE run_id=?", (run_id,)
        )
        if existing:
            return
        import time as _time

        await store.execute(
            "INSERT INTO run_history (run_id, agent_id, status, started_at, detail)"
            " VALUES (?,?,?,?,?)",
            (run_id, agent_id, "running", _time.time(), "adopted via run.recover"),
        )
    except Exception:  # noqa: BLE001 - audit row is best-effort
        log.debug("run.recover: could not ensure run_history row for %s", run_id)


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ── boot-time auto-resume service ───────────────────────────────────────────
class CheckpointRecoveryService:
    """Runs ``auto_resume_all`` once at boot, then idles (never blocks the task group)."""

    def __init__(self, daemon: Any = None) -> None:
        self._daemon = daemon
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        try:
            plans = await auto_resume_all()
            if plans:
                log.info(
                    "checkpoint_recovery: %d interrupted run(s) have resume plans", len(plans)
                )
        except Exception:  # noqa: BLE001 - boot recovery must not crash the daemon
            log.exception("checkpoint_recovery: auto-resume sweep failed")
        # Idle until shutdown so the service stays alive without busy-looping.
        await self._stopped.wait()

    async def stop(self) -> None:
        self._stopped.set()


@register_service("checkpoint_recovery")
def make_checkpoint_recovery(daemon: Any):  # (Daemon) -> service with async run()/stop()
    return CheckpointRecoveryService(daemon)
