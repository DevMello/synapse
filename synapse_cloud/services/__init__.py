"""Service-layer modules (business logic shared by routers/workers/hub).

Feature units add their own service modules here (e.g. `tokens.py`,
`versioning.py`, `telemetry_ingest.py`). Register inbound daemon-message
handlers in a service module that your router imports, so handler registration
happens at app startup via router autodiscovery.
"""
