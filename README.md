# Synapse

**An agent-manager platform with a hard trust boundary: your machine executes agents and holds the secrets; the cloud is only a broker and historian.**

Synapse is a **four-part system**: a Python daemon that runs agents on your machines with on-device security enforcement, a cloud broker that manages auth and audit, a web control surface for monitoring and deployment, and a modern documentation site with landing page.

Execution, raw provider keys, and PII redaction never leave the host the agent runs on — the cloud brokers commands and stores only redacted/encrypted records.

---

## The three invariants

Everything in Synapse is built to preserve three rules. If a change would break one of
these, it's the wrong change.

1. **The browser and the daemon never talk directly** — the cloud brokers every message.
2. **The cloud never executes agents or holds raw provider keys** — those stay on the daemon.
3. **The daemon connects outbound-only** — no inbound ports are ever opened on your machine.

This is the control-plane / data-plane split: the cloud is the *control plane* (auth,
routing, audit, analytics); your machine is the *data plane* (execution, secrets, redaction).

---

## The four products

| Product | Directory | What it is |
|---------|-----------|------------|
| **TUI Worker Daemon** | `synapse_worker/` | Python daemon for your machines. Executes agents, redacts PII/secrets **on-device**, enforces rulesets/blockers/guardrails, handles HITL pauses, checkpoints long runs, and connects to the cloud over an **outbound-only WebSocket uplink**. Ships a Typer CLI and optional Textual TUI. Published as `synapse` CLI. |
| **Cloud Backend** | `synapse_cloud/` | FastAPI broker/historian with ~60 REST endpoints + WebSocket daemon hub. Backed by **Supabase** (Postgres + RLS, Auth, Storage, Realtime) with in-process async workers for telemetry rollups, heartbeat monitoring, anomaly detection, webhooks, and notifications. |
| **Web UI** | `synapse_web/` | React/TypeScript SPA (Vite) control surface. One-click deploy, Markdown prompt editor with versioning/diff/rollback, live trace viewer, token + cost analytics, approvals queue, and marketplace. Serves as a static bundle from the Cloud Backend (same origin). |
| **Documentation Site** | `synapse_docs/` | Next.js 15 documentation and landing page. Modern, searchable docs site (`/docs`) with global CTRL+K search, integrated with the legacy spec docs. Serves the public-facing product story. |

The Web UI and Cloud Backend are deployed on the **same host** (one origin, no CORS);
Supabase and the daemons run separately.

---

## Architecture

```
┌──────────────────────────┐  Supabase Realtime (WSS)  ┌─────────────────────────┐
│   Web UI (synapse_web)   │ ◄──────────────────────► │   Cloud Backend         │
│   React SPA (Vite)       │      REST (same origin)   │   FastAPI + WS hub      │
│                          │ ────────────────────────► │   Supabase · Async jobs │
└──────────────────────────┘                           └────────────▲────────────┘
                                                                    │ outbound-only
                                                       WebSocket uplink (daemon-initiated):
                                                         • control + HITL
                                                         • telemetry firehose
                                                                    │
                                                       ┌────────────┴────────────┐
                                                       │  TUI Worker Daemon      │
                                                       │  (synapse_worker/)      │
                                                       │  • agent runtime        │
                                                       │  • PII/secret redaction │
                                                       │  • ruleset enforcement  │
                                                       │  • checkpoint WAL       │
                                                       │  (your machine)         │
                                                       └─────────────────────────┘

┌──────────────────────────┐
│  Documentation Site      │
│  (synapse_docs/)         │
│  Next.js 15 + Landing    │
│  CTRL+K Search           │
│  (public-facing)         │
└──────────────────────────┘
```

### Key mechanisms

- **Daemon auth**: RFC 8628 device-code grant — `synapse login` shows an 8-char code you approve in the Web UI; no terminal passwords.
- **Secrets**: Agent env-vars are **X25519 sealed-box encrypted** in the browser before transmission. The daemon holds the private key; the cloud relays opaque ciphertext + stores var names only.
- **Checkpoints**: Long runs journal to a local SQLite WAL and sync to the cloud **E2E-encrypted to an org recovery key**, so any authorized daemon can resume after total loss.
- **Guardrails**: On-device input/output filtering (PII/secret redaction + prompt-injection guard) and a Ruleset Engine (command blockers, write-path guards, host allow-lists, cost/tool caps) — all **enforced by the daemon, not the model**.

