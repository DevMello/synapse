# Synapse — Cloud Backend

> The control plane and nervous system. A stateless REST API + gRPC daemon hub that
> brokers every message between the browser (Web UI) and the worker daemons (TUI),
> persists all telemetry, runs the analytics/anomaly engine, fans out notifications,
> and powers the marketplaces.

---

## 1. Purpose & Role

The Cloud Backend is the **only component both the Web UI and the TUI Daemon talk to**.
The browser never talks to a daemon directly, and a daemon never talks to a browser
directly — the cloud sits in the middle as an authenticated, auditable broker.

Its responsibilities:

1. **Identity & tenancy** — users, organizations, teams, roles, and the daemons/agents
   they own.
2. **Real-time brokering** — a gRPC daemon hub (HTTP/2) that routes commands
   (browser → daemon) and telemetry (daemon → browser) with sub-second latency.
3. **Persistence** — the system of record for agent definitions, prompt versions, run
   history, logs, tool calls, costs, and audit trails.
4. **Analytics & anomaly detection** — turn the raw telemetry firehose into trends,
   dashboards, and proactive alerts.
5. **Notifications & HITL routing** — deliver approval requests and completion alerts to
   Slack / Discord / Email and collect responses.
6. **Webhooks & gateways** — inbound triggers that start agents; outbound gateways
   agents interact with.
7. **Marketplaces** — host and broker installation of agents and skills.

> **Design principle:** the cloud is a *broker and historian*, not an *executor*. No
> agent code, no provider API keys, and no customer data execution happens in the
> cloud. That stays on the daemon. This keeps the trust boundary tight and the backend
> horizontally scalable.

---

## 2. High-Level Architecture

```
                       ┌────── Cloud Backend host (single machine) ──────┐
   Daemons  ──gRPC──►   │  ┌────────────┐ ┌──────────┐ ┌──────────────┐  │
   (TUI)    (HTTP/2)    │  │ Web UI     │ │ REST API │ │  gRPC Daemon │  │
                       │  │ static     │ │ (FastAPI)│ │  Hub (device │  │
                       │  │ bundle     │ │          │ │  auth, HITL) │  │
                       │  └─────┬──────┘ └────┬─────┘ └──────┬───────┘  │
                       │        └─ one reverse proxy ─┘      │           │
                       └────────────────┼───────────────────┼───────────┘
                                 │                         │
   Browsers  ──HTTPS───────────► │ (load app + REST, one origin)         │ (publishes telemetry)
   (Web UI)  ──WSS───────────────┼──────────► Supabase Realtime ◄──────┘
                                 │            (Broadcast + Presence → browser fan-out)
              ┌──────────────────┼──────────────────────────────────────────┐
              ▼                  ▼                          ▼                ▼
        ┌──────────────────────────────────────┐   ┌──────────────┐  ┌────────────┐
        │            SUPABASE                   │   │ Async Workers│  │  (optional)│
        │  ┌────────────┐  ┌────────────────┐   │   │  (Celery/Arq)│  │  ClickHouse│
        │  │ Postgres   │  │ Auth (GoTrue)  │   │   │ - rollups    │  │  added ONLY│
        │  │ + RLS      │  │ user/browser   │   │   │ - anomaly    │  │  if Postgres│
        │  │ records,   │  └────────────────┘   │   │ - notify     │  │  analytics  │
        │  │ audit,     │  ┌────────────────┐   │   │ - webhooks   │  │  outgrows   │
        │  │ telemetry  │  │ Storage (S3)   │   │   └──────────────┘  │  partitions│
        │  │ (partition)│  │ blobs/traces   │   │                     └────────────┘
        │  └────────────┘  └────────────────┘   │
        └──────────────────────────────────────┘
```

