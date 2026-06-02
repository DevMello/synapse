"""Install the real ruleset / blocker engine at daemon assembly (§4.6).

``build_daemon()`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one is enough to swap the foundation's :class:`PermissiveRuleset` for the policy-
enforcing :class:`RulesetEngine` — mirroring the import-side-effect pattern in
``commands/redaction_boot.py``.

We guard against double-installation so re-imports (or re-assembly) are idempotent: a
``RulesetEngine`` already installed is left in place, preserving any policy already loaded
into it by a later unit.
"""
from __future__ import annotations

from ..logging import get_logger
from ..ruleset.base import get_ruleset, set_ruleset
from ..ruleset.engine import RulesetEngine

log = get_logger(__name__)


def _install_ruleset_engine() -> None:
    # Idempotent: don't clobber an engine (and its policy) that's already installed.
    if isinstance(get_ruleset(), RulesetEngine):
        return
    set_ruleset(RulesetEngine())
    log.debug("ruleset engine installed")


# Run at import time (build_daemon imports this module).
_install_ruleset_engine()
