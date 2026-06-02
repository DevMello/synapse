"""On-device crypto + the secret keystore seam.

Two E2E-encryption keypairs (X25519 / libsodium, via PyNaCl), both private halves held
only on this machine:

  * the **daemon keypair** — the Web UI seals env-var values to its public key; the
    daemon opens them (§4.10).
  * the **org recovery keypair** — checkpoints are sealed to it before cloud sync so any
    authorized daemon in the org can decrypt and resume (§4.12).

Secrets (tokens, private keys, env values) live in the OS keychain via the keystore
seam. Default impls:
  * :class:`InMemoryKeystore` in tests (``is_test``),
  * a keyring-backed store in production (installed by the auth unit),
  * an encrypted-file fallback for headless boxes (also auth unit).
The foundation only ships the in-memory default + the crypto primitives so it stays
importable without the ``keyring`` backend present.
"""
from __future__ import annotations

import abc
import base64
from dataclasses import dataclass
from typing import Optional

from nacl.public import PrivateKey, PublicKey, SealedBox

from .config import get_settings


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


@dataclass(frozen=True)
class KeyPair:
    public_key: str   # base64 X25519 public key (registered with the cloud)
    private_key: str  # base64 X25519 private key (NEVER leaves this machine)


def generate_keypair() -> KeyPair:
    sk = PrivateKey.generate()
    return KeyPair(public_key=_b64e(bytes(sk.public_key)), private_key=_b64e(bytes(sk)))


def public_key_b64(private_key_b64: str) -> str:
    sk = PrivateKey(_b64d(private_key_b64))
    return _b64e(bytes(sk.public_key))


def seal(public_key_b64: str, plaintext: bytes) -> str:
    """Seal plaintext to a public key (anonymous sealed box). Returns base64."""
    box = SealedBox(PublicKey(_b64d(public_key_b64)))
    return _b64e(box.encrypt(plaintext))


def seal_open(private_key_b64: str, ciphertext_b64: str) -> bytes:
    """Open a sealed box with the matching private key. Raises on tamper/mismatch."""
    box = SealedBox(PrivateKey(_b64d(private_key_b64)))
    return box.decrypt(_b64d(ciphertext_b64))


# ── keystore seam ───────────────────────────────────────────────────────────
class Keystore(abc.ABC):
    """Stores named secrets under a service namespace (OS keychain in prod)."""

    @abc.abstractmethod
    def get(self, service: str, key: str) -> Optional[str]: ...

    @abc.abstractmethod
    def set(self, service: str, key: str, value: str) -> None: ...

    @abc.abstractmethod
    def delete(self, service: str, key: str) -> None: ...

    @abc.abstractmethod
    def list_keys(self, service: str) -> list[str]: ...


class InMemoryKeystore(Keystore):
    """Process-local keystore for tests — never touches a real keychain."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get(self, service: str, key: str) -> Optional[str]:
        return self._data.get((service, key))

    def set(self, service: str, key: str, value: str) -> None:
        self._data[(service, key)] = value

    def delete(self, service: str, key: str) -> None:
        self._data.pop((service, key), None)

    def list_keys(self, service: str) -> list[str]:
        return [k for (s, k) in self._data if s == service]


_keystore: Optional[Keystore] = None


def get_keystore() -> Keystore:
    global _keystore
    if _keystore is None:
        # Foundation default: in-memory. The auth unit installs the keyring/file
        # backed store via set_keystore() at startup in non-test environments.
        _keystore = InMemoryKeystore()
    return _keystore


def set_keystore(keystore: Keystore) -> None:
    global _keystore
    _keystore = keystore


def reset_keystore() -> None:  # test helper
    global _keystore
    _keystore = None
