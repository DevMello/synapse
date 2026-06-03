# Synapse

**An agent-manager platform with a hard trust boundary: your machine executes agents and holds the secrets; the cloud is only a broker and historian.**

Synapse lets you deploy, run, and observe AI agents (both API models and CLI tools like
Claude Code, Codex, and Gemini CLI) on your own machines, while managing them from a web
control surface. Execution, raw provider keys, and PII redaction never leave the host the
agent runs on — the cloud brokers commands and stores only redacted/encrypted records.

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

## The three products

| Product | Package | What it is |
|---------|---------|------------|
| **TUI Worker Daemon** | `synapse_worker/` (`synapse-worker` on PyPI, `synapse` CLI) | Python daemon installed on your machines. Executes agents, redacts PII/secrets **on-device**, enforces rulesets/blockers/guardrails, handles HITL pauses, checkpoints long runs, and connects to the cloud over an **outbound-only WebSocket uplink**. Ships a Typer CLI and a Textual TUI. |
| **Cloud Backend** | `synapse_cloud/` (`synapse-cloud`) | FastAPI broker/historian. ~60 REST endpoints + a WebSocket daemon hub, backed by **Supabase** (Postgres + RLS, Auth, Storage, Realtime) with **Arq/Redis** async workers for telemetry rollups, heartbeat monitoring, anomaly detection, webhooks, and notifications. |
| **Web UI** | _specified in [`docs/web-ui.md`](docs/web-ui.md); served as a static bundle by the Cloud Backend_ | React/TS control surface: one-click deploy, Markdown prompt editor with versioning/diff/rollback, live trace viewer, analytics, approvals queue, marketplaces. |

The Web UI bundle and the Cloud Backend are deployed on the **same host** (one origin, no
CORS); Supabase and the daemons run separately.

---

## Architecture

```
┌─────────────┐        Supabase Realtime (WSS)        ┌──────────────────────────┐
│   Web UI    │ ◄───────────────────────────────────► │      Cloud Backend       │
│  (browser)  │            REST (same origin)          │  FastAPI + WS daemon hub │
└─────────────┘ ─────────────────────────────────────►│  Supabase · Arq/Redis    │
                                                       └────────────▲─────────────┘
                                                                    │ outbound-only
                                                       WebSocket uplink (daemon-initiated):
                                                         • control + HITL  (cloud→daemon
                                                           commands need no inbound port)
                                                         • telemetry firehose
                                                                    │
                                                       ┌────────────┴─────────────┐
                                                       │     TUI Worker Daemon    │
                                                       │  agent runtime · redaction│
                                                       │  ruleset · vault · SQLite │
                                                       │  (your machine)          │
                                                       └──────────────────────────┘
```

- **Daemon auth**: custom **OAuth 2.0 Device Authorization Grant** (RFC 8628) — `synapse
  login` shows a `user_code`, you approve it in the already-authenticated Web UI; no
  password is ever typed in the terminal. Per-device tokens are revocable.
- **Secrets**: agent env-var values are **E2E-encrypted** (X25519/libsodium sealed box via
  PyNaCl) — the daemon holds the private key, the browser encrypts to its public key, and
  the cloud relays opaque ciphertext + stores var *names* only.
- **Checkpoints**: long runs are journaled to a local SQLite WAL and synced to the cloud
  **E2E-encrypted to an org recovery key**, so any authorized daemon can resume after total
  local loss.
- **Guardrails**: on-device input/output filtering (PII/secret redaction + prompt-injection
  guard) and a Ruleset Engine (command blockers, write-path guards, host allow-lists,
  cost/tool caps) — all **enforced by the daemon, not the model**.

---

## Repository layout

```
synapse/
├── docs/                     # Product design specs (source of truth for behavior)
│   ├── tui-daemon.md         #   the worker daemon
│   ├── cloud-backend.md      #   the cloud broker/historian
│   ├── web-ui.md             #   the web control surface
│   ├── integration.md        #   how the three fit together + the invariants
│   └── possible-features.md  #   experimental, off-by-default feature designs
├── synapse_cloud/            # Cloud Backend (FastAPI)
│   ├── app.py                #   application factory (routers auto-discovered)
│   ├── routers/              #   REST endpoints (agents, runs, auth_device, hitl, …)
│   ├── ws_hub/               #   WebSocket daemon hub
│   ├── workers/              #   Arq async tasks (rollups, anomaly, heartbeat, …)
│   └── services/             #   memory sync, recovery, telemetry ingest, tokens, …
├── synapse_worker/           # TUI Worker Daemon (Typer CLI + Textual TUI)
│   ├── cli/                  #   `synapse` subcommands (login, daemon, agent, env, …)
│   ├── commands/             #   cloud→daemon command handlers (auto-discovered)
│   ├── runtime/              #   API + CLI agent adapters, ccusage cost accounting
│   ├── connection/           #   the outbound WebSocket uplink
│   ├── filtering/ ruleset/   #   redaction + injection guard + ruleset enforcement
│   ├── checkpoint/ vault/    #   durable execution + the E2E env-var vault
│   └── tui/                  #   Textual panes (agents, approvals, live, logs)
└── tools/
    ├── supabase/migrations/  # 9 SQL migrations (schema, RLS, partitioned telemetry)
    └── tests/                # cloud tests + self-contained tests/worker/ suite
```

