"""Synapse Cloud Backend — the broker/historian between the Web UI and TUI daemons.

See docs/cloud-backend.md and docs/integration.md for the full architecture. The
foundation (this package's top-level modules) provides shared seams that feature
modules plug into without editing each other's files:

  * config.py / db.py / deps.py / rbac.py / security.py — settings, DB, auth.
  * command_bus.py     — outbound commands to daemons (real impl = gRPC hub).
  * message_registry.py — inbound daemon-message handler registry.
  * realtime.py / storage.py / audit.py / notifications — side-effect seams.
  * app.py             — FastAPI factory with router + lifespan autodiscovery.

Each feature unit owns its own routers/services/workers/tests files and depends
only on these seams.
"""

__version__ = "0.1.0"
