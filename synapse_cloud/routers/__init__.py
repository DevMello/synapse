"""HTTP routers.

Each feature unit drops a module here exposing a module-level `router`
(an `APIRouter`). `synapse_cloud.app` autodiscovers and includes them — no edits
to a shared file, so units never conflict. Prefix/tag your router yourself,
e.g. `router = APIRouter(prefix="/agents", tags=["agents"])`.
"""