---

## Repository layout

```
synapse/                             # Monorepo: daemon, cloud, web UI, docs
├── synapse_worker/                  # TUI Worker Daemon (Python · Typer/Textual)
│   ├── cli/                         #   `synapse` subcommands
│   ├── commands/                    #   cloud→daemon command handlers
│   ├── runtime/                     #   agent adapters + cost accounting
│   ├── connection/                  #   WebSocket uplink
│   ├── filtering/                   #   redaction + injection guard
│   ├── ruleset/                     #   guardrail enforcement
│   ├── checkpoint/                  #   durable execution + recovery
│   ├── vault/                       #   E2E env-var encryption
│   ├── orchestrator/                #   agent workflow composition
│   ├── scheduler/                   #   cron + task scheduling
│   ├── memory/                      #   agent memory systems
│   ├── plugins/                     #   extensibility
│   ├── hitl/                        #   human-in-the-loop
│   └── tui/                         #   Textual dashboard
│
├── synapse_cloud/                   # Cloud Backend (Python · FastAPI)
│   ├── app.py                       #   application factory
│   ├── routers/                     #   REST endpoints (agents, runs, auth, hitl, …)
│   ├── ws_hub/                      #   WebSocket daemon hub
│   ├── workers/                     #   async jobs (rollups, anomaly, heartbeat)
│   ├── services/                    #   memory sync, recovery, telemetry, tokens
│   ├── notifications/               #   webhooks + alerts
│   └── command_auth.py              #   command authorization
│
├── synapse_web/                     # Web UI (React + TypeScript · Vite)
│   ├── src/
│   │   ├── screens/                 #   pages (agents, runs, settings, …)
│   │   ├── components/              #   UI primitives + common widgets
│   │   ├── api/                     #   TanStack Query hooks → REST
│   │   ├── store/                   #   Zustand state (UI, toasts, approvals)
│   │   ├── styles/                  #   design system CSS + Tailwind
│   │   └── lib/                     #   Supabase client, utilities
│   └── dist/                        #   built bundle (served by cloud backend)
│
├── synapse_docs/                    # Documentation Site (Next.js 15)
│   ├── app/
│   │   ├── page.tsx                 #   landing page
│   │   ├── docs/                    #   documentation pages
│   │   └── layout.tsx               #   root layout
│   ├── components/                  #   SearchCommand, Nav, Footer, etc.
│   ├── lib/docs.ts                  #   docs metadata + search index
│   ├── public/docs_html/            #   legacy HTML docs (embedded)
│   └── globals.css                  #   site styles + search modal
│
├── docs/                            # Product design specs (source of truth)
│   ├── tui-daemon.md                #   daemon behavior + design
│   ├── cloud-backend.md             #   broker/historian spec
│   ├── web-ui.md                    #   UI spec + screens
│   ├── integration.md               #   how components fit + invariants
│   ├── possible-features.md         #   experimental designs (orchestration, etc.)
│   └── tasks/                       #   implementation task docs
│
├── tools/
│   ├── supabase/migrations/         #   SQL migrations (schema, RLS, telemetry)
│   └── tests/                       #   integration + worker tests
│
├── pyproject.toml                   #   Python project config (cloud + worker)
├── .env.example                     #   env vars for cloud setup
└── README.md                        #   this file
```

---

## Getting started

### Prerequisites

