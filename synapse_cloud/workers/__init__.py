"""Async worker (Arq) app with task + cron autodiscovery.

Each feature unit drops a module in this package exposing any of:
  * `tasks`     — a list of coroutine functions (Arq task functions)
  * `cron_jobs` — a list of `arq.cron.cron(...)` jobs

`WorkerSettings` aggregates them across all worker modules, so units never edit
a shared file. Run with: `arq synapse_cloud.workers.WorkerSettings`.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from ..config import get_settings


def _discover() -> tuple[list[Any], list[Any]]:
    funcs: list[Any] = []
    crons: list[Any] = []
    pkg = importlib.import_module(__name__)
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        m = importlib.import_module(f"{__name__}.{mod.name}")
        funcs.extend(getattr(m, "tasks", []) or [])
        crons.extend(getattr(m, "cron_jobs", []) or [])
    return funcs, crons


def _redis_settings():
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """Arq worker entrypoint. Functions/cron jobs are discovered at import."""

    functions, cron_jobs = _discover()
    redis_settings = _redis_settings()
