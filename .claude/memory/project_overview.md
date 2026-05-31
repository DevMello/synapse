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
  degrade. Daemon auth = **custom OAuth 2.0 Device Authorization Grant (RFC 8628, decided
  2026-05-31)**: `synapse login` → `POST /auth/device/code` (sends hostname/OS/version) →
  `user_code` (`ABCD-1234`)+`verification_uri`+`interval`; daemon polls
  `/auth/device/token` (`authorization_pending`/`slow_down`); user approves in the
  already-authenticated Web UI (shown the device metadata first); daemon then gets a
  short-lived access token + **rotating** refresh token → OS keyring (0600 encrypted-file
  fallback on headless VPS). **No password ever typed in the terminal.** Per-device tokens
  are **revocable** from the Web UI Daemons list (sets `revoked_at`, kills refresh token,
  closes the gRPC stream) — no password change, other daemons unaffected. Device identity
  = hostname/OS/last_ip/last_seen ("logged in on my-macbook-pro, last seen 2m ago"). Data:
  `device_authorizations` table + `daemons` gains device-identity + refresh_token_hash +
  revoked_at. (daemons aren't Supabase Auth users.)
  Watch telemetry write volume/cost → batch/downsample. **Deployment (2026-05-31): Web
  UI and Cloud Backend run on the SAME host** (one deployment unit) — a single reverse
  proxy / FastAPI static mount serves the Web UI bundle + REST + gRPC hub, so the browser
  loads the app and hits REST on ONE origin (no CORS). Supabase + daemons stay separate;
  static frontend replicates per node so horizontal scaling is unaffected.
  Details: docs/cloud-backend.md
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

**Two-tier capability model (decided 2026-05-31):** capabilities (MCP servers / plugins /
system tools) are **provisioned per-daemon, then selected per-agent** — never installed
straight onto an agent. (1) **Daemon tier** — `plugin.install`/`mcp.configure` provisions
the venv/process on the host (data: `daemon_capabilities`); makes it *available* but grants
no agent access. (2) **Agent tier** — `capability.attach`/`capability.detach` toggles which
of the daemon's available capabilities each agent may use (data: `agent_capabilities`);
instant, no re-install/teardown. **Default state = "defaults on, rest off"**: built-in
defaults (filesystem/fetch/git/**memory** MCP) are **auto-attached** to every agent (still
detachable per agent); every other capability is **opt-in per agent**. The Ruleset Engine's
"MCP gating" IS this agent-tier selection (so an unselected server/tool is simply not
callable). `plugin.remove` is daemon-tier (tears down + detaches from ALL agents). Web UI:
daemon tier on the Daemons page §4.2 (enable/configure on host), agent tier on the agent's
Tools/MCP + Plugins tabs §4.7 (toggle on/off). **Existing agent permission controls
(editable in web-ui §4.7, enforced by daemon Ruleset Engine §4.6):** command blockers
(allow/deny shell+tool calls = script execution), write-path guards, network host
allow-list, cost/tool-call caps, capability/MCP gating — each action block/require-HITL/warn,
per-agent over an org default. **Known gap (left as-is 2026-05-31):** filesystem *reads*
are NOT a first-class ruleset dimension — only the file-explorer plugin scopes reads to
bounded paths; writes are guarded but general read-path guarding was deliberately deferred.

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

**Agent Memory subsystem (decided 2026-05-31, tui-daemon §4.13):** every agent gets a
built-in persistent **memory API** (`agent.memory.store/query/get/list/delete`), surfaced
to CLI agents via a default **`memory` MCP server** and to API agents programmatically.
Storage is a **swappable Storage Provider plugin**: default `sqlite-memory` (local SQLite,
zero-setup), `vector-memory` (Chroma/Qdrant in a local **Docker** container for semantic
search; graceful fallback to SQLite if Docker absent), enterprise (future). Reads/writes
are **local-first** (speed); cloud sync is **Sync-on-Demand** — a background **`memory.delta`**
(redacted via §4.5 Layer A before upload) keeps a cloud snapshot; Web UI edits/pre-loads
round-trip back via a **`memory.sync`** command applied to the daemon's local store (the
source of truth). **KEY TRUST DECISION: agent memory is NOT E2E-encrypted** — unlike env
vars and checkpoints, the cloud stores it as **redacted plaintext under Supabase RLS +
encryption-at-rest**, *deliberately*, because the product requires the Web UI to read/edit
memory (debugging, HITL correction of false memories, knowledge-transfer pre-load,
analytics like "400 entries / 50MB"). On-device redaction is the guarantee that no raw
secret reaches the snapshot; raw secrets belong in the env-var vault, never in memory.
Data: cloud `agent_memory` table (redacted key/value/text, tags, optional embedding_ref,
version, bytes, updated_by) + per-agent rollups. Web UI: **Memory tab / Memory Editor**
(web-ui §4.17). Distinct from checkpoint "session memory" (§4.12 = in-flight conversation
state for resume, which IS E2E-encrypted).

**Why:** the design centers a tight trust boundary — execution + secrets + redaction
stay on the user's machine; the cloud is broker + historian + analytics only.

**How to apply:** when building any product, preserve the control-plane/data-plane
split and the three invariants above. Redaction must happen on the daemon before any
upload.
