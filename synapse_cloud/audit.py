"""Append-only audit log seam (spec §9).

Every consequential command and agent decision lands here immutably. The
foundation ships a basic writer that inserts into `audit_events`. Unit 16 owns
this file and upgrades it with hash-chaining (tamper-evident ledger) + SIEM
export; until then the basic writer is fully functional.

`audit_events` is RLS-protected: authenticated users can SELECT their org's
rows but INSERT/UPDATE/DELETE are revoked — writes go through the service-role
client here, and there is intentionally no update/delete path.
"""
from __future__ import annotations

import abc
from typing import Any, Optional

from .db import service_db


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


class BasicAuditWriter(AuditWriter):
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
        await db.table("audit_events").insert(
            {
                "org_id": org_id,
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "run_id": run_id,
                "detail": detail or {},
            }
        ).execute()


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