- **Python 3.10+** (worker daemon targets 3.11+).
- **Node.js 18+** (for web UI and docs site).
- A **Supabase** project (schema lives in `tools/supabase/migrations/`).
- [`uv`](https://github.com/astral-sh/uv) recommended for Python.

> Background jobs (heartbeat sweep, telemetry rollups, anomaly detection) run **in-process** via the app lifespan scheduler — no Redis, no separate worker process.

### Option A: Local Full-Stack Setup

#### 1. Install & configure the cloud backend

```bash
# Install cloud deps (+ dev/test)
pip install -e ".[dev]"

# Install worker daemon deps (+ dev)
uv pip install -e ".[worker,dev]"

# Configure
cp .env.example .env
# Edit .env: add SUPABASE_SERVICE_ROLE_KEY, set DAEMON_JWT_SECRET
```

Key environment variables (see `.env.example`):

| Var | Purpose |
|-----|---------|
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase project + keys |
| `DAEMON_JWT_SECRET` | signs daemon device-code access tokens (HS256) |
| `GRANT_SIGNING_KEY` | ed25519 seed for orchestration grants |
| `SYNAPSE_ENV` | `dev` / `test` (test fakes side-effects) |
| `WEB_UI_DIST` | path to built Web UI bundle (e.g., `synapse_web/dist`) |

#### 2. Build the web UI

```bash
cd synapse_web
npm install
npm run build    # outputs to dist/
cd ..
```

#### 3. Run the cloud backend

```bash
# Serves Web UI + REST API + WebSocket daemon hub
uvicorn synapse_cloud.app:create_app --factory --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser.

#### 4. Run a worker daemon

In a new terminal:

```bash
synapse login            # device-code flow — approve in the Web UI
synapse daemon run       # foreground daemon
# or: synapse daemon install  # install as native service
```

Optionally run the TUI dashboard:

```bash
synapse tui              # Textual dashboard (separate terminal)
```

Other CLI commands: `synapse agent …`, `synapse env …`, `synapse plugin …`, `synapse --version`.

### Option B: Run the Documentation Site Locally

```bash
cd synapse_docs
npm install
npm run dev              # http://localhost:3000
npm run build            # for production
```

---

## Testing

```bash
# Cloud tests (against a real Supabase project, RLS-isolated)
python -m pytest tools/tests -k "not worker"

# Worker tests (self-contained, no network)
python -m pytest tools/tests/worker

# Live end-to-end (boots cloud + drives daemon over live WebSockets)
python -m tools.tests.live_cloud_smoke
```

> The full cloud suite can be slow and hit GoTrue rate limits. Prefer per-module runs.
> The schema is already migrated; don't add migrations for existing tables.

---

## Security model

- **Execution & secrets stay local.** The cloud never runs agents or sees raw provider keys. Env-var values are X25519 sealed-box encrypted to the daemon; the cloud holds ciphertext + names only.
- **Redaction on-device** before any byte is uploaded (regex/entropy + optional Presidio). Salted tokens like `<REDACTED:API_KEY:a91f>`.
- **Rules enforced by the daemon, not the model** — even a successful prompt injection can't bypass a blocker. Findings feed an immutable audit log + anomaly detector.
- **Per-device, revocable auth** via RFC 8628 device-code grant. Refresh tokens rotate; the cloud stores only token hashes.
- **Durable, recoverable runs** via SQLite WAL checkpoints, E2E-encrypted to an org recovery key so any authorized daemon can resume.

---

## Documentation

- **Public docs**: [synapse_docs/](synapse_docs/) (Next.js site with landing page + searchable docs)
- **Product specs**: [docs/](docs/) (behavioral source of truth)
  - [tui-daemon.md](docs/tui-daemon.md) — daemon design
  - [cloud-backend.md](docs/cloud-backend.md) — broker/historian spec
  - [web-ui.md](docs/web-ui.md) — UI spec + screens
  - [integration.md](docs/integration.md) — system architecture + invariants
  - [possible-features.md](docs/possible-features.md) — experimental designs (orchestration, agent-as-approver, model-comparison, drift monitoring)

---

## Development

### Code organization

- **synapse_worker**: Python 3.11+. CLI: Typer; TUI: Textual; async I/O: asyncio.
- **synapse_cloud**: Python 3.10+. FastAPI, Supabase Python SDK, WebSockets.
- **synapse_web**: React 18, TypeScript, Vite, TanStack Query, Zustand, Recharts.
- **synapse_docs**: Next.js 15, React 19, TypeScript. Embedded legacy HTML docs.

### Contributing

- Keep changes focused. PRs should solve one problem.
- Test locally: cloud tests need a real Supabase project. Worker tests are self-contained.
- Documentation specs in `docs/` are the source of truth. Update them before implementing.
- Experimental features go in `docs/possible-features.md` with blast-radius controls.

---

## Status

- ✅ **Cloud Backend** — implemented and production-ready
- ✅ **TUI Worker Daemon** — implemented and production-ready
- ✅ **Web UI** — implemented and production-ready
- ✅ **Documentation Site** — implemented (Next.js 15, with CTRL+K search)
- 🔄 **Experimental features** (orchestration, agent-as-approver, model-comparison, drift monitoring) — designed in `docs/possible-features.md`, off-by-default, gated behind org flags