> **Co-location note:** the **Web UI and the Cloud Backend run on the same host** — one
> deployment unit. A single reverse proxy on that machine (or FastAPI's static mount)
> serves the built Web UI bundle, the REST API, and the gRPC daemon hub, so the browser
> loads the app and calls REST on **one origin (no CORS)**. The gRPC hub listens on the
> same host for daemon links. Supabase and the daemons stay separate.
>
> **Stack note:** Supabase consolidates Postgres (records + audit + telemetry),
> Auth (browser/user identity), Storage (blobs), and Realtime (browser fan-out) into
> one managed service. A **thin custom gRPC hub** (served by grpc.aio alongside FastAPI)
> is kept *only* for the daemon control link, which needs device-token auth and strict
> at-least-once delivery for commands/HITL that Supabase Realtime isn't shaped for.
> **ClickHouse is dropped
> from the MVP** — partitioned Postgres handles telemetry; revisit only if aggregation
> queries actually degrade.

---

## 3. Real-Time Layer

Synapse splits the real-time layer in two, because the daemon link and the browser link
have very different requirements:

### 3.1 Daemon link — custom gRPC hub (HTTP/2)

- **gRPC service `DaemonLink`** (grpc.aio), one long-lived stream per worker,
  authenticated with a daemon device-token in call metadata (issued by our own
  device-code flow, *not* Supabase Auth; optionally pinned with mTLS client certs).
- **Two RPCs** per daemon, multiplexed over its single HTTP/2 connection:
  - `Connect(stream DaemonMessage) → stream CloudMessage` — **bidirectional**; the cloud
    pushes commands/HITL resolutions down this stream, the daemon pushes HITL requests
    and `run.reconcile` up. The **daemon always initiates** it, so the cloud reaches the
    daemon without any inbound port on the user's machine.
  - `IngestTelemetry(stream TelemetryFrame) → TelemetryAck` — **client-streaming** for
    the high-volume trace/metric firehose, on its own HTTP/2 stream so telemetry can't
    head-of-line-block control or HITL.
- This is a **thin custom service** because daemon control needs guarantees Supabase
  Realtime isn't built for: strict at-least-once delivery + idempotency for commands
  and HITL resolutions (carried as app-level sequence numbers + acks in the proto, since
  gRPC won't redeliver across a reconnect), device-token auth, and backpressure control
  (HTTP/2 flow control + explicit acks).
- The hub stays **stateless** — routing/presence state lives in **Supabase Postgres**
  (presence rows with TTL via a heartbeat) or a small Redis instance if pub/sub fan-out
  between hub nodes is needed at scale. Any node can serve any daemon stream; a command
  for a daemon is routed to whichever node currently holds its `Connect` stream.
- **Wire format**: Protocol Buffers (the `.proto` is the contract; compact, strongly
  typed, code-generated for both daemon and cloud).

### 3.2 Browser link — Supabase Realtime

- Browsers subscribe via **Supabase Realtime** (Broadcast channels + Presence), keyed
  by tenant + resource (`org:{id}:agent:{id}`, `org:{id}:daemon:{id}`).
- RLS policies gate which channels a user may subscribe to.
- The custom hub (and async workers) **publish** telemetry/events into Supabase
  Realtime channels; the browser receives them live via `supabase-js`. No bespoke
  browser socket code required.
- **Wire format**: JSON (debuggable, native to `supabase-js`).

### Message flow

```
Browser clicks "Run agent"
  → REST/Realtime to backend  → validate auth/RBAC  → write run row (Postgres)
  → gRPC hub pushes cmd to the target daemon's Connect stream  → daemon executes
  → daemon streams telemetry frames (IngestTelemetry) → hub → persists (Postgres/Storage)
    + publishes to Supabase Realtime channel org:{id}:agent:{id}
  → browser (subscribed via supabase-js) renders live trace
```

- **Delivery guarantees**: daemon-bound control + HITL messages are at-least-once with
  idempotency keys (app-level acks over the gRPC stream); high-volume browser telemetry is best-effort live but
  durably persisted — the authoritative copy is always in Postgres/Storage, the live
  stream is a convenience.

---

## 4. Data Model (Postgres — system of record)

Core entities:

- **organizations** — tenant root; billing, settings, **recovery_public_key** (org
  X25519 public key used to encrypt run checkpoints; private half lives only in
  authorized daemons' keychains).
- **users** — accounts; belong to orgs via **memberships** (role: owner/admin/operator/viewer).
- **daemons** — registered workers: name, tags, platform, version, status,
  **device identity** (hostname, os_version, last_ip, last_seen — powers the Web UI's
  "logged in on *my-macbook-pro*, last seen 2m ago"), **refresh_token_hash** + issuance
  time, **revoked_at** (null = active), and **e2e_public_key** (X25519 public key; the
  matching private key never leaves the daemon).
- **device_authorizations** — short-lived rows backing the device-code login (§5):
  hashed `device_code`, `user_code` (`ABCD-1234`), status (`pending`/`authorized`/
  `denied`/`expired`), requested device metadata (hostname/os/ip), the authorizing
  `user_id` + `org_id` (set on approval), `interval`, `created_at`, `expires_at`. Purged
  after expiry/use.
- **agents** — agent definitions: name, type (api/cli), platform, owning daemon,
  current_version, limits, status.
- **agent_versions** — immutable prompt/config snapshots (see Versioning §8).
- **schedules** — cron/interval/one-shot bindings to agents.
- **runs** — every execution: trigger source, status (incl. `interrupted`/`recovering`),
  started/ended, cost, token totals, exit code, redaction summary.
- **run_checkpoints** — durable last-known-good state per run: **plaintext metadata**
  (sequence number, step cursor, status, cost-so-far, daemon) + a reference to the
  **E2E-encrypted payload blob** (agent memory/state) the cloud cannot read (see §13).
- **agent_memory** — **redacted snapshot** of an agent's persistent memory (tui-daemon
  §4.13), synced on demand from the daemon: `agent_id`, `namespace`, `key`, redacted
  `value`/text, `tags`, optional `embedding_ref`, `version`, `bytes`, `updated_at`,
  `updated_by` (daemon vs. a Web UI operator). Unlike `run_checkpoints`/env vars this is
  **not** E2E-encrypted — it is **RLS-scoped redacted plaintext** so the Web UI Memory
  Editor can read/edit it (see §13.5). Per-agent rollups (`entry_count`, `total_bytes`,
  `provider`) power the memory analytics view.
- **tool_calls** — per-run tool invocations: name, args (redacted), result (redacted),
  latency, cost.
- **audit_events** — immutable, append-only decision/action log (see Auditability §9).
- **gateways** — outbound integrations an agent can interact with.
- **webhooks** — inbound trigger endpoints.
- **notification_channels** — Slack/Discord/Email destinations + routing rules.
- **hitl_requests** — pending/resolved approval gates.
- **env_var_refs** — env-var **metadata only**: name, scope (agent/shared), origin
  (ui/local), target daemon, updated_by, updated_at. **No values, ever** (see §10.5).
- **plugins** — catalog of installable capability packs: name, kind
  (mcp/script/workspace/composite), versions, platform compatibility, declared
  permissions, manifest ref, checksum/signature, ratings.
- **daemon_capabilities** — *daemon tier*: what is **provisioned/enabled on each daemon**
  — `daemon_id`, capability ref (plugin version or configured MCP server), kind, install
  status (`installing/ready/failed`), exposed tools, configured endpoint/args (MCP). A
  capability must exist here before any agent can attach it.
- **agent_capabilities** — *agent tier*: the **per-agent selection** of which
  `daemon_capabilities` an agent may use — `agent_id`, `daemon_capability_id`, `enabled`,
  `attached_by`, `attached_at`. Built-in defaults (filesystem/fetch/git/memory) are
  represented as **auto-attached** (default-on); all other capabilities are opt-in rows.
  This is the source the Ruleset Engine's capability-gating is derived from.
- **marketplace_listings / installs** — published agents, skills & plugins, and installs.

High-volume, append-heavy data (raw **logs**, **metrics**, **reasoning traces**) lives
in **partitioned Postgres tables** (time-range partitions, BRIN indexes; TimescaleDB
hypertables optional). Writes are **batched/downsampled** by the daemon and async
workers — never one row per token — to keep insert volume (and Supabase usage cost)
sane. Large blobs (full traces, artifacts) go in **Supabase Storage** (S3-backed),
referenced by key from the run/tool_call rows.

Multi-tenancy is enforced with **Postgres Row-Level Security (RLS)**: every table is
scoped by `org_id`, and policies ensure a user/daemon only ever reads or writes its own
org's rows — even through the auto-generated Supabase data APIs.

> **Scale escape hatch:** if analytics aggregations over the telemetry tables ever
> degrade past what partitioned Postgres + rollups can serve, introduce a columnar
> store (ClickHouse) *only for telemetry* and keep records/audit in Postgres. Not in
> the MVP.

---

## 5. API Surface

- **REST (FastAPI)** for custom CRUD/business logic: agent deploy, marketplace install,
  analytics queries, webhook processing. Simple table reads/writes can also use
  Supabase's auto-generated data API (PostgREST) directly from the browser, gated by RLS.
- **Custom daemon gRPC service** (`DaemonLink` over HTTP/2) for the daemon control link
  (commands, telemetry, HITL).
- **Supabase Realtime** for browser-facing live updates.
- **Agent memory**: read the redacted snapshot via the RLS data API; edits/pre-loads go
  through REST (`/agents/{id}/memory`) which writes `agent_memory` and emits a
  `memory.sync` command to the owning daemon (§13.5).
- **Inbound webhook endpoints** (`/hooks/{token}`) that authenticate, validate, and
  translate external events into `agent.run` commands routed to the right daemon.
- **Daemon auth endpoints**: `POST /auth/device/code`, `POST /auth/device/token`
  (polling), `POST /auth/token` (refresh, rotating), and `POST /daemons/{id}/revoke`
  (RBAC-gated) — the OAuth 2.0 Device Authorization Grant detailed below.

### Auth (two identity planes)

- **Browser / users → Supabase Auth (GoTrue)**: email/password, OAuth providers, magic
  links; issues Supabase JWTs that carry `org_id`/role claims used by RLS policies and
  by the FastAPI layer.
- **Daemons → custom OAuth 2.0 device-code flow** (FastAPI): the daemon is not a human
  user, so it gets its own long-lived refresh token + short-lived access token, scoped
  to a single daemon. This token is presented as gRPC call metadata (validated by a
  server interceptor) to authenticate the daemon stream, and is what RLS checks for
  daemon-originated writes.

#### Daemon login — OAuth 2.0 Device Authorization Grant (RFC 8628)

A headless daemon (often on a VPS with no browser) must authenticate **without ever
typing the user's password into the terminal**. The device-code flow solves this: the
user proves identity in the *browser* (where they already have a Supabase session), and
the terminal only ever receives a scoped, revocable token.

```
TUI                         Cloud Backend                         Web UI (browser)
 │  POST /auth/device/code  │                                      │
 │  {hostname, os, version} │                                      │
 │ ───────────────────────► │  create device_authorizations row    │
 │                          │  (status=pending, TTL ~10m)           │
 │ ◄─────────────────────── │  {device_code, user_code "ABCD-1234", │
 │                          │   verification_uri, expires_in,       │
 │                          │   interval: 5}                        │
 │                          │                                      │
 │  print user_code + URL   │              user visits URL, logs in │
 │                          │              enters ABCD-1234, Confirm│
 │  POST /auth/device/token │ ◄──────────────────────────────────  │
 │  {device_code}  (×5s)    │  mark row authorized + bind org/user  │
 │ ───────────────────────► │  create daemons row + issue tokens    │
 │ ◄─────────────────────── │  {access_token, refresh_token}        │
 │  store tokens in keyring │                                      │
```

**Endpoints**

- `POST /auth/device/code` — **unauthenticated**. The daemon sends device metadata
  (`hostname`, `os_version`, daemon `version`; the cloud also records the request's
  source IP). Returns `device_code` (opaque, stored hashed), `user_code` (human-readable
  8-char `ABCD-1234`), `verification_uri` (+ `verification_uri_complete` with the code
  pre-filled for QR/click), `expires_in` (~600s), and `interval` (poll seconds, e.g. 5).
- `POST /auth/device/token` — **polling**, unauthenticated, sends the `device_code`.
  Mirrors RFC 8628 responses: `authorization_pending` (keep polling), `slow_down`
  (back off the interval), `access_denied` (user rejected), `expired_token` (restart),
  or **success** → `{access_token (short-lived, ~15m JWT), refresh_token (long-lived,
  rotating), token_type, expires_in}`.
- `POST /auth/token` — **refresh**: exchange the refresh token for a new access token;
  the **refresh token is rotated** on every use (old one invalidated → detects token
  theft/replay).

**Authorization (Web UI side)** — the user opens `verification_uri`, is already
authenticated via **Supabase Auth**, enters the `user_code`, and confirms. The backend
validates the code (unexpired, pending), shows the **requesting device's metadata** for
the user to verify ("`my-macbook-pro`, macOS 15.3, from 203.0.113.7 — approve?"), then
flips the row to `authorized`, **binds it to the user's `org_id`**, and provisions the
`daemons` row. Codes are single-use and rate-limited; entropy makes `user_code` guessing
infeasible within the TTL.

**Revocation** — the cloud keeps the issued refresh token (hashed) tied to the daemon.
A **Revoke** action in the Web UI (or losing a device) sets the daemon `revoked_at`,
**invalidates the refresh token** (so it can never mint a new access token) and **tears
down the daemon's live gRPC stream immediately** (the hub closes `Connect` with
`UNAUTHENTICATED`). The short-lived access token expires on its own within minutes;
revocation needs **no change to the user's primary password** and affects only that one
device.

---

## 6. Observability & Anomaly Detection

> Don't just store logs — surface *trends* and *alert proactively*.

### Pipeline

1. Daemons stream metrics per run: cost, tokens (in/out), latency, tool-call count,
   error rate, duration.
2. Async workers roll these into **time-bucketed aggregates** per agent/daemon/org
   (per-minute → per-hour → per-day) stored in dedicated Postgres rollup tables
   (or TimescaleDB continuous aggregates).
3. The **anomaly engine** runs continuously over the rollups.

### Detectors

- **Cost-per-task spike** — flag when an agent's cost/run exceeds its rolling baseline
  (e.g. EWMA + z-score, or > N× median over a trailing window).
- **Latency regression** — alert when p95 latency is ≥ 3× the historical p95.
- **Error-rate surge** — sudden jump in failed runs.
- **Token blow-up** — output tokens far above the agent's norm (runaway loops).
- **Schedule drift / silence** — an agent that normally runs stops producing runs.
- **Daemon offline** — missed heartbeats beyond threshold.
- **Injection-attempt rate** — surge in prompt-injection / jailbreak findings emitted
  by daemons' Input/Output Filtering middleware (see tui-daemon.md §4.5 Layer B). Each
  daemon reports guardrail findings (category, severity, action taken — block /
  require-approval / warn) as telemetry; the engine baselines per agent and flags
  spikes (e.g. a normally-clean agent suddenly tripping override/exfiltration patterns,
  often signalling a poisoned data source or a compromised upstream). Repeated blocks on
  the same agent escalate to a higher-severity alert and can auto-pause the agent
  pending review.

Methods: rolling baselines (EWMA), z-score / MAD outlier detection, and seasonal
decomposition for agents with daily/weekly patterns. Each detector emits an
**anomaly event** with severity, the offending metric, the baseline, and the observed
value — which flows into the notification fan-out and the Web UI's alerts feed.

---

## 7. Notifications & HITL Routing

A unified **notification service**:

- **Channels**: Slack (bot + interactive buttons), Discord (webhooks + buttons),
  Email (transactional via SES/Postmark), and in-app.
- **Events**: agent completion/failure, anomaly alerts, daemon offline, HITL requests,
  budget thresholds.
- **Routing rules**: per-agent / per-org rules ("send failures of `deploy-bot` to
  #oncall on Slack, completions to email").

### HITL fan-out

When a daemon emits `hitl.request`, the service:

1. Renders the proposed action + context into an **interactive message** (Slack/Discord
   buttons: Approve / Deny; Email with signed approve/deny links; Web UI banner).
2. Records a `hitl_requests` row (status `pending`, TTL).
3. On response, validates the actor's RBAC permission to approve, writes the decision
   to the audit log, and routes `hitl.resolve` back to the originating daemon on its
   `Connect` stream.
4. On timeout → default-deny and notify.

---

## 8. Agent Versioning & Rollbacks

> Treat prompts like code.

- Every change to an agent's prompt/config creates a new **immutable `agent_versions`
  row** (monotonic version number, author, timestamp, diff, optional message).
- An agent points at a `current_version`. Deploying a version pushes it to the daemon
  via `agent.update_prompt`.
- **One-click rollback**: set `current_version` back to a prior known-good version →
  the backend re-pushes it to the daemon. Because versions are immutable, rollback is
  always safe and instantaneous.
- Versions can be **tagged** (`known-good`, `production`) and compared with a diff view.
- Run records reference the exact `agent_version` they executed, so failures are always
  attributable to a specific prompt revision — enabling auto-suggested rollbacks when a
  new version's error rate spikes.

---

## 9. Auditability

> Every tool call and agent decision logged immutably.

- **`audit_events`** is append-only. Writes go through an interface that forbids
  update/delete; the table is protected by DB permissions and, optionally, periodic
  **hash-chaining** (each event stores the hash of the previous event → tamper-evident
  ledger).
- Captured for every run: the full reasoning chain — prompt version used, each model
  decision, each tool call with (redacted) inputs/outputs, ruleset evaluations, HITL
  approvals (who approved what, when, and why), and the final action + result.
- **Guardrail findings** are first-class audit events: every PII/secret redaction and
  every prompt-injection / jailbreak detection (the matched category, severity, the
  action taken, and a redacted excerpt — never the raw sensitive content) is appended
  to the ledger by the daemon, so an operator can later prove *what* was caught, *when*,
  and *how the system responded* — and correlate an injection spike against the runs
  that triggered it.
- This means for any consequential action (a deleted file, a force-push), an operator
  can reconstruct the **exact chain of reasoning** that produced it.
- Exportable (SIEM-friendly: JSON/CEF) and retained per the org's retention policy.

---

## 10. Webhooks & Gateways

- **Webhooks (inbound)** — each agent can expose signed webhook URLs. Inbound events
  (GitHub push, Stripe event, custom POST) are authenticated (HMAC signature), mapped
  to a payload template, and dispatched as an `agent.run` to the target daemon.
- **Gateways (outbound)** — configured per agent: HTTP endpoints, message queues, MCP
  servers, or third-party APIs the agent is permitted to interact with. The cloud
  stores the gateway definitions and policy; the daemon enforces and executes the
  actual calls (so credentials and traffic stay local).

### 10.5 Environment Variable Relay (zero-knowledge)

The cloud brokers agent env vars **without ever being able to read their values**.

- **Key registration**: each daemon registers an **X25519 public key** at pairing
  (`daemons.e2e_public_key`); the private key never leaves the daemon's keychain.
- **Set from Web UI**: the browser fetches the target daemon's public key, encrypts
  each value client-side (libsodium sealed box), and sends only **ciphertext**. The
  backend validates RBAC, writes an **`env_var_refs` metadata row (name/scope/origin —
  no value)**, and relays the ciphertext to the daemon via an `env.set` command. The
  ciphertext is **not persisted** — it is forwarded and dropped.
- **Zero-knowledge**: TLS protects the wire, but because the cloud is the broker, the
  E2E layer is what guarantees it cannot read the value — it holds no private key and
  stores no ciphertext. The daemon decrypts and stores the value in its OS keyring.
- **Set locally**: when an operator runs `synapse env set` on the daemon, the daemon
  reports the **name only** up to the backend (an `env_var_refs` row with
  `origin = local`) so the Web UI can list it read-only. The value never leaves the box.
- **Delete**: an `env.delete` command removes the keyring entry and the metadata row.
- **Audit**: every set/delete writes an `audit_event` (who, when, which var name, which
  daemon) — never the value.

> Net effect: the Web UI is the control surface, the daemon is the vault, and the cloud
> is a blind courier. Compromising the cloud yields env-var *names*, never *values*.

---

## 11. Marketplaces & Plugin Catalog

- **Agent**, **Skill**, and **Plugin** marketplaces — hosted catalogs of publishable,
  installable agent templates, skills, and **capability packs** (browser use, terminal
  use, file explorer, coding-workspace, and MCP quick-installs).
- Listings carry metadata: description, platform compatibility, required tools/MCP,
  permissions requested, versioning, ratings, and (for plugins) the **manifest +
  checksum/signature** the daemon verifies before provisioning.
- **One-click install** is **two-tier** (see tui-daemon §4.11): `plugin.install` /
  `mcp.configure` provisions a capability **on a chosen daemon** (tracked in
  `daemon_capabilities`, status `installing/ready/failed`); `capability.attach` /
  `capability.detach` then toggles it **per agent** (tracked in `agent_capabilities`).
  Built-in defaults are auto-attached; everything else is opt-in per agent.
- Supports importing from **existing external marketplaces** (published skill packs,
  **MCP registries**) via adapters — an external MCP server becomes an `mcp`-kind plugin.
- Skills and plugins are **platform-scoped**: the same agent can carry different
  skills/packs per OS, and the cloud only offers packs compatible with the target
  daemon's platform.

> Plugin *values/secrets* still follow the env-var rule (§10.5): the catalog holds
> manifests and metadata, never an installed pack's runtime credentials.

---

## 12. Scaling, Reliability, Security

- **Stateless API + gRPC hub** → scale out horizontally; presence/routing state in
  Postgres (or a small Redis if cross-node pub/sub fan-out is needed at scale). Each
  daemon's long-lived stream is pinned to one node, so an L4/HTTP-2-aware load balancer
  (or Redis-backed routing) directs a daemon-bound command to the node holding its stream.
- **Co-located frontend**: the Web UI is a static bundle, so it ships with each backend
  node (served by the same reverse proxy / static mount) and replicates for free — it
  adds no state and doesn't constrain horizontal scaling. Start as a single host;
  add nodes behind the LB when REST/gRPC load grows.
- **Async workers (Celery/Arq)** for analytics rollups, anomaly scans, notification
  fan-out, and webhook processing — decoupled from request latency.
- **Storage tiering (all Supabase)**: Postgres (records/audit + partitioned telemetry +
  rollups), Supabase Storage (blobs). Optional ClickHouse only if telemetry analytics
  outgrows Postgres.
- **Multi-tenancy isolation**: **Postgres RLS** scopes every row by `org_id` — enforced
  even through the auto-generated Supabase data API; plus per-org rate limits and quotas.
- **Zero raw secrets**: the cloud stores agent *config* and *policy*, never provider
  API keys; telemetry arrives pre-redacted from the daemon. **Env-var values are
  E2E-encrypted to the daemon** — the cloud relays opaque ciphertext and stores only
  variable *names* (§10.5).
- **Transport**: TLS everywhere (gRPC over HTTP/2 for the daemon link, optionally mTLS;
  HTTPS/WSS for the browser); daemon (device-token in call metadata) and browser
  (Supabase JWT) independently authenticated; RBAC enforced on every command and HITL
  resolution via a gRPC server interceptor.
- **Cost control**: batch/downsample telemetry writes; Supabase self-hosts if vendor
  lock-in or per-row write cost becomes a concern at scale.

---

## 13. Durable Execution & Recovery Orchestration

The cloud is the **recovery backstop** for long-running runs. It never executes or reads
state — it detects loss, holds the encrypted last-known-good checkpoint, and orchestrates
which daemon resumes.

- **Checkpoint ingest**: daemons stream encrypted checkpoint deltas; the cloud persists
  the **opaque payload blob** (Supabase Storage) + **plaintext metadata** row
  (`run_checkpoints`) it can use for orchestration and dashboards. It holds no key to
  decrypt the payload.
- **Heartbeat-loss detection**: when a daemon misses heartbeats beyond threshold, the
  cloud marks it `offline` and flips its in-flight runs to **`interrupted`** (not
  `failed` — outcome unknown), raising a recovery alert.
- **Reconnect reconciliation**: on reconnect the daemon sends `run.reconcile` with its
  per-run checkpoint sequence numbers. The cloud diffs against its last-synced state:
  runs the daemon finished offline are **uploaded and finalized**; still-running ones
  resume live streaming; nothing is double-counted (idempotency keys).
- **Cross-daemon recovery**: if the original daemon stays gone, the cloud issues
  `run.recover` to another authorized daemon in the org, handing it the run's
  last-known-good checkpoint reference. That daemon pulls the encrypted blob, decrypts
  it with the **org recovery key**, and resumes — all without the cloud ever seeing
  plaintext.
- **Audit**: interruptions, recoveries, and which daemon adopted a run are written to
  the immutable audit log (§9).
- **Web UI**: surfaces run status (`interrupted/recovering/resumed`), recovery alerts,
  and a manual "resume / restart / abort" override gated by the agent's resume policy.

### 13.5 Agent Memory Sync & Editor

The cloud is the **historian and editing surface** for agent memory (tui-daemon §4.13) —
never the source of truth (the daemon's local provider is). Flow:

- **Delta ingest**: daemons push **`memory.delta`** messages (redacted on-device via §4.5
  Layer A) on the `Connect` stream. The cloud upserts the `agent_memory` snapshot and
  recomputes per-agent rollups (`entry_count`, `total_bytes`). This is **sync-on-demand /
  background**, not a per-access stream — memory reads/writes stay local on the hot path.
- **Serve to Web UI**: the Memory Editor (web-ui §4) reads the latest snapshot via the
  RLS-scoped data API. Operators can **search, view, edit, delete, and pre-load** entries
  (knowledge transfer before first run) and see analytics ("Agent A: 400 entries, 50 MB").
- **Push edits back**: a Web UI edit/delete/pre-load writes the `agent_memory` row
  (`updated_by` = operator) and emits a **`memory.sync`** command to the owning daemon,
  which applies it to the **local provider** and acks. The daemon store remains
  authoritative; the cloud copy converges on the next ack/delta.
- **Trust boundary**: `agent_memory` is **redacted plaintext under RLS + encryption-at-
  rest**, *not* E2E-encrypted — a deliberate exception from checkpoints/env vars because
  the product requires the Web UI to read and correct memory. On-device redaction is the
  guarantee that no raw secret reaches this table; raw secrets belong in the env-var vault
  (§10.5), never in memory.
- **Audit**: operator memory edits/deletes/pre-loads are written to the immutable audit
  log (§9) with before/after redacted values.

---

## 14. Tech Stack Summary

| Concern | Choice |
|---------|--------|
| API framework | FastAPI (Python) |
| Records + audit DB | **Supabase Postgres** (with RLS) |
| Agent memory snapshot | **Supabase Postgres** (`agent_memory`, redacted + RLS, not E2E) |
| Telemetry DB | **Supabase Postgres**, partitioned (TimescaleDB optional); ClickHouse only at scale |
| Blob storage | **Supabase Storage** (S3-backed) |
| Browser realtime | **Supabase Realtime** (Broadcast + Presence) |
| Daemon realtime | Custom gRPC hub over HTTP/2 (grpc.aio, Protocol Buffers) |
| User/browser auth | **Supabase Auth** (GoTrue) |
| Daemon auth | Custom OAuth 2.0 device-code flow, JWT |
| Async jobs | Celery / Arq |
| Optional cache/pub-sub | Redis (only if needed for hub fan-out) |
| Notifications | Slack/Discord SDKs, SES/Postmark (or Supabase Edge Functions) |
| Wire format | Protocol Buffers (daemon gRPC) / JSON (browser) |

See **[integration.md](integration.md)** for the end-to-end message flows that tie the
cloud to the daemon and Web UI.
