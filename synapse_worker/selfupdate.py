"""Signature/checksum-verified worker self-update (§5).

The cloud can push a ``daemon.update`` command telling this worker to upgrade its own
package. Self-updating is a privileged act — a tampered or man-in-the-middled package
would run with the daemon's full authority — so the integrity gate here mirrors the
plugin-provisioning gate (``plugins.runtime.verify_checksum``): an artifact is downloaded
to a temp file, its sha256 is checked against the cloud-declared checksum, and only then
is it installed. If a public key is configured we ALSO require a valid Ed25519 signature
over the bytes. **Verification failure aborts the install** — an unverified package is
never executed.

The two side-effecting steps — the network download and the ``pip install`` subprocess —
are isolated behind injectable callables (:class:`UpdateRunner`) so the checksum-gating
logic can be unit-tested without a network or really upgrading the process.
"""
from __future__ import annotations

import hashlib
import os
import subprocess  # nosec B404 - used to invoke the package installer (pip/uv), argv-list form
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .logging import get_logger

log = get_logger(__name__)

__all__ = [
    "UpdateRequest",
    "UpdateResult",
    "UpdateRunner",
    "verify_checksum",
    "verify_signature",
    "verify_artifact",
    "apply_update",
]


# ── integrity gate ────────────────────────────────────────────────────────────
def _normalize_checksum(expected: str) -> str:
    """Strip an optional ``sha256:`` prefix and lowercase. '' => no checksum supplied."""
    want = (expected or "").strip().lower()
    if want.startswith("sha256:"):
        want = want.split(":", 1)[1]
    return want


def verify_checksum(data: bytes, expected: str) -> bool:
    """Return True iff ``sha256(data)`` matches ``expected`` (sha256[:]-prefix tolerated).

    Mirrors ``plugins.runtime.verify_checksum``. An EMPTY ``expected`` returns False here:
    a self-update is privileged, so unlike plugin provisioning we refuse to install a
    package that arrived without any checksum to verify against.
    """
    want = _normalize_checksum(expected)
    if not want:
        return False
    return hashlib.sha256(data).hexdigest() == want


def verify_signature(data: bytes, signature_b64: str, public_key_b64: str) -> bool:
    """Return True iff ``signature`` is a valid Ed25519 signature over ``data``.

    Only enforced when a publisher public key is configured (see
    :func:`_configured_public_key`). Any failure — bad base64, wrong key, missing PyNaCl —
    is a verification FAILURE (returns False), never an exception that could skip the gate.
    """
    if not signature_b64 or not public_key_b64:
        return False
    try:
        import base64

        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey

        verify_key = VerifyKey(base64.b64decode(public_key_b64.encode("ascii")))
        try:
            verify_key.verify(data, base64.b64decode(signature_b64.encode("ascii")))
        except BadSignatureError:
            return False
        return True
    except Exception:  # noqa: BLE001 - any crypto/setup error => not verified
        log.warning("self-update: signature verification errored; treating as invalid")
        return False


def _configured_public_key() -> str:
    """The publisher Ed25519 public key (base64), if the operator pinned one.

    Read from ``SYNAPSE_UPDATE_PUBLIC_KEY`` (env) so an operator can require signed
    updates without a config-schema change. When unset, signature checking is skipped and
    the checksum is the sole gate (the cloud is already an authenticated channel).
    """
    return os.environ.get("SYNAPSE_UPDATE_PUBLIC_KEY", "").strip()


@dataclass
class UpdateRequest:
    """A normalized ``daemon.update`` payload (read defensively from the wire)."""

    version: str = ""
    url: str = ""
    checksum: str = ""        # sha256 hex (optionally 'sha256:'-prefixed)
    signature: str = ""       # base64 Ed25519 signature over the package bytes

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "UpdateRequest":
        """Build from the cloud payload, tolerating field aliases / missing keys."""
        p = payload if isinstance(payload, dict) else {}
        checksum = p.get("sha256") or p.get("checksum") or ""
        return cls(
            version=str(p.get("version") or ""),
            url=str(p.get("url") or ""),
            checksum=str(checksum),
            signature=str(p.get("signature") or ""),
        )


@dataclass
class UpdateResult:
    ok: bool
    version: str = ""
    error: Optional[str] = None
    installed: bool = False  # whether the installer actually ran (proves the gate held)


