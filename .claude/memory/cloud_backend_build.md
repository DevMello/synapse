---
name: cloud-backend-build
description: Cloud Backend is implemented (16 feature units on master) — build conventions, test strategy, and extension seams for adding features
metadata:
  type: project
---

The **Cloud Backend** (`synapse_cloud/`) is now implemented on `master` — no longer
docs-only. Built as a foundation + 16 parallel feature units, all merged. Integrated app
exposes ~61 REST paths + the WebSocket daemon hub; `python -c "from synapse_cloud.app import create_app; create_app()"` builds clean.

**Why:** executed the `distributed-whistling-blossom.md` plan via parallel worker agents off a
committed foundation, to build the whole spec (`docs/cloud-backend.md`) at once.

**How to apply — conventions any new feature MUST follow (these make changes conflict-free):**
- **Routers auto-discover**: drop a `synapse_cloud/routers/*.py` exposing a module-level
  `router = APIRouter()`. NEVER edit `app.py` (pkgutil imports them).
- **Arq tasks auto-discover**: `workers/*.py` export `tasks` / `cron_jobs`; `workers/__init__.py`
  aggregates. Don't edit it.
- **Inbound daemon frames**: `@on_daemon_message("<type>")` in `message_registry`; the WS hub
  (`ws_hub/routes.py`) dispatches every frame via `dispatch(type, ctx, payload)`. Don't edit the hub.
- **Outbound cloud→daemon**: `get_command_bus().send(daemon_id, command_type, payload, idempotency_key=)`.
- **Side-effect seams** (`realtime.py`, `storage.py`, `audit.py`, `notifications/base.py`,
  `command_bus.py`) each ship an in-memory fake auto-selected when `get_settings().is_test`.
  `audit.py` is the hash-chained ledger (Unit 16); preserve its `get_audit()`/`set_audit()`/
  `write(org_id, action, *, actor, resource_type, resource_id, run_id, detail)` surface.
- **DB**: `await service_db()` is service-role and **BYPASSES RLS** — every query MUST be
  explicitly `.eq("org_id", principal.org_id)`-scoped. `Principal` from `deps.py`
  (`get_principal`/`require_write`/`require_admin`).
- **Tests run against REAL Supabase** (project `synapse`, ref `gpxfylwhwdsswbgicgby`) — no DB
  fakes; only side-effects are faked. `make_test_org()` mints a unique RLS-isolated org per call
  so parallel test runs don't collide. The full suite is slow / occasionally GoTrue
  rate-limited under heavy back-to-back runs — prefer per-module runs.
- Schema is fully migrated; **do NOT add migrations** for existing tables. See [[project-overview]].
