"""Append-only audit log seam (spec §9).

Every consequential command and agent decision lands here immutably. The
DB-backed writer (`SupabaseAuditWriter`) inserts into `audit_events` and chains
each row to the previous one for that org with a SHA-256 hash, producing a
tamper-evident ledger: a single edited/removed row breaks the chain and is
detectable via the verify endpoint.

`audit_events` is RLS-protected: authenticated users can SELECT their org's
rows but INSERT/UPDATE/DELETE are revoked — writes go through the service-role
client here, and there is intentionally no update/delete path (append-only).

Hash-chain definition (per org, ordered by created_at):
  prev_hash = hash of the most recent existing row for the org (NULL at genesis)
  hash      = sha256_hex(prev_hash_or_"" + canonical_json(payload))
where payload is the canonical (sorted-key, compact) JSON of
  {action, actor, resource_type, resource_id, run_id, detail, created_at}.
"""
from __future__ import annotations

import abc
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from .db import service_db


def _canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 safe."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def chain_hash(prev_hash: Optional[str], payload: dict[str, Any]) -> str:
    """sha256_hex(prev_hash_or_"" + canonical_json(payload))."""
    material = (prev_hash or "") + _canonical_json(payload)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def hash_payload(
    *,
    action: str,
    actor: Optional[str],
    resource_type: Optional[str],
    resource_id: Optional[str],
    run_id: Optional[str],
    detail: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """The canonical field set that is hashed for a row (excludes id/hashes)."""
    return {
        "action": action,
        "actor": actor,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "run_id": run_id,
        "detail": detail,
        "created_at": created_at,
    }


class AuditWriter(abc.ABC):
    @abc.abstractmethod
    async def write(
        self,
        org_id: str,
        action: str,
        *,
        actor: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        run_id: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        ...


class SupabaseAuditWriter(AuditWriter):
    """DB-backed writer with a per-org, tamper-evident SHA-256 hash chain.

    `prev_hash` links to the `hash` of the most recent existing row for the org
    (NULL at genesis). `created_at` is generated here (UTC) so the exact value
    that is persisted is the value that is hashed.
    """

    async def write(
        self,
        org_id,
        action,
        *,
        actor=None,
        resource_type=None,
        resource_id=None,
        run_id=None,
        detail=None,
    ):
        db = await service_db()

        # Most recent row for this org gives us the link target. Order by
        # created_at then id so ties (same timestamp) are deterministic.
        prev_rows = (
            await db.table("audit_events")
            .select("hash")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(1)
            .execute()
        ).data or []
        prev_hash = prev_rows[0].get("hash") if prev_rows else None

        detail = detail or {}
        created_at = datetime.now(timezone.utc).isoformat()
        payload = hash_payload(
            action=action,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            run_id=run_id,
            detail=detail,
            created_at=created_at,
        )
        row_hash = chain_hash(prev_hash, payload)

        await db.table("audit_events").insert(
            {
                "org_id": org_id,
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "run_id": run_id,
                "detail": detail,
                "created_at": created_at,
                "prev_hash": prev_hash,
                "hash": row_hash,
            }
        ).execute()


# Backward-compat alias: callers/imports that referenced the original writer
# name keep working and now get hash-chaining for free.
BasicAuditWriter = SupabaseAuditWriter


class FakeAuditWriter(AuditWriter):
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def write(self, org_id, action, *, actor=None, resource_type=None,
                    resource_id=None, run_id=None, detail=None):
        self.events.append(
            {
                "org_id": org_id,
                "action": action,
                "actor": actor,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "run_id": run_id,
                "detail": detail or {},
            }
        )


_writer: Optional[AuditWriter] = None


def get_audit() -> AuditWriter:
    global _writer
    if _writer is None:
        from .config import get_settings

        _writer = FakeAuditWriter() if get_settings().is_test else BasicAuditWriter()
    return _writer


def set_audit(writer: AuditWriter) -> None:
    global _writer
    _writer = writer
