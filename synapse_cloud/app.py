"""FastAPI application factory.

Routers are autodiscovered: every module under `synapse_cloud.routers` that
exposes a module-level `router` (an `APIRouter`) is included automatically, so
feature units never edit this file — they drop a router module and it appears.

The lifespan starts/stops the WebSocket daemon hub AND the in-process periodic-job
scheduler (heartbeat sweep, rollups, anomaly, notifications) — so the whole backend
is just `uvicorn` + Supabase, with no separate worker process and no Redis. The
scheduler is skipped under SYNAPSE_ENV=test.
"""
from __future__ import annotations

import importlib
import pkgutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI

from . import ws_hub
from .config import get_settings
from .scheduler import Scheduler, discover_periodic_jobs


def _discover_routers() -> list[APIRouter]:
    from . import routers as routers_pkg

    found: list[APIRouter] = []
    for mod in pkgutil.iter_modules(routers_pkg.__path__):
        if mod.name.startswith("_"):
            continue
        m = importlib.import_module(f"{routers_pkg.__name__}.{mod.name}")
        router = getattr(m, "router", None)
        if isinstance(router, APIRouter):
            found.append(router)
    return found


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await ws_hub.startup(app)
    scheduler: Scheduler | None = None
    if not get_settings().is_test:
        scheduler = Scheduler(discover_periodic_jobs())
        await scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()
        await ws_hub.shutdown(app)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Synapse Cloud", version="0.1.0", lifespan=_lifespan)

    for router in _discover_routers():
        app.include_router(router)

    dist = settings.web_ui_dist
    if dist and Path(dist).is_dir():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        dist_path = Path(dist)

        # Serve the built asset chunks (JS, CSS, sourcemaps) from /assets.
        if (dist_path / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="web-ui-assets")

        # Catch-all: serve root-level static files (favicon, manifest, …) by path,
        # and fall back to index.html for every SPA route so Ctrl+R works on deep URLs.
        @app.get("/{full_path:path}", include_in_schema=False)
        async def _spa_fallback(full_path: str) -> FileResponse:
            candidate = dist_path / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist_path / "index.html")

    return app


app = create_app()
