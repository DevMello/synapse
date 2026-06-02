"""Health snapshot shape (§6).

The foundation defines the dataclass + a best-effort collector (zeros if ``psutil`` is
absent). The Health/Heartbeat unit fills in resource sampling and the 15s emit loop.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from . import __version__

_START = time.monotonic()


@dataclass
class HealthSnapshot:
    version: str = __version__
    uptime_seconds: float = 0.0
    cpu_percent: float = 0.0
    mem_mb: float = 0.0
    disk_percent: float = 0.0
    active_runs: int = 0
    queue_depth: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def collect(*, active_runs: int = 0, queue_depth: int = 0) -> HealthSnapshot:
    """Best-effort snapshot. Resource fields are 0 if psutil isn't installed."""
    snap = HealthSnapshot(
        uptime_seconds=round(time.monotonic() - _START, 1),
        active_runs=active_runs,
        queue_depth=queue_depth,
    )
    try:  # psutil is optional in the foundation; the health unit depends on it.
        import psutil  # type: ignore

        snap.cpu_percent = psutil.cpu_percent(interval=None)
        proc = psutil.Process()
        snap.mem_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
        snap.disk_percent = psutil.disk_usage(".").percent
    except Exception:  # noqa: BLE001 - psutil missing or sampling failed
        pass
    return snap
