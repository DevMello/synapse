# Synapse — Web UI

> The single pane of glass. A browser app where users register daemons, build and
> deploy agents in one click, edit prompts/skills/rulesets in a Markdown editor,
> schedule runs, watch live reasoning traces, approve HITL gates, and read deep
> analytics — all in real time over a WebSocket to the Cloud Backend.

---

## 1. Purpose & Role

The Web UI is the **control surface** of Synapse. It never touches a daemon directly;
every action it takes is a message to the Cloud Backend, which brokers it to the right
worker. Likewise, everything the user sees — live agent output, costs, logs, alerts —
is telemetry streamed *from* daemons *through* the cloud *into* the browser in real
time.

It must make a fundamentally distributed, multi-machine system feel like a single,
coherent app: "click a button, pick a daemon, an agent is live."

> **Deployment:** the Web UI ships as a static bundle **served from the same host as the
> Cloud Backend** (one deployment unit, behind one reverse proxy or FastAPI's static
> mount). The browser therefore loads the app and calls the REST API on **one origin —
> no CORS**. It still talks to **Supabase** (Auth/Realtime/data API) directly as an
> external service, and never to a daemon.

---

## 2. Tech Stack

| Concern | Choice |
|---------|--------|
| Framework | React + TypeScript (Next.js or Vite SPA) |
| Realtime | **Supabase Realtime** (`supabase-js`: Broadcast + Presence) |
| Server state | TanStack Query (REST + Supabase data API) |
| Client state | Zustand / Redux Toolkit |
| Styling | Tailwind CSS + a component library (Radix/shadcn) |
| Charts | Recharts / visx for analytics |
| Markdown editor | CodeMirror 6 / Monaco with live preview |
| Diff view | Monaco diff editor (prompt versioning) |
| Auth | **Supabase Auth** (`supabase-js`) — JWT carries `org_id`/role for RLS |
| Hosting | Built bundle served by the **Cloud Backend host** (same origin as REST; one reverse proxy / FastAPI static mount) |

- **Hybrid data model**: slow-changing config via REST + the Supabase data API
  (cached by TanStack Query, gated by RLS); fast-changing telemetry via **Supabase
  Realtime** channels, merged into the cache so the UI is always live without manual
  refresh. No bespoke WebSocket client to maintain.

---

## 3. Information Architecture

```
Synapse
├── Dashboard          (fleet overview: daemons, agents, alerts, spend)
├── Daemons            (registered workers + uptime monitoring + revoke)
├── Connect a device   (device-code verification page: enter ABCD-1234, approve)
├── Agents             (the core: list, detail, builder)
│   └── Agent Detail
│       ├── Overview   (status, availability, next run, recent runs)
│       ├── Editor     (Markdown: prompt, skills, rulesets)
│       ├── Versions   (history, diff, one-click rollback)
│       ├── Schedule   (cron/interval/one-shot)
│       ├── Tools/MCP  (gateways, MCP servers, blockers)
│       ├── Plugins    (install capability packs onto this agent's daemon)
│       ├── Environment(env vars — E2E encrypted to the daemon, write-only)
│       ├── Memory     (view/search/edit/pre-load persistent agent memory)
│       ├── Runs       (history + live trace viewer)
│       ├── Logs       (access logs, tool logs — redaction-aware)
│       └── Analytics  (tokens, spend, latency, tasks, tool calls)
├── Runs               (global run history across all agents)
├── Approvals          (HITL queue)
├── Alerts             (anomalies, failures, offline daemons)
├── Marketplace        (agents + skills + plugins, one-click install)
├── Notifications      (Slack/Discord/Email channels + routing)
├── Webhooks           (inbound triggers)
└── Settings           (org, members/RBAC, billing, API tokens)
```

---

## 4. Core Screens & Features

### 4.1 Dashboard

Fleet-wide health at a glance:

- **Daemons online/offline**, with uptime sparklines.
- **Active runs** right now (live count + streaming list).
- **Spend** today/this month with trend vs. previous period.
- **Open alerts** (anomalies, failures) and **pending approvals**.
- **Top agents** by spend / volume / error rate.

### 4.2 Daemons & Uptime Monitoring

