"""Install the production keystore at daemon assembly time.

``build_daemon()`` auto-imports every ``synapse_worker.commands.*`` module (pkgutil
discovery), so importing this one is enough to swap the foundation's in-memory keystore
default for the real keyring/encrypted-file backend — UNLESS we're in test mode, where
the in-memory default must stand so unit tests never touch a real keychain.

Selection (keyring → encrypted file) lives in ``auth.keystore_impl.select_keystore``;
this module just decides *whether* to install it.
"""
from __future__ import annotations

from ..config import get_settings
from ..crypto import set_keystore
from ..logging import get_logger

log = get_logger(__name__)


def _install_production_keystore() -> None:
    # Import lazily so test-mode assembly never imports the keyring backend.
    from ..auth.keystore_impl import select_keystore

    set_keystore(select_keystore())
    log.debug("production keystore installed")


# Run at import time (build_daemon imports this module). Tests keep the in-memory default.
if not get_settings().is_test:
    _install_production_keystore()
