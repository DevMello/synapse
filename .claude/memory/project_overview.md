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
  via WebSocket. Has a Textual TUI. **Agent env vars: E2E-encrypted (X25519/libsodium
  sealed box) — daemon holds private key, browser encrypts to its public key, cloud
  relays opaque ciphertext + stores var NAMES only (never values); daemon decrypts to
  OS keyring and injects at run time. Can also set vars locally via `synapse env set`.**
  Details: docs/tui-daemon.md
- **Cloud Backend** — FastAPI broker/historian. **Stack decision (2026-05-29): use
  Supabase** for Postgres+RLS (records/audit/telemetry), Auth (browser users), Storage
  (blobs), and Realtime (browser fan-out). Keep a **thin custom FastAPI WebSocket hub
  only for the daemon link** (needs device-token auth + strict at-least-once delivery
  for commands/HITL that Supabase Realtime isn't shaped for). **ClickHouse dropped from
  MVP** — partitioned Postgres handles telemetry; add columnar store only if analytics
  degrade. Daemon auth = custom OAuth device-code (daemons aren't Supabase Auth users).
  Watch telemetry write volume/cost → batch/downsample. Details: docs/cloud-backend.md
- **Web UI** — React/TS control surface. One-click agent deploy, Markdown prompt
  editor, versioning+diff+rollback, live trace viewer, analytics, approvals queue,
  marketplaces. Details: docs/web-ui.md

**Capability layering (don't conflate these three):** (1) **Skills** = knowledge/
behavior (prompts/instructions) — what an agent *knows*; (2) **Plugins / capability
packs** = runtime capabilities (browser-use, terminal-use, file-explorer, coding
venv/workspaces, MCP quick-installs) — what an agent *can do*, provisioned on the daemon
in isolated venvs/sandboxes and attached per-agent, installed one-click from the web;
(3) **MCP servers** = one mechanism a plugin uses to expose tools. Daemon ships default
MCP servers (filesystem, fetch, git). Plugin kinds: mcp/script/workspace/composite.
Details in docs/tui-daemon.md §4.11.

**Three invariants:** (1) browser and daemon never talk directly — cloud brokers all;
(2) cloud never executes agents or holds raw provider keys — those stay on the daemon;
(3) daemon connects outbound-only (no inbound ports). See docs/integration.md.

**Why:** the design centers a tight trust boundary — execution + secrets + redaction
stay on the user's machine; the cloud is broker + historian + analytics only.

**How to apply:** when building any product, preserve the control-plane/data-plane
split and the three invariants above. Redaction must happen on the daemon before any
upload.