- List of registered workers: name, tags, platform, version, **status (online/offline)**,
  last-seen, resource usage (CPU/mem), active-run count.
- **Device identity** per daemon: hostname, OS version, and last-seen IP, rendered as
  "logged in on **my-macbook-pro** (macOS 15.3) — last seen 2 minutes ago", so a user can
  recognize each session at a glance.
- **Uptime monitoring** per daemon: availability %, downtime incidents timeline,
  heartbeat history. Configurable offline-alert thresholds.
- **Revoke** (per daemon): one click invalidates that device's tokens and drops its live
  connection — for a lost laptop or decommissioned VPS — **without changing the user's
  password** and without touching any other daemon. Shows a confirm dialog with the
  device's identity so the right session is killed.
- **Capabilities** (per daemon) — the *daemon tier* of the two-tier capability model:
  enable/install **MCP servers, plugins, and system tools on this host** (where their
  venv/process lives) and configure each (endpoint, args, version). Each shows
  `installing → ready | failed`. Enabling here makes a capability **available** on the
  daemon but does **not** grant any agent access — that's selected per agent (§4.7).
  Removing a capability here detaches it from **all** the daemon's agents at once.

#### Pairing a new daemon (device-code login)

Running `synapse login` on a machine starts the **OAuth 2.0 Device Authorization Grant**.
The Web UI side is a short **verification page** at the `verification_uri`:

1. The user (already signed in via **Supabase Auth**) lands on **Connect a device** and
   enters the **`user_code`** (`ABCD-1234`) the CLI printed — or follows the
   `verification_uri_complete` link/QR that pre-fills it.
2. The page shows the **requesting device's metadata** (hostname, OS, source IP) for the
   user to verify before approving — defense against a code phished onto the wrong device.
3. **Confirm** authorizes the device; it binds to the user's org and appears in the
   Daemons list as online. **Deny** rejects it. Codes expire (~10 min) and are single-use.

### 4.3 Agents

**One-click creation** is the headline interaction:

1. Click **New Agent**.
2. Pick a **daemon** to host it (or "any daemon with tag X").
3. Choose **type** (API agent or CLI tool like `claude code`) and a starting template
   (blank, or from the **Marketplace**).
4. Agent is deployed to the daemon and live.

The **agent list** shows status, host daemon, type, platform, last run, next scheduled
run, today's spend, and **availability** (is its daemon online and is the agent
enabled). Bulk actions: enable/disable, run now, move to another daemon.

### 4.4 Markdown Editor (prompts, skills, rulesets)

Everything that defines an agent's behavior is editable **online**:

- **CodeMirror/Monaco** editor with Markdown highlighting and **live preview**.
- Edit the system prompt, per-task prompts, skill definitions, and rulesets/blockers.
- **Template variables** (`{{var}}`) are recognized and validated.
- Saving creates a **new version** (never an in-place mutation).
- **Skills are platform-scoped** — the editor lets you maintain different skill sets
  per OS (Windows/macOS/Linux) for the same agent.

### 4.5 Versions & Rollback

- Full **version history** with author, timestamp, and message.
- **Side-by-side diff** (Monaco diff) between any two versions.
- **One-click rollback** to a previous version → backend re-pushes to the daemon.
- Versions can be **tagged** `known-good` / `production`.
- When a new version's error rate spikes, the UI **surfaces a "revert" suggestion**
  pointing at the last known-good version.

### 4.6 Scheduling

- Visual schedule builder: cron expression (with human-readable preview), fixed
  interval, or one-shot.
- Missed-run policy selector (skip / run-once / coalesce).
- Timezone-aware; shows the next N fire times.

### 4.7 Tools, MCP, Plugins & Blockers

**Tools / MCP / blockers** — *agent-tier capability selection*

This tab is the **agent tier** of the two-tier model (the *daemon tier* — what's actually
installed on the host — lives on the Daemons page, §4.2):

- **Capability toggles**: a checklist of every capability **available on this agent's
  daemon** — MCP servers, plugins, and system tools — each with an **include/exclude**
  toggle for *this agent*. Toggling is instant (`capability.attach`/`detach`) — it does
  **not** install or tear anything down; it only selects from what the daemon already has.
