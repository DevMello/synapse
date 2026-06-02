"""``EnvVault`` — on-device env-var storage, resolution, and injection (§4.10).

Threat model: env-var VALUES are secrets. They must live ONLY in the OS keyring on this
machine — never on disk in plaintext, never on the cloud. The cloud only ever sees:
  * opaque sealed-box ciphertext (E2E from the Web UI to this daemon's X25519 key), and
  * name-only metadata (so the dashboard can show *which* vars are set, never the value).

Keyring namespaces (service -> key=name -> value):
  * shared scope: ``synapse:shared:env``
  * agent scope:  ``synapse:agent:{agent_id}:env``

The matching name-only metadata is mirrored into the durable ``env_names`` table so
``synapse env list`` and the dashboard can enumerate names without unlocking the keychain.

Resolution (``resolve``) builds an agent's effective environment as a **shared -> agent**
merge: shared vars first, then the agent's own vars override shared ones of the same name.

Precedence within the agent scope: a value SET LOCALLY (``synapse env set``) overrides a
value PUSHED from the UI (``env.set``) of the same name. The keyring holds a single value
per (service, name), so a local set overwrites the UI value and stamps origin='local';
``env_names.origin`` records the winning provenance for the dashboard.

The daemon private key (for opening sealed boxes) lives in the keystore at service
``synapse:daemon`` / key ``daemon_private_key`` (written by the auth unit).
"""
from __future__ import annotations

import time
from typing import Optional

from ..crypto import Keystore, get_keystore, seal_open
from ..filtering.base import get_filter_chain
from ..logging import get_logger
from ..store import LocalStore, get_store

log = get_logger(__name__)

# Keystore location of the daemon's X25519 private key (auth unit writes it).
DAEMON_KEYSTORE_SERVICE = "synapse:daemon"
DAEMON_PRIVATE_KEY = "daemon_private_key"

SHARED_ENV_SERVICE = "synapse:shared:env"

ORIGIN_UI = "ui"
ORIGIN_LOCAL = "local"

SCOPE_SHARED = "shared"
SCOPE_AGENT = "agent"


def agent_env_service(agent_id: str) -> str:
    """Keyring service namespace holding an agent's private env values."""
    return f"synapse:agent:{agent_id}:env"


