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
  via **gRPC (HTTP/2, grpcio/grpc.aio, Protocol Buffers)** — a bidirectional `Connect`
  stream for control+HITL (daemon-initiated, so cloud→daemon commands need no inbound
  port) + a client-streaming `IngestTelemetry` RPC for the trace firehose, multiplexed
  over one HTTP/2 connection. Has a Textual TUI. **Agent env vars: E2E-encrypted (X25519/libsodium
  sealed box) — daemon holds private key, browser encrypts to its public key, cloud
  relays opaque ciphertext + stores var NAMES only (never values); daemon decrypts to
  OS keyring and injects at run time. Can also set vars locally via `synapse env set`.**
  Details: docs/tui-daemon.md
- **Cloud Backend** — FastAPI broker/historian. **Stack decision (2026-05-29): use
  Supabase** for Postgres+RLS (records/audit/telemetry), Auth (browser users), Storage
  (blobs), and Realtime (browser fan-out). Keep a **thin custom gRPC hub (grpc.aio over
  HTTP/2, Protocol Buffers) only for the daemon link** (needs device-token auth in call
  metadata + strict at-least-once delivery for commands/HITL that Supabase Realtime isn't
  shaped for). **Transport decision (2026-05-31): daemon link is gRPC, NOT WebSockets**
  (browser link stays Supabase Realtime/WSS — gRPC-Web is weaker for browser pub/sub).
  gRPC gives no cross-reconnect redelivery, so at-least-once + idempotency keys + seq/acks
  stay at the app layer (SQLite WAL offline buffer unchanged). **ClickHouse dropped from
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

**Input/Output Filtering middleware (on-device guardrails, tui-daemon.md §4.5):** two
layers run before content is acted on or uploaded. Layer A = PII/secret redaction
(regex/entropy/Presidio + user rules; salted tokens like `<REDACTED:API_KEY:a91f>`;
modes block/mask/hash). Layer B = prompt-injection/jailbreak guard — inbound screening
of untrusted tool/web content (instruction-override, exfiltration, tool-bypass) +
outbound screening of model output (self-instruction override, policy divergence,
secret-leak); detection via heuristics + local attack signatures + optional Ollama
classifier; actions map to the Ruleset Engine (block/require-approval/warn). **Trust
model: rules are enforced by the DAEMON, not the model** — a successful injection still
can't bypass a blocker. Findings (category/severity/action/redacted-excerpt, never raw
content) → immutable audit log + cloud injection-attempt anomaly detector (cloud
baselines per agent, alerts on spikes, can auto-pause). Configured per-agent over an
org default in web-ui §4.7; surfaced in Logs §4.10 + Alerts §4.13.

**Three invariants:** (1) browser and daemon never talk directly — cloud brokers all;
(2) cloud never executes agents or holds raw provider keys — those stay on the daemon;
(3) daemon connects outbound-only (no inbound ports). See docs/integration.md.

**Durable execution (checkpointing/resume):** long runs are checkpointed via a local
SQLite write-ahead journal (per-step: agent memory, current tool-call intent+result with
idempotency key, file-op journal, cost). Resume skips committed steps; mid-tool steps
without a result re-run only if idempotent else pause for HITL. Checkpoints sync to cloud
**E2E-encrypted to an ORG RECOVERY KEY** (separate from the per-daemon env-var key) so
the cloud stores opaque blobs + plaintext metadata only, and ANY authorized daemon in the
org can decrypt to resume after total local loss. Recovery: cloud detects heartbeat loss
→ run `interrupted`; on reconnect daemon `run.reconcile` uploads offline work; cloud can
`run.recover` onto another daemon. Details: docs/tui-daemon.md §4.12, cloud-backend.md §13.

**Why:** the design centers a tight trust boundary — execution + secrets + redaction
stay on the user's machine; the cloud is broker + historian + analytics only.

**How to apply:** when building any product, preserve the control-plane/data-plane
split and the three invariants above. Redaction must happen on the daemon before any
upload.