- **Defaults**: built-in capabilities (filesystem, fetch, git, memory MCP) show as
  **on by default**; the operator can still detach one for this agent. Everything else is
  **off until explicitly toggled on**.
- **Greyed-out / "install on daemon first"**: a capability not yet enabled on the host
  appears disabled with a shortcut to enable it on the Daemons page — keeping the two
  tiers visibly distinct.
- **Gateways** the agent may use are configured here too.
- Define **rulesets/blockers**: denied commands, path guards, network allow-lists,
  cost/tool-call caps, and which actions require **HITL approval**. Each rule's severity
  (block / require-approval / warn) is set here. The capability toggles above are the
  enforcement surface for "MCP gating" (tui-daemon §4.6).

**Input/Output Filtering (guardrails)** — the *Filtering* panel

Configure the daemon-side middleware that screens content entering and leaving the model
(see [tui-daemon.md](tui-daemon.md) §4.5). Two layers, both edited here:

- **PII / secret redaction** — toggle built-in detectors (API keys, emails, tokens,
  card/SSN patterns), add **custom redaction rules** (regex/keyword), and pick the mode
  per rule: **block / mask / hash**. A read-only note explains tokens are salted on-device.
- **Prompt-injection & jailbreak guard** — enable inbound screening (untrusted tool/web
  content checked for instruction-override, data-exfiltration, and tool-bypass attempts)
  and outbound screening (model output checked for self-instruction override, policy
  divergence, secret-leak). Each finding category maps to a **ruleset action**
  (block / require-approval / warn). Optionally enable the **local classifier** (Ollama)
  for daemons that have it; the UI flags daemons where it's unavailable.
- Set **per-agent overrides** on top of an **org-wide default policy**; the panel shows
  which settings are inherited vs. overridden.

Findings never include raw sensitive content — only category, severity, action, and a
redacted excerpt — and surface live in **Logs** (§4.10) and **Alerts** (§4.13).

**Plugins (capability packs)** — the *Plugins* tab

Plugins give an agent new **actions** (vs. skills, which give it knowledge). Installing
follows the **two tiers**: provision on a daemon, then attach to an agent.

- **Defaults shown**: every agent lists its built-in capabilities (default MCP servers:
  filesystem, fetch, git, memory) as **auto-attached** (detachable per agent).
- **Provision (daemon tier)**: from the **Marketplace** or the Daemons page (§4.2), pick
  a pack and **one-click enable** it on a chosen daemon — this creates the venv/workspace
  and registers its MCP servers/tools on the host. Packs include **browser use**
  (Playwright automation), **terminal use** (sandboxed shell), **file explorer** (scoped
  FS read/write tools), **MCP quick-installs** (GitHub, Slack, Postgres…), and **custom
  coding environments** (per-project virtualenvs/workspaces for `claude`/`aider` agents).
- **Attach (agent tier)**: once a pack is `ready` on the daemon, **toggle it on for this
  agent** here (or in *Tools/MCP*). Attaching is instant and reuses the provisioned pack —
  no re-install. The same daemon's other agents stay unaffected until individually toggled.
- **Live install status**: a pack shows `installing → ready | failed` as the daemon
  provisions it. Failures surface the install log.
- **Per-platform**: the UI only offers packs compatible with the target daemon's OS;
  the same agent can carry different packs on different daemons.
- **Manage**: view each pack's exposed tools and declared **permissions** (network/
  filesystem/HITL), pin versions, update, detach from this agent, or remove from the
  daemon (which tears down its sandbox and detaches it from all agents).
- **Custom packs**: install an unpublished/local plugin by reference for private tools.

See [tui-daemon.md](tui-daemon.md) §4.11 for how packs are provisioned and sandboxed,
and [cloud-backend.md](cloud-backend.md) for the catalog/relay.

### 4.8 Environment Variables

Set the env vars an agent's runs execute with (e.g. `OPENAI_API_KEY`, `DATABASE_URL`,
`STRIPE_SECRET`). Designed so **secret values never touch cloud storage and the cloud
cannot even read them in transit**.

- **Editor UI**: a `KEY` / `VALUE` table per agent. Each row marks the var as
  **secret** (masked, write-only) or **plain** (e.g. `LOG_LEVEL`, readable for
  convenience). Bulk paste/import from a `.env` file.
