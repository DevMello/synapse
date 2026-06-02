"""On-disk layout under ~/.synapse, with owner-only permissions.

All daemon state (tokens fallback, agent defs, plugin venvs, the SQLite store) lives
under a single base dir. Everything is created ``0700``/``0600`` so other local users
can't read it (cloud-backend.md / tui-daemon.md §2). On Windows ``chmod`` only toggles
the read-only bit; a full user-scoped ACL is applied by the service-install unit, but we
still restrict what we can here.
"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .config import Settings, get_settings

IS_WINDOWS = os.name == "nt"


@dataclass(frozen=True)
class WorkerPaths:
    home: Path

    @property
    def agents_dir(self) -> Path:
        return self.home / "agents"

    @property
    def plugins_dir(self) -> Path:
        return self.home / "plugins"

    @property
    def keys_dir(self) -> Path:
        return self.home / "keys"

    @property
    def db_path(self) -> Path:
        return self.home / "state.db"

    @property
    def config_path(self) -> Path:
        return self.home / "config.toml"

    @property
    def token_file(self) -> Path:
        """Encrypted-token fallback for headless boxes with no OS keychain."""
        return self.keys_dir / "tokens.enc"

    def agent_dir(self, agent_id: str) -> Path:
        return self.agents_dir / agent_id

    def plugin_dir(self, name: str) -> Path:
        return self.plugins_dir / name

    def ensure_layout(self) -> None:
        for d in (self.home, self.agents_dir, self.plugins_dir, self.keys_dir):
            d.mkdir(parents=True, exist_ok=True)
            restrict_dir(d)


def paths_for(settings: Settings | None = None) -> WorkerPaths:
    s = settings or get_settings()
    return WorkerPaths(home=s.home_dir)


def get_paths() -> WorkerPaths:
    return paths_for(get_settings())


def restrict_dir(path: Path) -> None:
    """Best-effort 0700 on the directory (owner-only)."""
    try:
        os.chmod(path, stat.S_IRWXU)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pass


def restrict_file(path: Path) -> None:
    """Best-effort 0600 on a file (owner read/write only)."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pass


def secure_write(path: Path, data: bytes | str) -> None:
    """Write a file with owner-only perms (created restricted, never world-readable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    restrict_dir(path.parent)
    if isinstance(data, str):
        data = data.encode("utf-8")
    # Open with 0600 from the start so there's no readable window. O_BINARY on
    # Windows prevents \n -> \r\n translation that would corrupt binary payloads
    # (e.g. sealed ciphertext / keys); it's absent (0) on POSIX.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    mode = stat.S_IRUSR | stat.S_IWUSR
    fd = os.open(path, flags, mode)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    restrict_file(path)
