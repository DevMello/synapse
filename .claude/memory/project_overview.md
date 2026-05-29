---
name: project-overview
description: What Synapse is — a 3-product agent-manager platform (Web UI, Cloud Backend, TUI Daemon)
metadata:
  type: project
---

Synapse is an **agent manager platform** with three products, currently at the
product-design stage (docs only, no code yet).

- **TUI Worker Daemon** — Python (`synapse-worker` on PyPI) installed on user
  machines. Executes agents (API + CLI tools like `claude code`), redacts PII/secrets
  on-device, enforces rulesets/blockers, handles HITL pauses, connects outbound-only
  via WebSocket. Has a Textual TUI. Details: docs/tui-daemon.md
- **Cloud Backend** — FastAPI broker/historian. WebSocket hub (Redis pub/sub) routing
  commands (browser→daemon) and telemetry (daemon→browser). Postgres + ClickHouse + S3.
  Analytics, anomaly detection, versioning/rollback, audit log, marketplaces,
  notifications, HITL routing. Never executes agents or holds raw secrets.
  Details: docs/cloud-backend.md
- **Web UI** — React/TS control surface. One-click agent deploy, Markdown prompt
  editor, versioning+diff+rollback, live trace viewer, analytics, approvals queue,
  marketplaces. Details: docs/web-ui.md

**Three invariants:** (1) browser and daemon never talk directly — cloud brokers all;
(2) cloud never executes agents or holds raw provider keys — those stay on the daemon;
(3) daemon connects outbound-only (no inbound ports). See docs/integration.md.

**Why:** the design centers a tight trust boundary — execution + secrets + redaction
stay on the user's machine; the cloud is broker + historian + analytics only.

**How to apply:** when building any product, preserve the control-plane/data-plane
split and the three invariants above. Redaction must happen on the daemon before any
upload.