---

## Getting started

### Prerequisites

- **Python 3.10+** (the worker targets 3.11+).
- A **Supabase** project (the schema lives in `tools/supabase/migrations/`).
- **Redis** (for the cloud's Arq async workers).
- [`uv`](https://github.com/astral-sh/uv) recommended for installs.

### 1. Install

```bash
# Cloud Backend (+ dev/test deps)
pip install -e ".[dev]"

# Worker daemon (+ dev deps). Optional extras: [redaction] (Presidio), [vector] (Chroma)
uv pip install -e ".[worker,dev]"
```

### 2. Configure the cloud

```bash
cp .env.example .env
# Fill in SUPABASE_SERVICE_ROLE_KEY, set a real DAEMON_JWT_SECRET, point REDIS_URL at Redis.
```

Key environment variables (see `.env.example`):

| Var | Purpose |
|-----|---------|
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase project + keys |
| `DAEMON_JWT_SECRET` | signs daemon device-code access tokens (HS256) |
| `REDIS_URL` | Arq async worker queue |
| `SYNAPSE_ENV` | `dev` / `test` (`test` fakes outbound side-effects) |
| `WEB_UI_DIST` | path to a built Web UI bundle to serve from the same origin |

### 3. Run the Cloud Backend

```bash
# Web app + WebSocket daemon hub (one process)
uvicorn synapse_cloud.app:create_app --factory --reload

# Async workers (separate process)
arq synapse_cloud.workers.WorkerSettings
```

### 4. Run a worker daemon

```bash
synapse login            # device-code flow — approve in the Web UI, no password in the terminal
synapse daemon run       # run in the foreground (or `synapse daemon install` for a native service)
synapse tui              # optional Textual dashboard
```

Other CLI groups: `synapse agent …`, `synapse env …`, `synapse plugin …`, `synapse init`,
`synapse --version`.

---

## Testing

```bash
# Cloud tests run against a REAL Supabase project (each test mints an RLS-isolated org).
python -m pytest tools/tests -k "not worker"

# Worker tests are fully self-contained — no Supabase, no network (a MockCloud WS hub fixture).
python -m pytest tools/tests/worker

# Live end-to-end: boots the real cloud + drives the real daemon over live WebSockets.
python -m tools.tests.live_cloud_smoke
```

> The full cloud suite is slow and can hit GoTrue rate limits under heavy back-to-back runs
> — prefer per-module runs. The schema is already migrated; don't add migrations for
> existing tables.

---

## Security model (at a glance)

- **Execution & secrets stay local.** The cloud never runs an agent or sees a raw provider
  key. Env-var values are X25519 sealed-box encrypted to the daemon; the cloud holds
  ciphertext + names only.
- **Redaction happens on-device** before any byte is uploaded (regex/entropy + optional
  Presidio; salted tokens like `<REDACTED:API_KEY:a91f>`).
- **Rules are enforced by the daemon, not the model** — a successful prompt injection still
  can't get past a blocker. Findings feed an immutable audit log + a cloud anomaly detector.
- **Per-device, revocable auth** via the device-code grant; refresh tokens rotate; the cloud
  stores only token *hashes*.
- **Durable, recoverable runs** via SQLite WAL checkpoints, E2E-encrypted to an org recovery
  key so any authorized daemon can resume.

---

## Documentation

The `docs/` specs are the behavioral source of truth:

- **[docs/tui-daemon.md](docs/tui-daemon.md)** — the worker daemon (runtime, redaction,
  ruleset, checkpointing, agent memory, capabilities).
- **[docs/cloud-backend.md](docs/cloud-backend.md)** — the broker/historian (data model,
  API surface, sync, recovery).
- **[docs/web-ui.md](docs/web-ui.md)** — the web control surface.
- **[docs/integration.md](docs/integration.md)** — how the three products fit together and
  the invariants they preserve.
- **[docs/possible-features.md](docs/possible-features.md)** — experimental, off-by-default
  feature designs (agent orchestration, agent-as-approver, model-comparison runs, native
  handoff protocol, behavioral-drift & intent monitoring), each with its own blast-radius
  controls and promotion checklist.

---

## Status

The **Cloud Backend** and **TUI Worker Daemon** are implemented on `master`. The **Web UI**
and the features in `docs/possible-features.md` are at the design stage. Experimental
features are off by default, gated behind org-level flags and explicit consent, and excluded
from `production`-tagged agents.
