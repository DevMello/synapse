"""FastAPI application factory.

Routers are autodiscovered: every module under `synapse_cloud.routers` that
exposes a module-level `router` (an `APIRouter`) is included automatically, so
feature units never edit this file — they drop a router module and it appears.

The lifespan starts/stops the gRPC daemon hub (overridden by unit 2) so the hub
shares the app process. The Arq worker runs as a separate process
(`arq synapse_cloud.workers.WorkerSettings`), not in the web app.
"""
from __future__ import annotations

import importlib
import pkgutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI

from . import grpc_hub
from .config import get_settings


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
    await grpc_hub.startup(app)
    try:
        yield
    finally:
        await grpc_hub.shutdown(app)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Synapse Cloud", version="0.1.0", lifespan=_lifespan)

    for router in _discover_routers():
        app.include_router(router)

    dist = settings.web_ui_dist
    if dist and Path(dist).is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=dist, html=True), name="web-ui")

    return app


app = create_app()
