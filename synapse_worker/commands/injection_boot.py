"""Register the Layer B injection / jailbreak guard at daemon assembly (§4.5).

``build_daemon()`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one installs :class:`InjectionFilter` into the shared filter chain — mirroring
``commands/redaction_boot.py``.

Ordering: ``redaction_boot`` (Layer A) registers first so secrets are masked before this
guard ever sees them; both filters then live in the chain. We guard against
double-registration so re-imports are idempotent, and honour
``settings.injection_guard_enabled`` so an operator can turn the layer off.
"""
from __future__ import annotations

from ..config import get_settings
from ..filtering.base import get_filter_chain
from ..filtering.injection import InjectionFilter
from ..logging import get_logger

log = get_logger(__name__)


def _install_injection_filter() -> None:
    chain = get_filter_chain()
    # Idempotent: a second import (or re-assembly) must not stack duplicate filters.
    if any(getattr(f, "name", None) == "injection" for f in chain.filters):
        return
    chain.register(InjectionFilter())
    log.debug("injection filter installed")


# Run at import time (build_daemon imports this module). Respect the operator toggle.
if get_settings().injection_guard_enabled:
    _install_injection_filter()
