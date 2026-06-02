"""HITL Gatekeeper package (§4.7).

Exposes the suspend/resume primitive (:class:`Gatekeeper`) and its module-level
singleton (:func:`get_gatekeeper`). The Agent Runtime calls
``await get_gatekeeper().request_approval(...)`` when the Ruleset Engine returns a
``REQUIRE_HITL`` decision (or an agent explicitly asks for approval); the
``hitl.resolve`` command handler (``synapse_worker.commands.hitl``) delivers the
cloud's decision back into the waiting gate.
"""
from __future__ import annotations

from .gatekeeper import (
    Gatekeeper,
    HitlOutcome,
    get_gatekeeper,
    reset_gatekeeper,
)

__all__ = [
    "Gatekeeper",
    "HitlOutcome",
    "get_gatekeeper",
    "reset_gatekeeper",
]
