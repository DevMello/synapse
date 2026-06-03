"""Unit 2 — Auth & device login. Self-contained: no network, no real keychain.

The cloud HTTP is mocked with an in-process ``httpx.MockTransport`` whose device-token
endpoint walks pending → authorized → tokens, matching the error bodies
``synapse_cloud/routers/auth_device.py`` returns. The FileKeystore is exercised against a
tmp path; ``synapse init`` is driven via Typer's CliRunner.
"""
from __future__ import annotations

import base64
import json

import httpx
import pytest
from typer.testing import CliRunner

from synapse_worker.auth import keys
from synapse_worker.auth.device_flow import (
    DeviceFlowClient,
    DeviceFlowError,
)
from synapse_worker.auth.keystore_impl import FileKeystore
from synapse_worker.cli.main import app


# ── helpers ───────────────────────────────────────────────────────────────────
def _make_jwt(daemon_id: str, org_id: str) -> str:
    """A minimal unsigned-ish HS256 JWT (we only ever read the unverified payload)."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": daemon_id, "org_id": org_id}).encode()
    ).rstrip(b"=")
    return f"{header.decode()}.{payload.decode()}.sig"


def _cloud_transport(*, pending_polls: int = 2, deny: bool = False) -> httpx.MockTransport:
    """A mock cloud: device/code then N pending polls, then authorized tokens (or denied)."""
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/device/code":
            return httpx.Response(
                200,
                json={
                    "device_code": "DEV-CODE-123",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://cloud.example/activate",
                    "verification_uri_complete": "https://cloud.example/activate?user_code=ABCD-1234",
                    "interval": 1,
                    "expires_in": 600,
                },
            )
        if request.url.path == "/auth/device/token":
            if deny:
                return httpx.Response(400, json={"error": "access_denied"})
            if state["polls"] < pending_polls:
                state["polls"] += 1
                # FastAPI wraps detail={"error":...} as {"detail":{"error":...}}.
                return httpx.Response(400, json={"detail": {"error": "authorization_pending"}})
            return httpx.Response(
                200,
                json={
                    "access_token": _make_jwt("daemon-1", "org-9"),
                    "refresh_token": "refresh-xyz",
                    "token_type": "Bearer",
                    "expires_in": 900,
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _client(transport: httpx.MockTransport) -> DeviceFlowClient:
    return DeviceFlowClient(
        "https://cloud.example", client=httpx.Client(transport=transport)
    )


# ── device flow ───────────────────────────────────────────────────────────────
def test_device_flow_pending_then_authorized():
    sleeps: list[float] = []
    with _client(_cloud_transport(pending_polls=2)) as c:
        device = c.request_device_code(
            hostname="host", os_version="os", daemon_version="0.1.0"
        )
        assert device.user_code == "ABCD-1234"
        tokens = c.poll_for_token(device, sleep=sleeps.append)
    assert tokens.refresh_token == "refresh-xyz"
    # Two pending polls => two inter-poll sleeps before success.
    assert len(sleeps) == 2


def test_device_flow_access_denied_aborts():
    with _client(_cloud_transport(deny=True)) as c:
        device = c.request_device_code(
            hostname="h", os_version="o", daemon_version="0.1.0"
        )
        with pytest.raises(DeviceFlowError, match="denied"):
            c.poll_for_token(device, sleep=lambda _: None)


def test_device_flow_slow_down_increases_interval():
    intervals: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/device/code":
            return httpx.Response(
                200,
                json={
                    "device_code": "d",
                    "user_code": "AAAA-1111",
                    "verification_uri": "u",
                    "verification_uri_complete": "uc",
                    "interval": 5,
                    "expires_in": 600,
                },
            )
        # First poll: slow_down, then success.
        if not intervals_seen["slowed"]:
            intervals_seen["slowed"] = True
            return httpx.Response(400, json={"error": "slow_down"})
        return httpx.Response(
            200,
            json={
                "access_token": _make_jwt("d2", "o2"),
                "refresh_token": "r",
                "token_type": "Bearer",
                "expires_in": 1,
            },
        )

    intervals_seen = {"slowed": False}
    transport = httpx.MockTransport(handler)
    with _client(transport) as c:
        device = c.request_device_code(hostname="h", os_version="o", daemon_version="v")
        c.poll_for_token(device, sleep=intervals.append)
    # interval started at 5, slow_down bumped it to 10 before the (only) sleep.
    assert intervals == [10]


def test_device_flow_expiry_times_out():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/device/code":
            return httpx.Response(
                200,
                json={
                    "device_code": "d",
                    "user_code": "AAAA-1111",
                    "verification_uri": "u",
                    "verification_uri_complete": "uc",
                    "interval": 1,
                    "expires_in": 5,
                },
            )
        return httpx.Response(400, json={"error": "authorization_pending"})

    # Fake clock that jumps past the deadline on the second check.
    ticks = iter([0.0, 0.0, 100.0, 100.0, 100.0])
    with _client(httpx.MockTransport(handler)) as c:
        device = c.request_device_code(hostname="h", os_version="o", daemon_version="v")
        with pytest.raises(DeviceFlowError, match="expired"):
            c.poll_for_token(device, sleep=lambda _: None, now=lambda: next(ticks))


# ── keys: token + keypair storage ──────────────────────────────────────────────
def test_store_tokens_and_keypair_roundtrip(keystore):
    keys.store_tokens("access-abc", "refresh-def", keystore=keystore)
    assert keys.get_access_token(keystore=keystore) == "access-abc"
    assert keys.get_refresh_token(keystore=keystore) == "refresh-def"

    pair = keys.ensure_daemon_keypair(keystore=keystore)
    assert pair.public_key and pair.private_key
    # Idempotent: a second call returns the same identity, never rotating it.
    again = keys.ensure_daemon_keypair(keystore=keystore)
    assert again.private_key == pair.private_key
    assert keys.get_daemon_public_key(keystore=keystore) == pair.public_key


def test_org_recovery_key_store_get(keystore):
    assert keys.get_org_recovery_key(keystore=keystore) is None
    keys.store_org_recovery_key("pub-key", "priv-key", keystore=keystore)
    rk = keys.get_org_recovery_key(keystore=keystore)
    assert rk is not None
    assert rk.public_key == "pub-key"
    assert rk.private_key == "priv-key"


# ── FileKeystore (real, against tmp) ───────────────────────────────────────────
def test_file_keystore_roundtrip(tmp_path):
    from synapse_worker.paths import WorkerPaths

    paths = WorkerPaths(home=tmp_path / "fks")
    paths.ensure_layout()
    ks = FileKeystore(paths)

    assert ks.get("svc", "k") is None
    ks.set("svc", "k", "v1")
    ks.set("svc", "k2", "v2")
    assert ks.get("svc", "k") == "v1"
    assert sorted(ks.list_keys("svc")) == ["k", "k2"]

    # Persists across a fresh instance (re-reads the encrypted blob + key file).
    ks2 = FileKeystore(paths)
    assert ks2.get("svc", "k2") == "v2"

    ks2.delete("svc", "k")
    assert ks2.get("svc", "k") is None
    assert ks2.list_keys("svc") == ["k2"]

    # The on-disk blob is ciphertext, not plaintext tokens.
    raw = paths.token_file.read_bytes()
    assert b"v2" not in raw


def test_file_keystore_survives_binary_ciphertext_on_windows(tmp_path):
    # Regression: secure_write must round-trip RAW ciphertext containing 0x0a/0x0d bytes
    # (the Windows CRLF-translation bug). Write enough entries that the sealed blob is
    # large enough to almost certainly contain both bytes, then re-read from disk.
    from synapse_worker.paths import WorkerPaths

    paths = WorkerPaths(home=tmp_path / "fks-bin")
    paths.ensure_layout()
    ks = FileKeystore(paths)
    for i in range(50):
        ks.set("synapse:daemon", f"k{i}", f"value-{i}-{'x' * 30}")

    raw = paths.token_file.read_bytes()
    assert 0x0A in raw and 0x0D in raw  # the bytes the bug used to corrupt

    fresh = FileKeystore(paths)  # re-reads + decrypts the blob from disk
    assert all(fresh.get("synapse:daemon", f"k{i}") == f"value-{i}-{'x' * 30}" for i in range(50))


# ── login: full flow wiring (tokens -> keystore, ids -> store.kv) ───────────────
@pytest.mark.asyncio
async def test_login_persists_tokens_and_identity(monkeypatch, store, keystore):
    transport = _cloud_transport(pending_polls=1)

    # Patch the client factory so the command uses our mock transport + no real sleeps.
    real_init = DeviceFlowClient.__init__

    def fake_init(self, base, **kw):
        real_init(self, base, client=httpx.Client(transport=transport))

    monkeypatch.setattr(DeviceFlowClient, "__init__", fake_init)
    # poll_for_token sleeps via time.sleep by default; neutralize it.
    monkeypatch.setattr("time.sleep", lambda _: None)

    runner = CliRunner()
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0, result.output

    assert keys.get_access_token(keystore=keystore) is not None
    assert keys.get_refresh_token(keystore=keystore) == "refresh-xyz"
    assert keys.get_daemon_public_key(keystore=keystore)
    # Raw token never printed.
    assert "refresh-xyz" not in result.output

    assert await store.kv_get("daemon_id") == "daemon-1"
    assert await store.kv_get("org_id") == "org-9"


# ── CLI surface ────────────────────────────────────────────────────────────────
def test_login_help_works():
    result = CliRunner().invoke(app, ["login", "--help"])
    assert result.exit_code == 0
    assert "device-code" in result.output or "Pair" in result.output


def test_init_writes_config(settings):
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "--name", "box-1", "--tags", "gpu,prod", "--max-concurrent-runs", "7", "--yes"],
    )
    assert result.exit_code == 0, result.output

    cfg = paths_config(settings)
    assert cfg.exists()
    text = cfg.read_text(encoding="utf-8")
    assert 'daemon_name = "box-1"' in text
    assert "max_concurrent_runs = 7" in text
    assert '"gpu"' in text and '"prod"' in text

    # tomllib must parse what we wrote.
    import tomllib

    data = tomllib.loads(text)
    assert data["daemon"]["daemon_name"] == "box-1"
    assert data["daemon"]["max_concurrent_runs"] == 7


def test_init_refuses_overwrite_without_force(settings):
    runner = CliRunner()
    first = runner.invoke(app, ["init", "--name", "a", "--yes"])
    assert first.exit_code == 0
    second = runner.invoke(app, ["init", "--name", "b", "--yes"])
    assert second.exit_code == 1
    assert "already exists" in second.output


def paths_config(settings):
    from synapse_worker.paths import paths_for

    return paths_for(settings).config_path