# ── injectable side effects (network + installer) ─────────────────────────────
Downloader = Callable[[str], Awaitable[bytes]]
Installer = Callable[[str, str], Awaitable[None]]  # (path, version) -> None


async def _default_download(url: str) -> bytes:
    """Fetch the package bytes over https. Isolated so tests inject known bytes."""
    import httpx

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def _default_install(package_path: str, version: str) -> None:
    """Install the verified package via uv pip / pip (subprocess, argv-list, no shell).

    Prefers ``uv pip install`` when ``uv`` is importable (it is the project's installer);
    falls back to ``python -m pip install --upgrade``. Runs to completion and raises on a
    non-zero exit so callers can report the failure upstream.
    """
    argv = _install_argv(package_path)
    log.info("self-update: installing %s via %s", version or "package", argv[0])
    proc = subprocess.run(  # nosec B603 - argv list (no shell); path is a verified temp file
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        tail = (proc.stdout or b"").decode("utf-8", "replace")[-2000:]
        raise RuntimeError(f"installer exited {proc.returncode}: {tail}")


def _install_argv(package_path: str) -> list[str]:
    """Build the installer argv, preferring uv when present."""
    import importlib.util

    if importlib.util.find_spec("uv") is not None:
        return ["uv", "pip", "install", "--upgrade", package_path]
    return [sys.executable, "-m", "pip", "install", "--upgrade", package_path]


@dataclass
class UpdateRunner:
    """Bundles the two side-effecting steps so tests can inject fakes for both.

    Defaults perform a real download + install; unit tests pass a ``download`` that returns
    known bytes and an ``install`` that records the call, so the CHECKSUM-GATING logic is
    exercised end-to-end without touching the network or upgrading the process.
    """

    download: Downloader = _default_download
    install: Installer = _default_install


# ── orchestration ─────────────────────────────────────────────────────────────
def verify_artifact(data: bytes, req: UpdateRequest) -> tuple[bool, Optional[str]]:
    """Apply the full integrity gate to downloaded bytes. Returns (ok, error).

    Order: checksum first (cheap, always required), then signature IF a publisher key is
    pinned. The package is trusted only when every applicable check passes.
    """
    if not verify_checksum(data, req.checksum):
        return False, "checksum mismatch (or no checksum supplied)"
    pub = _configured_public_key()
    if pub:
        if not verify_signature(data, req.signature, pub):
            return False, "signature verification failed"
    return True, None


async def apply_update(
    req: UpdateRequest, *, runner: Optional[UpdateRunner] = None
) -> UpdateResult:
    """Download, VERIFY, then install — aborting before install on any failure.

    Returns an :class:`UpdateResult`; ``installed`` is True only if the integrity gate
    passed and the installer ran. Never raises into the caller (the command handler reports
    the result upstream); never installs an unverified package.
    """
    runner = runner or UpdateRunner()

    if not req.url:
        return UpdateResult(ok=False, version=req.version, error="no package url")

    # 1. Download to memory (and, after verification, a temp file for the installer).
    try:
        data = await runner.download(req.url)
    except Exception as exc:  # noqa: BLE001 - network/IO failure aborts cleanly
        log.warning("self-update: download failed: %s", exc)
        return UpdateResult(ok=False, version=req.version, error=f"download failed: {exc}")

    # 2. INTEGRITY GATE — verify BEFORE the package ever touches the installer.
    ok, why = verify_artifact(data, req)
    if not ok:
        log.error("self-update: ABORTING — %s (version=%s)", why, req.version or "?")
        return UpdateResult(ok=False, version=req.version, error=why, installed=False)

    # 3. Install the now-verified bytes from a temp file.
    tmp_path: Optional[str] = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix="synapse-worker-", suffix=_artifact_suffix(req.url)
        )
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        await runner.install(tmp_path, req.version)
    except Exception as exc:  # noqa: BLE001 - install failure is reported, not raised
        log.exception("self-update: install failed")
        return UpdateResult(ok=False, version=req.version, error=f"install failed: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:  # best-effort temp cleanup
                pass

    log.info("self-update: installed version=%s", req.version or "(unspecified)")
    return UpdateResult(ok=True, version=req.version, installed=True)


def _artifact_suffix(url: str) -> str:
    """Preserve a recognizable package suffix (.whl/.tar.gz) so pip can identify it."""
    lowered = url.lower()
    for suffix in (".whl", ".tar.gz", ".zip"):
        if lowered.endswith(suffix):
            return suffix
    return ".whl"
