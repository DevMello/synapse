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
                       ┌────────────────────────────────────────────┐
   Browsers  ──WSS──►  │             API / Realtime Tier            │
   (Web UI)  ──HTTPS─► │  ┌──────────────┐   ┌───────────────────┐  │
                       │  │ REST/GraphQL │   │  WebSocket Hub     │  │
   Daemons   ──WSS──►  │  │  (FastAPI)   │   │  (stateless +      │  │
   (TUI)               │  └──────┬───────┘   │   Redis pub/sub)   │  │
                       │         │           └─────────┬─────────┘  │
                       └─────────┼─────────────────────┼────────────┘
                                 │                      │
              ┌──────────────────┼──────────────────────┼─────────────────┐
              ▼                  ▼                      ▼                  ▼
        ┌───────────┐    ┌──────────────┐      ┌──────────────┐   ┌──────────────┐
        │ Postgres  │    │ Redis        │      │ Timeseries / │   │ Object Store │
        │ (records, │    │ (pub/sub,    │      │ ClickHouse   │   │ (S3: large   │
        │  audit)   │    │  presence,   │      │ (logs,       │   │  log blobs,  │
        │           │    │  rate limit) │      │  metrics)    │   │  artifacts)  │
        └───────────┘    └──────────────┘      └──────────────┘   └──────────────┘
              ▲                                        ▲
              │            ┌──────────────────────────┐│
              └────────────┤  Async Workers (Celery)  ├┘
                           │  - analytics rollups     │
                           │  - anomaly detection     │
                           │  - notification fan-out  │
                           │  - webhook processing    │
                           └──────────────────────────┘
```

---

## 3. Real-Time WebSocket Hub

The defining feature of the backend. Two classes of socket connect:

- **Daemon sockets** — one per worker, authenticated with the daemon token.
- **Browser sockets** — one (or more) per logged-in user session.

### Routing model

- Every daemon and browser session subscribes to **Redis pub/sub** channels keyed by
  tenant + resource (`org:{id}:daemon:{id}`, `org:{id}:agent:{id}`, `user:{id}`).
- The hub is **stateless** — any node can serve any socket, because routing state
  lives in Redis. This lets the realtime tier scale horizontally behind a load
  balancer with sticky-by-nothing semantics.
- **Presence** (which daemons/browsers are online) is tracked in Redis with TTL keys
  refreshed by heartbeats.

### Message flow

```
Browser clicks "Run agent"
  → WS frame to hub  → validate auth/RBAC  → publish cmd to org:{id}:daemon:{id}
  → daemon (subscribed) receives cmd  → executes
  → daemon streams telemetry frames  → hub  → persists + republishes
  → browser (subscribed to org:{id}:agent:{id}) renders live trace
```

- **Wire format**: MessagePack to daemons (compact), JSON to browsers (debuggable).
- **Backpressure**: per-socket send queues with drop-oldest for non-critical telemetry
  and guaranteed delivery for control/HITL frames.
- **Delivery guarantees**: control + HITL frames are at-least-once with idempotency
  keys; high-volume log frames are best-effort live but durably persisted (the
  authoritative copy is in storage, the live stream is a convenience).

---

## 4. Data Model (Postgres — system of record)

Core entities:

- **organizations** — tenant root; billing, settings.
- **users** — accounts; belong to orgs via **memberships** (role: owner/admin/operator/viewer).
- **daemons** — registered workers: name, tags, platform, version, last_seen, status.
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
- **marketplace_listings / installs** — published agents & skills, and installations.

High-volume, append-heavy data (raw **logs**, **metrics**, **reasoning traces**) lives
in **ClickHouse** (or Timescale) for cheap time-series storage and fast aggregation;
large blobs (full traces, artifacts) in **object storage (S3)** referenced by key.

---

## 5. API Surface

- **REST/GraphQL (FastAPI)** for CRUD: agents, schedules, gateways, webhooks, channels,
  marketplace, analytics queries, user/org management.
- **WebSocket** for everything real-time (commands, telemetry, presence, HITL).
- **Inbound webhook endpoints** (`/hooks/{token}`) that authenticate, validate, and
  translate external events into `agent.run` commands routed to the right daemon.
- **OAuth 2.0** (device-code flow for daemons, authorization-code + PKCE for the
  browser). JWT access tokens (short-lived) + rotating refresh tokens.

---

## 6. Observability & Anomaly Detection

> Don't just store logs — surface *trends* and *alert proactively*.

### Pipeline

1. Daemons stream metrics per run: cost, tokens (in/out), latency, tool-call count,
   error rate, duration.
2. Async workers roll these into **time-bucketed aggregates** per agent/daemon/org
   (per-minute → per-hour → per-day) in ClickHouse.
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

---

## 11. Marketplaces

- **Agent Marketplace** and **Skill Marketplace** — hosted catalogs of publishable,
  installable agent templates and skills.
- Listings carry metadata: description, platform compatibility, required tools/MCP,
  permissions requested, versioning, ratings.
- **One-click install** resolves a listing into an agent definition + skill files and
  pushes them to a chosen daemon via `agent.deploy` / `skill.install`.
- Supports importing from **existing external marketplaces** (e.g. published skill
  packs, MCP registries) via adapters.
- Skills are **platform-scoped**: the same agent can install different skills per OS.

---

## 12. Scaling, Reliability, Security

- **Stateless API + realtime tier** → scale out horizontally; Redis carries routing,
  presence, rate-limit, and pub/sub state.
- **Async workers (Celery/Arq)** for analytics rollups, anomaly scans, notification
  fan-out, and webhook processing — decoupled from request latency.
- **Storage tiering**: Postgres (records/audit), ClickHouse (telemetry), S3 (blobs),
  Redis (ephemeral).
- **Multi-tenancy isolation**: row-level tenant scoping on every query; per-org rate
  limits and quotas.
- **Zero raw secrets**: the cloud stores agent *config* and *policy*, never provider
  API keys; telemetry arrives pre-redacted from the daemon.
- **Transport**: TLS everywhere; daemon and browser sockets independently
  authenticated; RBAC enforced on every command and HITL resolution.

---

## 13. Tech Stack Summary

| Concern | Choice |
|---------|--------|
| API framework | FastAPI (Python) |
| Realtime | WebSockets + Redis pub/sub |
| Records DB | PostgreSQL |
| Telemetry DB | ClickHouse (or TimescaleDB) |
| Blob storage | S3-compatible object store |
| Cache / pub-sub / presence | Redis |
| Async jobs | Celery / Arq |
| Auth | OAuth 2.0 (device-code + auth-code/PKCE), JWT |
| Notifications | Slack/Discord SDKs, SES/Postmark |
| Wire format | MessagePack (daemon) / JSON (browser) |

See **[integration.md](integration.md)** for the end-to-end message flows that tie the
cloud to the daemon and Web UI.
