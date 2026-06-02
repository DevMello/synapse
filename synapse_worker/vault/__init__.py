"""Environment-variable vault (§4.10).

Env-var VALUES live ONLY in this machine's OS keyring — never on disk in plaintext,
never on the cloud. The cloud relays opaque sealed-box ciphertext (E2E from the Web UI)
and name-only metadata; this package decrypts, stores, resolves, and injects.

Public surface:
  * :class:`EnvVault` — keyring-namespaced storage + resolution/injection.
"""
from __future__ import annotations

from .vault import EnvVault

__all__ = ["EnvVault"]
