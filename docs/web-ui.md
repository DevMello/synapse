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

---

## 2. Tech Stack

| Concern | Choice |
|---------|--------|
| Framework | React + TypeScript (Next.js or Vite SPA) |
| Realtime | Native WebSocket client w/ auto-reconnect + resubscribe |
| Server state | TanStack Query (REST/GraphQL) |
| Client state | Zustand / Redux Toolkit |
| Styling | Tailwind CSS + a component library (Radix/shadcn) |
| Charts | Recharts / visx for analytics |
| Markdown editor | CodeMirror 6 / Monaco with live preview |
| Diff view | Monaco diff editor (prompt versioning) |
| Auth | OAuth 2.0 auth-code + PKCE; JWT in memory + refresh |

- **Hybrid data model**: slow-changing config via REST/GraphQL (cached by TanStack
  Query); fast-changing telemetry via the WebSocket, merged into the cache so the UI
  is always live without manual refresh.

---

## 3. Information Architecture

```
Synapse
├── Dashboard          (fleet overview: daemons, agents, alerts, spend)
├── Daemons            (registered workers + uptime monitoring)
├── Agents             (the core: list, detail, builder)
│   └── Agent Detail
│       ├── Overview   (status, availability, next run, recent runs)
│       ├── Editor     (Markdown: prompt, skills, rulesets)
│       ├── Versions   (history, diff, one-click rollback)
│       ├── Schedule   (cron/interval/one-shot)
│       ├── Tools/MCP  (gateways, MCP servers, blockers)
│       ├── Runs       (history + live trace viewer)
│       ├── Logs       (access logs, tool logs — redaction-aware)
│       └── Analytics  (tokens, spend, latency, tasks, tool calls)
├── Runs               (global run history across all agents)
├── Approvals          (HITL queue)
├── Alerts             (anomalies, failures, offline daemons)
├── Marketplace        (agents + skills, one-click install)
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
- **Uptime monitoring** per daemon: availability %, downtime incidents timeline,
  heartbeat history. Configurable offline-alert thresholds.
- Pairing flow: shows the device-code/instructions to connect a new daemon.

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

### 4.7 Tools, MCP & Blockers

- Configure **MCP servers** and **gateways** the agent may use.
- Define **rulesets/blockers**: denied commands, path guards, network allow-lists,
  cost/tool-call caps, and which actions require **HITL approval**.
- Each rule's severity (block / require-approval / warn) is set here.

### 4.8 Runs & Live Trace Viewer

- **Run history** per agent and globally: trigger source (schedule/webhook/manual),
  status, duration, cost, tokens, exit code.
- **Live trace viewer** — open a running agent and watch its reasoning stream in real
  time: each prompt, completion, tool call, tool result, token tally, and running
  cost, updating over the WebSocket.
- Replay completed runs with the same trace UI.

### 4.9 Logs (redaction-aware)

- **Full access logs and tool logs** for every agent, searchable and filterable.
- Redacted values are rendered as visible markers (`<REDACTED:API_KEY>`) — the UI
  *never receives raw secrets*, because the daemon masked them before upload.
- A per-run **redaction summary** ("12 secrets masked") gives confidence without
  exposure.

### 4.10 Analytics

Deep, per-agent and fleet-wide:

- **Tokens** (in/out over time), **spend** (per agent/day/model), **API usage**,
  **tasks/runs** completed, **run history**, **tool-call counts and latency**.
- Cost breakdowns by agent, model, and daemon.
- **Trends** with comparison to historical baselines.
- Charts powered by the cloud's analytics rollups; drill from a chart into the
  underlying runs.

### 4.11 Approvals (HITL)

- A live **approval queue** of paused runs awaiting human decision.
- Each card shows the **proposed sensitive action**, full context/diff, and the
  reasoning trace so far.
- **Approve / Deny** with an optional reason; the decision is RBAC-checked, written to
  the audit log, and routed back to the daemon to resume (or abort) the run.
- Mirrors what arrives in Slack/Discord/Email so any channel can resolve a gate.

### 4.12 Alerts / Observability

- A feed of **anomaly alerts** from the cloud's detection engine: cost-per-task spikes,
  3× latency regressions, error surges, token blow-ups, silent agents, offline daemons.
- Each alert shows the metric, the baseline, the observed value, and a link to the
  offending runs.

### 4.13 Marketplaces

- Browse the **Agent Marketplace** and **Skill Marketplace** (plus imported external
  catalogs).
- Listings show description, platform compatibility, required tools/MCP, requested
  permissions, version, and ratings.
- **One-click install**: pick a target daemon, and the agent/skill is provisioned.

### 4.14 Notifications & Webhooks

- **Notifications**: connect Slack/Discord/Email channels; define routing rules
  (which events from which agents go where).
- **Webhooks**: create signed inbound trigger URLs that start agents on external
  events; view delivery history.

### 4.15 Settings & RBAC

- Org profile, **members & roles** (owner/admin/operator/viewer), billing/usage,
  and API tokens. Roles gate who can deploy, edit, approve HITL, and view secrets-
  adjacent data.

---

## 5. Real-Time Behavior

- On login, the browser opens a WebSocket to the cloud and **subscribes** to the
  resources currently in view (an agent detail page subscribes to that agent's run/
  telemetry channel; the dashboard subscribes to fleet-level events).
- Incoming frames patch the TanStack Query cache → UI updates with no refresh.
- Auto-reconnect with **resubscribe-on-reconnect** so live views recover seamlessly.
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