- **End-to-end encrypted**: on save, the browser fetches the **target daemon's public
  key** and encrypts each value client-side (libsodium sealed box). Only the resulting
  **ciphertext** is sent — the cloud relays it as an opaque blob to the daemon, which
  decrypts it and stores it in the **OS keyring**. TLS protects the wire; the E2E layer
  ensures the cloud (the broker) never sees plaintext. See
  [tui-daemon.md](tui-daemon.md) and [cloud-backend.md](cloud-backend.md).
- **Write-only**: once saved, a secret value **cannot be read back** in the UI — there
  is nowhere to read it from (not stored on the cloud, encrypted at rest on the daemon).
  You can **overwrite** or **delete** it, not view it. The UI only ever shows the list
  of **variable names** + metadata (last updated, who, which daemon), which is all the
  cloud retains.
- **Locally-set vars are visible too**: vars set directly on the daemon
  (`synapse env set ...`) appear here as **read-only, "set locally"** entries (name
  only), so the operator sees the full effective environment without the UI being able
  to expose or manage their values. Precedence and origin are labeled.
- **Scope**: per-agent by default; an org/daemon-level **shared set** can be defined and
  inherited (with per-agent override).
- **Auto-redaction tie-in**: every value pushed this way is registered with the
  daemon's redaction middleware, so even if an agent echoes a secret it is masked in
  logs.

### 4.9 Runs & Live Trace Viewer

- **Run history** per agent and globally: trigger source (schedule/webhook/manual),
  status, duration, cost, tokens, exit code.
- **Live trace viewer** — open a running agent and watch its reasoning stream in real
  time: each prompt, completion, tool call, tool result, token tally, and running
  cost, updating over the WebSocket.
- Replay completed runs with the same trace UI.
- **Recovery status**: runs surface `interrupted` / `recovering` / `resumed` states
  with a checkpoint progress marker (e.g. "step 14/30, resumed on macbook-02"). A
  manual **Resume / Restart / Abort** override is available (gated by the agent's resume
  policy) for the rare case auto-recovery needs a human decision. See
  [tui-daemon.md](tui-daemon.md) §4.12.

### 4.10 Logs (redaction-aware)

- **Full access logs and tool logs** for every agent, searchable and filterable.
- Redacted values are rendered as visible markers (`<REDACTED:API_KEY>`) — the UI
  *never receives raw secrets*, because the daemon masked them before upload.
- A per-run **redaction summary** ("12 secrets masked") gives confidence without
  exposure.
- **Guardrail findings inline**: prompt-injection / jailbreak detections appear in the
  trace where they fired — tagged with category (override / exfiltration / tool-bypass /
  policy-divergence / secret-leak), severity, and the action the daemon took (blocked /
  sent to approval / warned) — alongside a redacted excerpt. Filter the log to
  *guardrail events only* to review everything caught for a run.

### 4.11 Analytics

Deep, per-agent and fleet-wide:

- **Tokens** (in/out over time), **spend** (per agent/day/model), **API usage**,
  **tasks/runs** completed, **run history**, **tool-call counts and latency**.
- Cost breakdowns by agent, model, and daemon.
- **Trends** with comparison to historical baselines.
- Charts powered by the cloud's analytics rollups; drill from a chart into the
  underlying runs.

### 4.12 Approvals (HITL)

- A live **approval queue** of paused runs awaiting human decision.
- Each card shows the **proposed sensitive action**, full context/diff, and the
  reasoning trace so far.
- **Approve / Deny** with an optional reason; the decision is RBAC-checked, written to
  the audit log, and routed back to the daemon to resume (or abort) the run.
- Mirrors what arrives in Slack/Discord/Email so any channel can resolve a gate.

### 4.13 Alerts / Observability

- A feed of **anomaly alerts** from the cloud's detection engine: cost-per-task spikes,
  3× latency regressions, error surges, token blow-ups, silent agents, offline daemons,
  **interrupted runs awaiting recovery**, and **prompt-injection spikes** (an agent
  suddenly tripping override/exfiltration patterns — often a poisoned data source or
  compromised upstream; repeated blocks can auto-pause the agent pending review).
