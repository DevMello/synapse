"""Register the Layer A redaction filter at daemon assembly (§4.5).

``build_daemon()`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one is enough to install :class:`RedactionFilter` into the shared filter chain —
mirroring the import-side-effect pattern in ``commands/connection.py``.

The filter is registered FIRST among the guard layers so secrets are masked before
anything downstream (injection guard, persistence, upload) ever sees the raw value. We
guard against double-registration so re-imports are idempotent, and honour
``settings.redaction_enabled`` so an operator can turn the layer off.
"""
from __future__ import annotations

from ..config import get_settings
from ..filtering.base import get_filter_chain
from ..filtering.redaction import RedactionFilter
from ..logging import get_logger

log = get_logger(__name__)


def _install_redaction_filter() -> None:
    chain = get_filter_chain()
    # Idempotent: a second import (or re-assembly) must not stack duplicate filters.
    if any(getattr(f, "name", None) == "redaction" for f in chain.filters):
        return
    chain.register(RedactionFilter())
    log.debug("redaction filter installed")


# Run at import time (build_daemon imports this module). Respect the operator toggle.
if get_settings().redaction_enabled:
    _install_redaction_filter()
