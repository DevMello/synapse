"""Audit log query + SIEM export (spec §9, Unit 16).

Read-only, org-scoped, admin-only access to the tamper-evident audit ledger:
  * GET /audit            — filtered, paginated query (created_at desc).
  * GET /audit/export     — full export as JSON array or ArcSight CEF.
  * GET /audit/verify     — recompute the per-org hash chain and report integrity.

Reading the audit log is sensitive (it reveals who did what), so every endpoint
is gated on admin (`require_admin`). The service-role client bypasses RLS, so
EVERY query is explicitly scoped by `principal.org_id`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from ..audit import chain_hash, hash_payload
from ..db import service_db
from ..deps import Principal, require_admin

router = APIRouter(prefix="/audit", tags=["audit"])

_FIELDS = (
    "id, org_id, actor, action, resource_type, resource_id, run_id, "
    "detail, prev_hash, hash, created_at"
)
_MAX_LIMIT = 1000


async def _query_events(
    org_id: str,
    *,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    actor: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    ascending: bool = False,
) -> list[dict]:
    db = await service_db()
    q = db.table("audit_events").select(_FIELDS).eq("org_id", org_id)
    if action:
        q = q.eq("action", action)
    if resource_type:
        q = q.eq("resource_type", resource_type)
    if actor:
        q = q.eq("actor", actor)
    if since:
        q = q.gte("created_at", since)
    if until:
        q = q.lte("created_at", until)
    # Deterministic ordering; id as a tiebreaker mirrors the writer's chain order.
    q = q.order("created_at", desc=not ascending).order("id", desc=not ascending)
    if limit is not None:
        q = q.range(offset, offset + limit - 1)
    return (await q.execute()).data or []


@router.get("")
async def list_audit_events(
    principal: Principal = Depends(require_admin),
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    actor: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None, description="ISO8601 lower bound (inclusive)"),
    until: Optional[str] = Query(default=None, description="ISO8601 upper bound (inclusive)"),
    limit: int = Query(default=100, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Filtered, paginated audit query for the caller's org (created_at desc)."""
    return await _query_events(
        principal.org_id,
        action=action,
        resource_type=resource_type,
        actor=actor,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )


def _cef_escape(value: str) -> str:
    """Escape CEF extension values: backslash, equals, and newlines."""
    return (
        value.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _to_cef(row: dict) -> str:
    """Render one audit row as an ArcSight CEF line.

    Header: CEF:Version|Device Vendor|Device Product|Device Version|
            Signature ID|Name|Severity|Extension
    """
    action = str(row.get("action") or "")
    extensions: list[str] = []

    def add(key: str, value) -> None:
        if value is None or value == "":
            return
        extensions.append(f"{key}={_cef_escape(str(value))}")

    add("rt", row.get("created_at"))
    add("suser", row.get("actor"))
    add("cs1", row.get("resource_type"))
    add("cs1Label", "resourceType" if row.get("resource_type") else None)
    add("cs2", row.get("resource_id"))
    add("cs2Label", "resourceId" if row.get("resource_id") else None)
    add("cs3", row.get("run_id"))
    add("cs3Label", "runId" if row.get("run_id") else None)
    add("externalId", row.get("id"))

    header = f"CEF:0|Synapse|CloudBackend|1.0|{action}|{action}|0"
    return header + "|" + " ".join(extensions)


@router.get("/export")
async def export_audit_events(
    principal: Principal = Depends(require_admin),
    format: str = Query(default="json", pattern="^(json|cef)$"),
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    actor: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    until: Optional[str] = Query(default=None),
):
    """Export the org's audit events as a JSON array or CEF (one line per event)."""
    # Export ascending (chronological) — natural for SIEM ingestion + chain order.
    rows = await _query_events(
        principal.org_id,
        action=action,
        resource_type=resource_type,
        actor=actor,
        since=since,
        until=until,
        ascending=True,
    )
    if format == "cef":
        body = "\n".join(_to_cef(r) for r in rows)
        return PlainTextResponse(content=body, media_type="text/plain")
    return rows


@router.get("/verify")
async def verify_audit_chain(
    principal: Principal = Depends(require_admin),
) -> dict:
    """Recompute the per-org hash chain and report whether the links are intact.

    Walks the org's events in chain order and checks, for each row, that
    `prev_hash` equals the previous row's stored `hash` and that the stored
    `hash` recomputes from the canonical payload. The first break (if any) is
    reported.
    """
    rows = await _query_events(principal.org_id, ascending=True)

    expected_prev: Optional[str] = None
    for index, row in enumerate(rows):
        payload = hash_payload(
            action=row.get("action"),
            actor=row.get("actor"),
            resource_type=row.get("resource_type"),
            resource_id=row.get("resource_id"),
            run_id=row.get("run_id"),
            detail=row.get("detail") or {},
            created_at=row.get("created_at"),
        )
        if (row.get("prev_hash") or None) != (expected_prev or None):
            return {
                "ok": False,
                "count": len(rows),
                "broken_at": index,
                "broken_id": row.get("id"),
                "reason": "prev_hash mismatch",
            }
        recomputed = chain_hash(row.get("prev_hash"), payload)
        if recomputed != row.get("hash"):
            return {
                "ok": False,
                "count": len(rows),
                "broken_at": index,
                "broken_id": row.get("id"),
                "reason": "hash mismatch",
            }
        expected_prev = row.get("hash")

    return {"ok": True, "count": len(rows), "broken_at": None}