- Each alert shows the metric, the baseline, the observed value, and a link to the
  offending runs.

### 4.14 Marketplaces

- Browse the **Agent Marketplace**, **Skill Marketplace**, and **Plugin Marketplace**
  (capability packs / MCP quick-installs), plus imported external catalogs and MCP
  registries.
- Listings show description, platform compatibility, required tools/MCP, requested
  permissions, version, and ratings.
- **One-click install**: pick a target daemon (and agent), and the agent/skill/plugin
  is provisioned onto it.

### 4.15 Notifications & Webhooks

- **Notifications**: connect Slack/Discord/Email channels; define routing rules
  (which events from which agents go where).
- **Webhooks**: create signed inbound trigger URLs that start agents on external
  events; view delivery history.

### 4.16 Settings & RBAC

- Org profile, **members & roles** (owner/admin/operator/viewer), billing/usage,
  and API tokens. Roles gate who can deploy, edit, approve HITL, and view secrets-
  adjacent data.

### 4.17 Memory Editor (the agent's *Memory* tab)

Every agent has **persistent memory** it reads/writes across runs (tui-daemon §4.13).
Unlike env vars, this memory is **visible and editable** here — the Web UI is the
debugging, correction, and knowledge-transfer surface for it.

- **Browse & search**: a table of memory entries per agent — `key`, value/text preview,
  `tags`, `namespace`, size, last-updated. Full-text (and, on a vector provider,
  **semantic**) search across entries.
- **Why it's visible** (and env vars aren't): memory is **redacted on-device** (§4.5
  Layer A strips secrets/PII *before* sync) and stored cloud-side as **RLS-scoped
  redacted plaintext** — explicitly **not** E2E-encrypted. That trade-off is what lets
  the operator actually read and fix it. Truly secret values belong in **Environment**
  (§4.8), never in memory.
- **HITL correction**: when an agent misbehaves, open Memory to check whether it
  **hallucinated or read a wrong fact**. Edit or delete a bad entry inline; the change is
  written cloud-side and pushed to the daemon (`memory.sync`) so the **local store** (the
  source of truth) is corrected before the next run.
- **Pre-load / knowledge transfer**: bulk-add entries (instructions, a dataset, seed
  facts) **before first run** — the editor becomes a seeding tool; the cloud syncs the
  rows down to the daemon's local provider.
- **Analytics**: per-agent memory footprint — entry count and total size ("Agent A: 400
  entries, 50 MB"), provider in use (SQLite vs. vector), and growth over time, so an
  operator can spot runaway memory.
- **Provider selection**: choose the agent's **Storage Provider** — default `sqlite-
  memory`, or `vector-memory` (Chroma/Qdrant in a Docker container on the daemon) for
  semantic recall; surfaced as a plugin install on the agent's daemon.
- **Sync model**: reads come from the **cloud snapshot** (synced on demand from the
  daemon — not a live per-access stream), so the tab is fast; edits round-trip back to
  the daemon. Audit log records every operator edit/delete/pre-load.

---

## 5. Real-Time Behavior

- On login (Supabase Auth), the browser **subscribes to Supabase Realtime channels**
  for the resources in view (an agent detail page subscribes to that agent's run/
  telemetry channel; the dashboard subscribes to fleet-level events). RLS decides what
  it's allowed to receive.
- Incoming events patch the TanStack Query cache → UI updates with no refresh.
- `supabase-js` handles reconnect; the app **resubscribes on reconnect** so live views
  recover seamlessly.
- Optimistic UI for commands (e.g. "Run now" shows pending immediately), reconciled
  when the daemon's acknowledgement/telemetry arrives.

---

## 6. UX Principles

- **One screen, whole fleet** — abstract away that agents live on many machines.
- **Live by default** — the user should rarely need to refresh.
- **Safety visible** — redaction markers, blockers, and approval gates are surfaced,
  not hidden, so users trust what's running.
- **Code-grade prompt management** — versioning, diffs, and rollback make prompts feel
  as safe to change as code.

See **[integration.md](integration.md)** for how the Web UI's actions travel through
the cloud to the daemon and how telemetry flows back.
