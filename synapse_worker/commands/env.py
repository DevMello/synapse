"""``env.set`` + ``env.delete`` command handlers (cloud -> daemon, §4.10).

``build_daemon()`` auto-imports every ``synapse_worker.commands.*`` module, so importing
this one registers both handlers.

E2E model: the Web UI seals each env value to THIS daemon's X25519 public key (libsodium
sealed box); the cloud relays only the opaque ciphertext. We open it with the daemon
private key (keystore) and store the plaintext in the keyring under a per-agent namespace.
Only the NAME ever touches durable storage / the cloud.

Wire shapes (read defensively — the cloud is the source of truth)::

    env.set    {"name": <str>, "ciphertext": <base64 sealed box>}
    env.delete {"name": <str>}

The agent_id is NOT in the payload; it's embedded in the idempotency key
(``env.set:{agent_id}:{name}`` / ``env.delete:{agent_id}:{name}``). We parse it from
there, falling back to ``payload["agent_id"]`` if a future wire revision includes it.
"""
from __future__ import annotations

from typing import Any, Optional

from ..logging import get_logger
from ..router import CommandContext, on_command
from ..vault import EnvVault

log = get_logger(__name__)


def _agent_id_from(ctx: CommandContext, payload: dict[str, Any]) -> Optional[str]:
    """Recover agent_id from the idempotency key (``<cmd>:{agent_id}:{name}``).

    Defensive: the key may be missing/garbled, so fall back to an explicit payload field.
    We split on ':' and take parts[1] — the command type itself may contain a '.', never
    a ':'. Falls back to ``payload['agent_id']`` last.
    """
    key = ctx.idempotency_key or ""
    parts = key.split(":")
    if len(parts) >= 3 and parts[1]:
        return parts[1]
    fallback = payload.get("agent_id")
    return str(fallback) if fallback else None


@on_command("env.set")
async def handle_env_set(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Decrypt a UI-pushed env value and store it in the agent's keyring namespace."""
    name = payload.get("name")
    ciphertext = payload.get("ciphertext")
    if not name or not ciphertext:
        log.warning("env.set: missing name/ciphertext; ignoring")
        return

    agent_id = _agent_id_from(ctx, payload)
    if not agent_id:
        log.warning("env.set for %s: no agent_id (idempotency key/payload); ignoring", name)
        return

    vault = EnvVault()
    try:
        value = vault.decrypt(str(ciphertext))
    except Exception:  # noqa: BLE001 - never log the plaintext or the raw ciphertext
        log.exception("env.set for %s: failed to open sealed box", name)
        return

    # origin='ui': pushed from the Web UI. Registers with the redaction filter so the
    # value is masked in logs even if some downstream echoes it.
    await vault.store_value(
        str(name), value, agent_id=agent_id, origin="ui", register_redaction=True
    )
    log.info("env.set: stored %s for agent %s (ui)", name, agent_id)


@on_command("env.delete")
async def handle_env_delete(ctx: CommandContext, payload: dict[str, Any]) -> None:
    """Remove an env value from the keyring + its ``env_names`` row."""
    name = payload.get("name")
    if not name:
        log.warning("env.delete: missing name; ignoring")
        return

    agent_id = _agent_id_from(ctx, payload)
    if not agent_id:
        log.warning("env.delete for %s: no agent_id; ignoring", name)
        return

    vault = EnvVault()
    await vault.delete_value(str(name), agent_id=agent_id)
    log.info("env.delete: removed %s for agent %s", name, agent_id)
