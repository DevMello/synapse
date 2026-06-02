"""Environment Variable Vault tests (§4.10) — self-contained, no network.

Covers the full E2E path: a value sealed to the daemon's public key (as the Web UI would
do) arrives via ``env.set``, is opened with the daemon private key from the keystore, and
lands in the OS keyring under the per-agent namespace with NAME-ONLY metadata in
``env_names``. Also covers ``env.delete``, shared->agent merge + local-over-ui precedence,
the ``synapse env set/list/rm`` CLI (names only), and redaction registration.

The conftest installs the in-memory keystore/uplink and a fresh filter chain per test, so
nothing here touches a real keychain, the cloud, or the network.
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from synapse_worker.crypto import (
    generate_keypair,
    get_keystore,
    seal,
)
from synapse_worker.filtering.base import Direction, get_filter_chain, reset_filter_chain
from synapse_worker.filtering.redaction import RedactionFilter
from synapse_worker.router import CommandContext
from synapse_worker.vault import EnvVault
from synapse_worker.vault.vault import (
    DAEMON_KEYSTORE_SERVICE,
    DAEMON_PRIVATE_KEY,
    SHARED_ENV_SERVICE,
    agent_env_service,
)


# ── helpers ───────────────────────────────────────────────────────────────────
def _seed_daemon_keypair() -> str:
    """Install a daemon keypair in the keystore; return the public key (b64)."""
    kp = generate_keypair()
    ks = get_keystore()
    ks.set(DAEMON_KEYSTORE_SERVICE, DAEMON_PRIVATE_KEY, kp.private_key)
    return kp.public_key


async def _call_env_set(name: str, ciphertext: str, agent_id: str) -> None:
    from synapse_worker.commands.env import handle_env_set

    ctx = CommandContext(
        command_type="env.set",
        idempotency_key=f"env.set:{agent_id}:{name}",
    )
    await handle_env_set(ctx, {"name": name, "ciphertext": ciphertext})


async def _call_env_delete(name: str, agent_id: str) -> None:
    from synapse_worker.commands.env import handle_env_delete

    ctx = CommandContext(
        command_type="env.delete",
        idempotency_key=f"env.delete:{agent_id}:{name}",
    )
    await handle_env_delete(ctx, {"name": name})


# ── env.set: E2E decrypt + store + resolve ────────────────────────────────────
@pytest.mark.asyncio
async def test_env_set_decrypts_stores_and_resolves(store, keystore):
    pub = _seed_daemon_keypair()
    ciphertext = seal(pub, b"sk-secret-value")

    await _call_env_set("OPENAI_API_KEY", ciphertext, "agt_1")

    # Value landed in the keyring under the per-agent namespace (decrypted).
    assert (
        keystore.get(agent_env_service("agt_1"), "OPENAI_API_KEY")
        == "sk-secret-value"
    )

    # NAME-ONLY metadata row exists with origin='ui'.
    row = await store.fetchone(
        "SELECT scope, agent_id, name, origin FROM env_names"
        " WHERE scope='agent' AND agent_id=? AND name=?",
        ("agt_1", "OPENAI_API_KEY"),
    )
    assert row == {
        "scope": "agent",
        "agent_id": "agt_1",
        "name": "OPENAI_API_KEY",
        "origin": "ui",
    }

    # resolve() returns it.
    vault = EnvVault(store=store)
    assert vault.resolve("agt_1") == {"OPENAI_API_KEY": "sk-secret-value"}


@pytest.mark.asyncio
async def test_env_set_missing_agent_id_is_noop(store, keystore):
    pub = _seed_daemon_keypair()
    ciphertext = seal(pub, b"v")

    from synapse_worker.commands.env import handle_env_set

    # No agent_id in the idempotency key and none in the payload.
    ctx = CommandContext(command_type="env.set", idempotency_key="env.set")
    await handle_env_set(ctx, {"name": "X", "ciphertext": ciphertext})

    assert keystore.list_keys(agent_env_service("agt_1")) == []


@pytest.mark.asyncio
async def test_env_set_agent_id_fallback_from_payload(store, keystore):
    pub = _seed_daemon_keypair()
    ciphertext = seal(pub, b"vv")

    from synapse_worker.commands.env import handle_env_set

    ctx = CommandContext(command_type="env.set", idempotency_key="env.set")
    await handle_env_set(
        ctx, {"name": "X", "ciphertext": ciphertext, "agent_id": "agt_9"}
    )

    assert keystore.get(agent_env_service("agt_9"), "X") == "vv"


@pytest.mark.asyncio
async def test_env_set_bad_ciphertext_does_not_raise(store, keystore):
    _seed_daemon_keypair()
    # garbage that isn't a valid sealed box: handler must swallow, store nothing.
    await _call_env_set("X", "bm90LWEtc2VhbGVkLWJveA==", "agt_1")
    assert keystore.list_keys(agent_env_service("agt_1")) == []


# ── env.delete ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_env_delete_removes_value_and_row(store, keystore):
    pub = _seed_daemon_keypair()
    await _call_env_set("TOK", seal(pub, b"abcd-secret"), "agt_1")
    assert keystore.get(agent_env_service("agt_1"), "TOK") == "abcd-secret"

    await _call_env_delete("TOK", "agt_1")

    assert keystore.get(agent_env_service("agt_1"), "TOK") is None
    row = await store.fetchone(
        "SELECT name FROM env_names WHERE scope='agent' AND agent_id=? AND name=?",
        ("agt_1", "TOK"),
    )
    assert row is None


# ── resolution: shared -> agent merge + local-over-ui precedence ──────────────
@pytest.mark.asyncio
async def test_shared_then_agent_merge(store):
    vault = EnvVault(store=store)
    await vault.store_value("REGION", "us-east", shared=True, origin="local")
    await vault.store_value("ONLY_AGENT", "x", agent_id="agt_1", origin="local")

    resolved = vault.resolve("agt_1")
    assert resolved["REGION"] == "us-east"     # from shared
    assert resolved["ONLY_AGENT"] == "x"       # from agent


@pytest.mark.asyncio
async def test_agent_overrides_shared(store):
    vault = EnvVault(store=store)
    await vault.store_value("LOG_LEVEL", "info", shared=True, origin="local")
    await vault.store_value("LOG_LEVEL", "debug", agent_id="agt_1", origin="local")

    # Agent scope wins over shared for the same name.
    assert vault.resolve("agt_1")["LOG_LEVEL"] == "debug"


@pytest.mark.asyncio
async def test_local_overrides_ui_same_name(store, keystore):
    pub = _seed_daemon_keypair()
    # First a UI push, then a local set of the same name overwrites it.
    await _call_env_set("API_KEY", seal(pub, b"ui-pushed-secret"), "agt_1")
    vault = EnvVault(store=store)
    await vault.store_value(
        "API_KEY", "locally-set-secret", agent_id="agt_1", origin="local"
    )

    assert vault.resolve("agt_1")["API_KEY"] == "locally-set-secret"
    # The metadata origin reflects the winning (local) provenance.
    row = await store.fetchone(
        "SELECT origin FROM env_names WHERE scope='agent' AND agent_id=? AND name=?",
        ("agt_1", "API_KEY"),
    )
    assert row == {"origin": "local"}


# ── redaction registration ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_register_with_redaction_masks_value(store):
    # Fresh chain with Unit 6's redaction filter registered.
    reset_filter_chain()
    chain = get_filter_chain()
    flt = RedactionFilter()
    chain.register(flt)

    vault = EnvVault(store=store)
    await vault.store_value(
        "SECRET", "super-secret-token-1234", agent_id="agt_1", origin="local"
    )

    res = chain.screen_outbound("echoing super-secret-token-1234 in a log")
    assert "super-secret-token-1234" not in res.text
    assert res.manifest.counts.get("ENV", 0) >= 1


@pytest.mark.asyncio
async def test_plain_value_not_registered_for_redaction(store):
    reset_filter_chain()
    chain = get_filter_chain()
    chain.register(RedactionFilter())

    vault = EnvVault(store=store)
    # register_redaction=False => not masked even though stored.
    await vault.store_value(
        "PUBLIC_URL",
        "https://example.com/non-secret",
        agent_id="agt_1",
        origin="local",
        register_redaction=False,
    )

    res = chain.screen_outbound("visit https://example.com/non-secret today")
    assert "https://example.com/non-secret" in res.text


# ── CLI: set / list / rm ──────────────────────────────────────────────────────
def _cli_app():
    import typer

    from synapse_worker.cli import cmd_env

    app = typer.Typer()
    cmd_env.register(app)
    return app


def test_cli_set_list_rm(store, uplink, keystore):
    runner = CliRunner()
    app = _cli_app()

    # set
    res = runner.invoke(
        app, ["env", "set", "DB_URL=postgres://secret", "--agent", "agt_1"]
    )
    assert res.exit_code == 0, res.output
    assert keystore.get(agent_env_service("agt_1"), "DB_URL") == "postgres://secret"

    # NAME ONLY reported upstream as env.local.
    local_frames = uplink.of_type("env.local")
    assert any(
        f.payload.get("name") == "DB_URL" and f.payload.get("agent_id") == "agt_1"
        for f in local_frames
    )

    # list shows NAMES only — never the value.
    res = runner.invoke(app, ["env", "list", "--agent", "agt_1"])
    assert res.exit_code == 0, res.output
    assert "DB_URL" in res.output
    assert "postgres://secret" not in res.output

    # rm removes it.
    res = runner.invoke(app, ["env", "rm", "DB_URL", "--agent", "agt_1"])
    assert res.exit_code == 0, res.output
    assert keystore.get(agent_env_service("agt_1"), "DB_URL") is None

    res = runner.invoke(app, ["env", "list", "--agent", "agt_1"])
    assert "DB_URL" not in res.output


def test_cli_shared_scope(store, uplink, keystore):
    runner = CliRunner()
    app = _cli_app()
    res = runner.invoke(app, ["env", "set", "GLOBAL=val", "--shared"])
    assert res.exit_code == 0, res.output
    assert keystore.get(SHARED_ENV_SERVICE, "GLOBAL") == "val"


def test_cli_set_requires_scope(store):
    runner = CliRunner()
    app = _cli_app()
    res = runner.invoke(app, ["env", "set", "X=y"])
    assert res.exit_code != 0
