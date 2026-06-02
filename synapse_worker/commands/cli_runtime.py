"""CLI runtime unit wiring (§4.3).

``app.build_daemon`` auto-imports every ``synapse_worker.commands.*`` module; importing
this one triggers :mod:`synapse_worker.runtime.cli_adapter`, whose import side-effect
registers the ``"cli"`` adapter in the runtime registry. The engine (sibling unit) then
resolves it via ``get_adapter("cli")``.

There are no ``@on_command`` handlers here — the CLI adapter is a runtime capability, not
a command target. Like ``commands/connection.py``, this is an import-only registration
module.
"""
from __future__ import annotations

from ..runtime import cli_adapter  # noqa: F401  (import side-effect: registers "cli")
