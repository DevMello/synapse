# Synapse — Cloud Backend

> The control plane and nervous system. A stateless API + real-time WebSocket hub that
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
2. **Real-time brokering** — a WebSocket hub that routes commands (browser → daemon)
   and telemetry (daemon → browser) with sub-second latency.
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
                       ┌────────────────────────────────────────────────┐
   Daemons   ──WSS──►  │           Custom Realtime Tier (FastAPI)        │
   (TUI)               │  ┌──────────────┐   ┌────────────────────────┐  │
                       │  │ REST API     │   │  Daemon WebSocket Hub   │  │
                       │  │ (FastAPI)    │   │  (device-token auth,    │  │
                       │  └──────┬───────┘   │   strict delivery/HITL) │  │
                       │         │           └────────────┬───────────┘  │
                       └─────────┼────────────────────────┼──────────────┘
                                 │                         │
   Browsers  ──HTTPS───────────► │ (REST)                  │ (publishes telemetry)
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

> **Stack note:** Supabase consolidates Postgres (records + audit + telemetry),
> Auth (browser/user identity), Storage (blobs), and Realtime (browser fan-out) into
> one managed service. A **thin custom FastAPI WebSocket hub** is kept *only* for the
> daemon control link, which needs device-token auth and strict at-least-once delivery
> for commands/HITL that Supabase Realtime isn't shaped for. **ClickHouse is dropped
> from the MVP** — partitioned Postgres handles telemetry; revisit only if aggregation
> queries actually degrade.

---

## 3. Real-Time Layer

Synapse splits the real-time layer in two, because the daemon link and the browser link
have very different requirements:

### 3.1 Daemon link — custom FastAPI WebSocket hub

- **Daemon sockets** — one per worker, authenticated with a daemon device-token
  (issued by our own device-code flow, *not* Supabase Auth).
- This is a **thin custom service** because daemon control needs guarantees Supabase
  Realtime isn't built for: strict at-least-once delivery + idempotency for commands
  and HITL resolutions, device-token auth, and backpressure control.
- The hub stays **stateless** — routing/presence state lives in **Supabase Postgres**
  (presence rows with TTL via a heartbeat) or a small Redis instance if pub/sub fan-out
  between hub nodes is needed at scale. Any node can serve any daemon socket.
- **Wire format**: MessagePack (compact, high-volume telemetry).

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
  → custom hub publishes cmd to the target daemon over its WS  → daemon executes
  → daemon streams telemetry frames → hub → persists (Postgres/Storage)
    + publishes to Supabase Realtime channel org:{id}:agent:{id}
  → browser (subscribed via supabase-js) renders live trace
```

- **Delivery guarantees**: daemon-bound control + HITL frames are at-least-once with
  idempotency keys (custom hub); high-volume browser telemetry is best-effort live but
  durably persisted — the authoritative copy is always in Postgres/Storage, the live
  stream is a convenience.

---

## 4. Data Model (Postgres — system of record)

Core entities:

- **organizations** — tenant root; billing, settings.
- **users** — accounts; belong to orgs via **memberships** (role: owner/admin/operator/viewer).
- **daemons** — registered workers: name, tags, platform, version, last_seen, status,
  **e2e_public_key** (X25519 public key; the matching private key never leaves the daemon).
- **agents** — agent definitions: name, type (api/cli), platform, owning daemon,
  current_version, limits, status.
- **agent_versions** — immutable prompt/config snapshots (see Versioning §8).
- **schedules** — cron/interval/one-shot bindings to agents.
- **runs** — every execution: trigger source, status, started/ended, cost, token
  totals, exit code, redaction summary.
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
- **plugin_installs** — which plugin version is attached to which agent on which daemon,
  plus install status (`installing/ready/failed`) and exposed-tool capabilities.
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
- **Custom daemon WebSocket** for the daemon control link (commands, telemetry, HITL).
- **Supabase Realtime** for browser-facing live updates.
- **Inbound webhook endpoints** (`/hooks/{token}`) that authenticate, validate, and
  translate external events into `agent.run` commands routed to the right daemon.

### Auth (two identity planes)

- **Browser / users → Supabase Auth (GoTrue)**: email/password, OAuth providers, magic
  links; issues Supabase JWTs that carry `org_id`/role claims used by RLS policies and
  by the FastAPI layer.
- **Daemons → custom OAuth 2.0 device-code flow** (FastAPI): the daemon is not a human
  user, so it gets its own long-lived refresh token + short-lived access token, scoped
  to a single daemon. This token authenticates the daemon WebSocket and is what RLS
  checks for daemon-originated writes.

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
   to the audit log, and routes `hitl.resolve` back to the originating daemon over WS.
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
- **One-click install** resolves a listing and pushes it to a chosen daemon (and agent)
  via `agent.deploy` / `skill.install` / `plugin.install`. The cloud tracks
  `plugin_installs` status reported back by the daemon (`installing/ready/failed`).
- Supports importing from **existing external marketplaces** (published skill packs,
  **MCP registries**) via adapters — an external MCP server becomes an `mcp`-kind plugin.
- Skills and plugins are **platform-scoped**: the same agent can carry different
  skills/packs per OS, and the cloud only offers packs compatible with the target
  daemon's platform.

> Plugin *values/secrets* still follow the env-var rule (§10.5): the catalog holds
> manifests and metadata, never an installed pack's runtime credentials.

---

## 12. Scaling, Reliability, Security

- **Stateless API + custom hub** → scale out horizontally; presence/routing state in
  Postgres (or a small Redis if cross-node pub/sub fan-out is needed at scale).
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
- **Transport**: TLS everywhere; daemon (device-token) and browser (Supabase JWT)
  independently authenticated; RBAC enforced on every command and HITL resolution.
- **Cost control**: batch/downsample telemetry writes; Supabase self-hosts if vendor
  lock-in or per-row write cost becomes a concern at scale.

---

## 13. Tech Stack Summary

| Concern | Choice |
|---------|--------|
| API framework | FastAPI (Python) |
| Records + audit DB | **Supabase Postgres** (with RLS) |
| Telemetry DB | **Supabase Postgres**, partitioned (TimescaleDB optional); ClickHouse only at scale |
| Blob storage | **Supabase Storage** (S3-backed) |
| Browser realtime | **Supabase Realtime** (Broadcast + Presence) |
| Daemon realtime | Custom FastAPI WebSocket hub (MessagePack) |
| User/browser auth | **Supabase Auth** (GoTrue) |
| Daemon auth | Custom OAuth 2.0 device-code flow, JWT |
| Async jobs | Celery / Arq |
| Optional cache/pub-sub | Redis (only if needed for hub fan-out) |
| Notifications | Slack/Discord SDKs, SES/Postmark (or Supabase Edge Functions) |
| Wire format | MessagePack (daemon) / JSON (browser) |

See **[integration.md](integration.md)** for the end-to-end message flows that tie the
cloud to the daemon and Web UI.