class EnvVault:
    """Keyring-namespaced env storage with sealed-box decrypt + run-time resolution.

    Stateless beyond its injected seams (keystore + store), so the command handlers and
    the CLI can each construct one cheaply. All value writes go to the keyring; only
    names reach the durable ``env_names`` table.
    """

    def __init__(
        self,
        *,
        keystore: Optional[Keystore] = None,
        store: Optional[LocalStore] = None,
    ) -> None:
        # Resolve seams lazily-ish: the keystore singleton is always available, but the
        # store may not be initialised in lightweight contexts, so allow override/None.
        self._keystore = keystore or get_keystore()
        self._store = store

    # ── store accessor (lazy so CLI/handlers don't need it wired at construction) ──
    def _get_store(self) -> LocalStore:
        return self._store or get_store()

    # ── sealed-box decrypt ────────────────────────────────────────────────────
    def _daemon_private_key(self) -> str:
        sk = self._keystore.get(DAEMON_KEYSTORE_SERVICE, DAEMON_PRIVATE_KEY)
        if not sk:
            raise RuntimeError(
                "daemon private key missing from keystore; cannot open sealed env value"
            )
        return sk

    def decrypt(self, ciphertext_b64: str) -> str:
        """Open a UI-sealed env value with the daemon private key. Returns plaintext.

        Never logs the plaintext (this is a secret value by definition).
        """
        return seal_open(self._daemon_private_key(), ciphertext_b64).decode()

    # ── value storage (keyring only) ──────────────────────────────────────────
    def _service_for(self, *, agent_id: Optional[str], shared: bool) -> str:
        if shared:
            return SHARED_ENV_SERVICE
        if not agent_id:
            raise ValueError("agent_id required for agent-scope env var")
        return agent_env_service(agent_id)

    async def store_value(
        self,
        name: str,
        value: str,
        *,
        agent_id: Optional[str] = None,
        shared: bool = False,
        origin: str = ORIGIN_LOCAL,
        register_redaction: bool = True,
    ) -> None:
        """Persist ONE env value to the keyring + its NAME-ONLY row to ``env_names``.

        The value goes to the keyring under the scope's service namespace; only the name
        (plus scope/agent/origin) is written to the durable table. Optionally registers
        the value with the redaction filter so it's masked even if echoed in logs.
        """
        service = self._service_for(agent_id=agent_id, shared=shared)
        self._keystore.set(service, name, value)

        scope = SCOPE_SHARED if shared else SCOPE_AGENT
        await self._get_store().execute(
            "INSERT INTO env_names (scope, agent_id, name, origin, updated_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(scope, agent_id, name) DO UPDATE SET"
            "   origin=excluded.origin, updated_at=excluded.updated_at",
            (scope, agent_id or "", name, origin, time.time()),
        )

        # Secrets (anything not explicitly marked plain) get masked in logs henceforth.
        if register_redaction:
            self.register_with_redaction([value])

    async def delete_value(
        self,
        name: str,
        *,
        agent_id: Optional[str] = None,
        shared: bool = False,
    ) -> None:
        """Remove a value from the keyring and drop its ``env_names`` row."""
        service = self._service_for(agent_id=agent_id, shared=shared)
        self._keystore.delete(service, name)

        scope = SCOPE_SHARED if shared else SCOPE_AGENT
        await self._get_store().execute(
            "DELETE FROM env_names WHERE scope=? AND agent_id=? AND name=?",
            (scope, agent_id or "", name),
        )

    # ── name-only enumeration (never returns values) ──────────────────────────
    async def list_names(
        self, *, agent_id: Optional[str] = None, shared: bool = False
    ) -> list[dict[str, str]]:
        """Return name-only metadata rows ({name, origin, scope}) — never values."""
        scope = SCOPE_SHARED if shared else SCOPE_AGENT
        rows = await self._get_store().fetchall(
            "SELECT name, origin, scope FROM env_names"
            " WHERE scope=? AND agent_id=? ORDER BY name",
            (scope, agent_id or ""),
        )
        return rows

    # ── resolution & injection ────────────────────────────────────────────────
    def resolve(self, agent_id: str) -> dict[str, str]:
        """Effective env for a run: shared set merged UNDER the agent's own set.

        Shared vars apply first; the agent's own vars override shared ones of the same
        name. Within the agent scope, locally-set values already won at write time (a
        local set overwrites the keyring entry), so we just read the resolved keyring
        values back here.

        Values are read straight from the keyring — they are NOT returned through any
        cloud/disk path. Missing keyring entries (name listed but value evicted) are
        skipped defensively.
        """
        merged: dict[str, str] = {}

        # 1) shared scope (lowest precedence).
        for name in self._keystore.list_keys(SHARED_ENV_SERVICE):
            val = self._keystore.get(SHARED_ENV_SERVICE, name)
            if val is not None:
                merged[name] = val

        # 2) agent scope overrides shared.
        service = agent_env_service(agent_id)
        for name in self._keystore.list_keys(service):
            val = self._keystore.get(service, name)
            if val is not None:
                merged[name] = val

        return merged

    def register_with_redaction(self, values: list[str]) -> None:
        """Mask each value in logs by registering it with the redaction filter (Unit 6).

        Walks the shared filter chain and calls ``register_secret`` on any filter that
        exposes it (the Unit 6 ``RedactionFilter``). Guards if the redaction layer isn't
        present so the vault still works on a pass-through chain.
        """
        try:
            filters = get_filter_chain().filters
        except Exception:  # noqa: BLE001 - chain access must never break a run
            return
        for flt in filters:
            register = getattr(flt, "register_secret", None)
            if callable(register):
                for value in values:
                    if value:
                        register(value, category="ENV")
