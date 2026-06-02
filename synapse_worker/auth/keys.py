"""Daemon + org-recovery E2E keypairs and token storage in the keychain (§2, §4.10/§4.12).

All daemon secrets live under one keystore service so Unit 1 ("Connection") and the env
vault / checkpoint units read them by the same convention. The key NAMES here are the
shared contract — do not rename them.

Two keypairs:
  * **daemon keypair** (X25519) — generated on first pairing; the private half stays in
    the keychain, the public half is registered with the cloud and used by the Web UI to
    seal env-var values to this daemon (§4.10).
  * **org recovery keypair** — org-scoped; the daemon RECEIVES it over the authenticated
    session (§2) so checkpoints can be sealed to it (§4.12). Until the login response
    carries it (see the seam in cli/cmd_login.py), it stays unset; the setters here let a
    later unit install it without touching this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import crypto
from ..crypto import Keystore, get_keystore

# Shared keystore namespace + key names (Unit 1 reads these — do NOT rename).
SERVICE = "synapse:daemon"

KEY_ACCESS_TOKEN = "access_token"
KEY_REFRESH_TOKEN = "refresh_token"
KEY_DAEMON_PRIVATE = "daemon_private_key"
KEY_DAEMON_PUBLIC = "daemon_public_key"
KEY_ORG_RECOVERY_PRIVATE = "org_recovery_private_key"
KEY_ORG_RECOVERY_PUBLIC = "org_recovery_public_key"


def _ks(keystore: Optional[Keystore]) -> Keystore:
    return keystore or get_keystore()


# ── tokens ───────────────────────────────────────────────────────────────────
def store_tokens(
    access_token: str, refresh_token: str, *, keystore: Optional[Keystore] = None
) -> None:
    """Persist the daemon's access + refresh tokens in the keychain only."""
    ks = _ks(keystore)
    ks.set(SERVICE, KEY_ACCESS_TOKEN, access_token)
    ks.set(SERVICE, KEY_REFRESH_TOKEN, refresh_token)


def get_access_token(*, keystore: Optional[Keystore] = None) -> Optional[str]:
    return _ks(keystore).get(SERVICE, KEY_ACCESS_TOKEN)


def get_refresh_token(*, keystore: Optional[Keystore] = None) -> Optional[str]:
    return _ks(keystore).get(SERVICE, KEY_REFRESH_TOKEN)


# ── daemon keypair ───────────────────────────────────────────────────────────
def ensure_daemon_keypair(*, keystore: Optional[Keystore] = None) -> crypto.KeyPair:
    """Return the daemon X25519 keypair, generating + storing it on first call.

    Idempotent: an existing private key in the keychain is reused (and its public half
    re-derived if missing) so re-running ``synapse login`` never rotates the daemon's
    identity key out from under sealed env vars.
    """
    ks = _ks(keystore)
    private = ks.get(SERVICE, KEY_DAEMON_PRIVATE)
    if private:
        public = ks.get(SERVICE, KEY_DAEMON_PUBLIC) or crypto.public_key_b64(private)
        ks.set(SERVICE, KEY_DAEMON_PUBLIC, public)
        return crypto.KeyPair(public_key=public, private_key=private)

    pair = crypto.generate_keypair()
    ks.set(SERVICE, KEY_DAEMON_PRIVATE, pair.private_key)
    ks.set(SERVICE, KEY_DAEMON_PUBLIC, pair.public_key)
    return pair


def get_daemon_public_key(*, keystore: Optional[Keystore] = None) -> Optional[str]:
    """The public key to register with the cloud (the Web UI seals env vars to it).

    TODO(connection unit): upload this to the cloud as ``daemons.public_key`` once the
    daemon endpoint exists; for this unit it is persisted + exposed only.
    """
    return _ks(keystore).get(SERVICE, KEY_DAEMON_PUBLIC)


# ── org recovery keypair ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class OrgRecoveryKey:
    public_key: str
    private_key: Optional[str]  # None when only the public half is known


def store_org_recovery_key(
    public_key: str,
    private_key: Optional[str] = None,
    *,
    keystore: Optional[Keystore] = None,
) -> None:
    """Install the org recovery keypair received over the authenticated session (§2).

    The daemon does not generate this — the cloud hands it to authorized daemons so any
    of them can open checkpoints (§4.12). Callers pass whatever halves the session
    carried; the public half is always stored, the private half only when present.
    """
    ks = _ks(keystore)
    ks.set(SERVICE, KEY_ORG_RECOVERY_PUBLIC, public_key)
    if private_key is not None:
        ks.set(SERVICE, KEY_ORG_RECOVERY_PRIVATE, private_key)


def get_org_recovery_key(
    *, keystore: Optional[Keystore] = None
) -> Optional[OrgRecoveryKey]:
    ks = _ks(keystore)
    public = ks.get(SERVICE, KEY_ORG_RECOVERY_PUBLIC)
    if not public:
        return None
    return OrgRecoveryKey(
        public_key=public, private_key=ks.get(SERVICE, KEY_ORG_RECOVERY_PRIVATE)
    )
