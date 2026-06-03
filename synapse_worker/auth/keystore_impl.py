"""Production keystores: OS keychain with an encrypted-file fallback (§2).

Secrets (access/refresh tokens, the daemon X25519 private key, the org recovery private
key) never live in plaintext on disk. Two backends:

  * :class:`KeyringKeystore` — the OS keychain (Keychain / Credential Manager / Secret
    Service) via the ``keyring`` library. Preferred everywhere a keychain exists.
  * :class:`FileKeystore` — a libsodium-encrypted JSON blob at ``paths.token_file``,
    written ``0600`` (``paths.secure_write``). Used on headless boxes whose keyring is
    locked or absent. The file is sealed with a machine-local key persisted next to it
    (also ``0600``), generated once.

:func:`select_keystore` tries keyring first and falls back to the file store, so the
daemon pairs on a VPS with no Secret Service the same way it does on a laptop.

To enumerate which keys exist (``list_keys``) the keyring backend keeps a tiny index
entry, since the OS keychain APIs ``keyring`` exposes can't list a service's items.
"""
from __future__ import annotations

import json
from typing import Optional

import nacl.secret
import nacl.utils

from ..crypto import Keystore, _b64d, _b64e
from ..logging import get_logger
from ..paths import WorkerPaths, get_paths, secure_write

log = get_logger(__name__)

# A reserved key used to remember which keys a service holds (keyring can't list).
_INDEX_KEY = "__index__"


# ── keyring backend ──────────────────────────────────────────────────────────
class KeyringKeystore(Keystore):
    """OS keychain backend. Keeps a per-service index so ``list_keys`` works."""

    def __init__(self) -> None:
        import keyring  # imported lazily so the module imports without a backend

        self._keyring = keyring

    def get(self, service: str, key: str) -> Optional[str]:
        return self._keyring.get_password(service, key)

    def set(self, service: str, key: str, value: str) -> None:
        self._keyring.set_password(service, key, value)
        index = set(self._read_index(service))
        if key not in index:
            index.add(key)
            self._write_index(service, index)

    def delete(self, service: str, key: str) -> None:
        try:
            self._keyring.delete_password(service, key)
        except Exception:  # noqa: BLE001 - keyring raises PasswordDeleteError if absent
            pass
        index = set(self._read_index(service))
        if key in index:
            index.discard(key)
            if index:
                self._write_index(service, index)
            else:
                # Don't leave an empty index entry lingering in the keychain.
                try:
                    self._keyring.delete_password(service, _INDEX_KEY)
                except Exception:  # noqa: BLE001
                    pass

    def list_keys(self, service: str) -> list[str]:
        return sorted(self._read_index(service))

    # ── index helpers ────────────────────────────────────────────────────────
    def _read_index(self, service: str) -> list[str]:
        raw = self._keyring.get_password(service, _INDEX_KEY)
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except ValueError:
            return []
        return [k for k in data if isinstance(k, str)]

    def _write_index(self, service: str, keys: set[str]) -> None:
        self._keyring.set_password(service, _INDEX_KEY, json.dumps(sorted(keys)))


# ── encrypted-file backend ───────────────────────────────────────────────────
class FileKeystore(Keystore):
    """Encrypted-file fallback: a single ``SecretBox``-sealed JSON map, 0600 on disk.

    The whole keystore is one ciphertext blob keyed by ``(service, key)``; the symmetric
    key is a 32-byte random secret persisted once alongside the blob (also 0600). This is
    a *local* secret — its only job is to keep the token file unreadable to other users
    on the box, matching the keychain's at-rest protection.
    """

    def __init__(self, paths: Optional[WorkerPaths] = None) -> None:
        self._paths = paths or get_paths()
        self._blob_path = self._paths.token_file
        # Sit the key next to the blob (tokens.enc -> tokens.key) so they move together.
        self._key_path = self._blob_path.with_suffix(".key")

    # ── key material ─────────────────────────────────────────────────────────
    def _box(self) -> nacl.secret.SecretBox:
        if self._key_path.is_file():
            key = _b64d(self._key_path.read_text(encoding="ascii").strip())
        else:
            key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
            # secure_write creates the parent 0700 and the file 0600 from the start.
            secure_write(self._key_path, _b64e(key))
        return nacl.secret.SecretBox(key)

    # ── on-disk map ──────────────────────────────────────────────────────────
    # The blob is the raw libsodium ciphertext, written/read as bytes. secure_write opens
    # with O_BINARY on Windows, so 0x0A bytes are no longer translated to CRLF — there is
    # no need to base64-armor the ciphertext just to survive the file write.
    def _load(self) -> dict[str, str]:
        if not self._blob_path.is_file():
            return {}
        blob = self._blob_path.read_bytes()
        if not blob:
            return {}
        plaintext = self._box().decrypt(blob)
        data = json.loads(plaintext.decode("utf-8"))
        return {str(k): str(v) for k, v in data.items()}

    def _save(self, data: dict[str, str]) -> None:
        plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")
        ciphertext = bytes(self._box().encrypt(plaintext))
        secure_write(self._blob_path, ciphertext)

    @staticmethod
    def _slot(service: str, key: str) -> str:
        return f"{service}\x00{key}"

    # ── Keystore API ─────────────────────────────────────────────────────────
    def get(self, service: str, key: str) -> Optional[str]:
        return self._load().get(self._slot(service, key))

    def set(self, service: str, key: str, value: str) -> None:
        data = self._load()
        data[self._slot(service, key)] = value
        self._save(data)

    def delete(self, service: str, key: str) -> None:
        data = self._load()
        if data.pop(self._slot(service, key), None) is not None:
            self._save(data)

    def list_keys(self, service: str) -> list[str]:
        prefix = f"{service}\x00"
        return sorted(
            slot[len(prefix):] for slot in self._load() if slot.startswith(prefix)
        )


# ── selection ────────────────────────────────────────────────────────────────
def select_keystore(paths: Optional[WorkerPaths] = None) -> Keystore:
    """Return the keyring backend if usable, else the encrypted-file fallback.

    "Usable" means ``keyring`` imports AND a real (non-fail) backend is active and
    answers a probe set/get. A ``fail.Keyring`` backend (no OS keychain) or any error
    means we fall back to the 0600 file store.
    """
    try:
        import keyring
        from keyring.backends import fail as _fail

        backend = keyring.get_keyring()
        if isinstance(backend, _fail.Keyring):
            raise RuntimeError("no usable keyring backend")
        store = KeyringKeystore()
        # Probe: a chainer that silently no-ops would corrupt our token storage.
        store.set("synapse:probe", "probe", "ok")
        if store.get("synapse:probe", "probe") != "ok":
            raise RuntimeError("keyring probe failed")
        store.delete("synapse:probe", "probe")
        return store
    except Exception as exc:  # noqa: BLE001 - any keyring trouble => file fallback
        log.info("keyring unavailable (%s); using encrypted-file keystore", exc)
        return FileKeystore(paths)
