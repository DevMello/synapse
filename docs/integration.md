# Synapse — System Integration

> How the three products — the **Web UI**, the **Cloud Backend**, and the **TUI Worker
> Daemon** — connect to form one coherent agent-management platform.

Read the per-product details first:
- **[web-ui.md](web-ui.md)** — the browser control surface
- **[cloud-backend.md](cloud-backend.md)** — the broker, historian, and analytics brain
- **[tui-daemon.md](tui-daemon.md)** — the on-machine executor

---

## 1. The Shape of the System

Synapse is a **control-plane / data-plane** split with a broker in the middle:

```
   ┌──────────────┐        WSS + HTTPS        ┌──────────────────┐   gRPC (HTTP/2)    ┌──────────────────┐
   │   Web UI     │ ◄───────────────────────► │  Cloud Backend   │ ◄────────────────► │  TUI Daemon(s)   │
   │  (browser)   │     commands / telemetry  │   (broker +      │   commands /       │  (user machines) │
   │ CONTROL PLANE│                           │    historian)    │   telemetry        │   DATA PLANE     │
   └──────┬───────┘                           └────────┬─────────┘                    └──────────────────┘
        sees                                    routes + stores                          executes + protects
          └──── served from the same host ───────────┘
```

**Deployment topology:** the **Web UI and Cloud Backend run on the same machine** — one
deployment unit. A single reverse proxy on that host (or FastAPI's own static mount)
serves the built Web UI bundle, the REST API, and the gRPC daemon hub. So the browser
loads the app and makes its REST calls against **one origin** (no CORS), while the gRPC
hub listens on the same host for daemon links. **Supabase** (Postgres/Auth/Storage/
Realtime) remains an external managed service both the browser and the backend talk to,
and the **daemons** are always separate (on users' own machines). Co-locating the
frontend doesn't change the broker model: the cloud is still the only endpoint the
browser and daemon each know about, and the three invariants below are unaffected.

Three invariants define every interaction:

1. **The browser and the daemon never talk directly.** The cloud brokers everything.
2. **The cloud never executes agents or holds raw secrets.** Execution and credentials
   stay on the daemon; the cloud stores config, policy, and (pre-redacted) telemetry.
3. **The daemon connects outbound-only.** No inbound ports on user machines; the
   gRPC stream is always initiated from the daemon to the cloud — even cloud→daemon
   commands ride the daemon-initiated bidirectional stream.

---

## 2. Connection Establishment

### Daemon ↔ Cloud (custom gRPC hub, HTTP/2)
1. User installs `synapse-worker`, runs `synapse login` → **OAuth 2.0 Device
   Authorization Grant** (daemons aren't Supabase Auth users — they get their own daemon
   token). The CLI gets a `user_code` (`ABCD-1234`) + URL from `/auth/device/code`
   (sending hostname/OS/version), the user approves it in the **already-authenticated Web
   UI**, and the CLI's polling of `/auth/device/token` then returns the tokens. No
   password is ever typed in the terminal. (Full handshake in cloud-backend.md §5.)
2. Daemon receives a rotating refresh token + short-lived access token (stored in the OS
   keychain; `0600` encrypted-file fallback on headless boxes).
3. Daemon opens an outbound **gRPC connection (HTTP/2)** to the **custom hub**, presenting
   the access token as call metadata (optionally mTLS), and opens its `Connect` bidi
   stream + `IngestTelemetry` stream, registering (name, tags, platform, version).
4. Cloud marks the daemon **online**, writes a presence row (Postgres, TTL refreshed by
   heartbeat), and routes its `org:{id}:daemon:{id}` channel.
5. Daemon heartbeats every 15s (HTTP/2 keepalive guards the transport) → cloud derives
   uptime + offline alerts.

### Browser ↔ Cloud (Supabase)
0. Browser loads the Web UI bundle from the **Cloud Backend host** (same machine that
   serves the REST API) — one origin, so REST calls need no CORS.
1. User logs in via **Supabase Auth** (GoTrue: OAuth providers / email). The JWT
   carries `org_id`/role claims used by RLS.
2. Browser subscribes to live resources via **Supabase Realtime** (Broadcast +
   Presence), gated by RLS; slow-changing config is read via REST / the Supabase data
   API. Live updates require no bespoke browser socket code.

The browser and daemon still never talk directly — the cloud (gRPC hub + Supabase)
is the only endpoint either side knows about.

---

## 3. The Two Message Directions

### Downstream: commands (Browser → Cloud → Daemon)

A user action in the Web UI becomes a command frame the cloud authenticates,
RBAC-checks, persists, and publishes to the target daemon's channel:

| Web UI action | Cloud step | Daemon command |
|---------------|-----------|----------------|
| New agent + pick daemon | create `agents` row | `agent.deploy` |
| Edit prompt & save | new `agent_versions` row | `agent.update_prompt` |
| Set schedule | create `schedules` row | `schedule.set` |
| Run now | create `runs` row (pending) | `agent.run` |
| Cancel run | update `runs` | `agent.cancel` |
| Install from marketplace | resolve listing | `agent.deploy` / `skill.install` |
| Install plugin (capability pack) | track `plugin_installs` | `plugin.install` |
| Remove plugin | update `plugin_installs` | `plugin.remove` |
| Configure MCP / blockers | persist policy | `mcp.configure` |
| Set env var (E2E encrypted) | store name only, relay ciphertext | `env.set` |
| Delete env var | drop metadata row | `env.delete` |
| Approve/deny HITL | write audit + decision | `hitl.resolve` |
| Resume interrupted run | mark `recovering`, hand off checkpoint | `run.recover` |
| Rollback to version | set `current_version` | `agent.update_prompt` |
| Revoke a daemon | set `revoked_at`, kill refresh token | (hub closes the stream `UNAUTHENTICATED`) |

### Upstream: telemetry (Daemon → Cloud → Browser)

While an agent runs, the daemon streams a reasoning trace to the gRPC hub
(`IngestTelemetry`). The cloud
persists it (Supabase Postgres for records + partitioned telemetry, Supabase Storage for
blobs) **and** publishes it to a Supabase Realtime channel for any subscribed browser:

| Daemon emits | Cloud does | Browser sees |
|--------------|-----------|--------------|
| prompt / completion chunks | persist trace + republish | live trace viewer |
| tool call + result (redacted) | store `tool_calls` | tool logs, trace |
| token usage + cost | aggregate metrics | analytics, running cost |
| run finished (status, totals) | finalize `runs` | run history, notification |
| checkpoint delta (encrypted) | store blob + metadata (`run_checkpoints`) | run progress |
| `run.reconcile` (on reconnect) | diff state, ingest offline work | resumed/“recovered” status |
| `hitl.request` | create gate, fan out | approvals queue + Slack/Discord/Email |
| heartbeat / health | update presence | daemon uptime |
| anomaly-relevant metrics | feed anomaly engine | alerts feed |

---

## 4. End-to-End Walkthroughs

### 4.0 Pair a new daemon (device-code login)

```
TUI: `synapse login`
   │  POST /auth/device/code { hostname:"vps-01", os:"ubuntu 24.04", version }
   ▼
Cloud: device_authorizations(pending, TTL 10m) → { user_code "ABCD-1234",
       verification_uri, interval:5 }
   │  TUI prints code + URL (+ QR), starts polling /auth/device/token every 5s
   ▼
Browser (already logged in via Supabase Auth): open URL → enter ABCD-1234
   │  sees requesting device "vps-01, ubuntu 24.04, from 203.0.113.7" → Confirm
   ▼
Cloud: mark authorized + bind org/user → create daemons row → next poll returns
       { access_token (~15m), refresh_token (rotating) }
   ▼
TUI: store tokens in OS keyring (0600 file fallback) → open gRPC stream (4.1)
   ▼
Browser: Daemons list shows "vps-01 — online, last seen now" + a Revoke button

   ── later: lost VPS ──
Browser: Daemons → vps-01 → Revoke
   ▼  Cloud: set revoked_at, invalidate refresh token, close its gRPC stream
      (UNAUTHENTICATED). No password change; other daemons unaffected.
```

### 4.1 Create and run an agent (one click → live)

```
Browser: New Agent → pick daemon "macbook-01", type=CLI (claude code)
   │  REST: agent.create (Supabase JWT)
   ▼
Cloud:  RBAC/RLS check → write agents + agent_versions(v1) [Postgres]
   │  gRPC hub pushes agent.deploy on Connect stream → org:acme:daemon:macbook-01
   ▼
Daemon: write agent def to ~/.synapse/agents/ → ack
   │
Browser: "Run now"  ──REST: agent.run──►  Cloud (write runs row) ──gRPC Connect──►  Daemon
   ▼
Daemon: render prompt → spawn `claude` subprocess → stream stdout
   │  every chunk → Redaction Middleware → upload queue → IngestTelemetry to gRPC hub
   ▼
Cloud:  persist trace/metrics [Postgres/Storage] → publish to
        Supabase Realtime channel org:acme:agent:{id}
   ▼
Browser: live trace viewer (supabase-js) updates token-by-token, cost ticks up
   ▼
Daemon: run completes → emits run.finished(status, cost, tokens)
   ▼
Cloud:  finalize run → notification service → Slack "✅ triage-bot done, $0.42"
```

### 4.2 Human-in-the-Loop on a sensitive action

```
Daemon: agent wants to run `git push --force`
   ▼  Ruleset Engine: matches "require-approval"
Daemon: SUSPEND run → emit hitl.request(action, diff, reasoning-so-far)
   ▼
Cloud:  write hitl_requests(pending) + audit_event → fan out:
        Slack interactive msg [Approve][Deny] + Web UI Approvals card
   ▼
Human:  clicks Approve in Slack (or Web UI)
   ▼
Cloud:  RBAC-check approver → write audit_event(approved, who/why)
        → publish hitl.resolve(approve) to daemon
   ▼
Daemon: RESUME run → executes the push → streams result
   ▼  (on timeout instead → default deny → run aborts → notify)
```

### 4.3 Webhook-triggered run

```
GitHub push → POST /hooks/{token} (Cloud)
   ▼
Cloud:  verify HMAC signature → map payload → create runs row → agent.run
   ▼  gRPC Connect stream → target daemon
Daemon: executes → telemetry flows back exactly as in 4.1
```

### 4.4 Anomaly detection → alert

```
Daemon: streams per-run cost/latency continuously
   ▼
Cloud:  async workers roll metrics into Postgres rollup tables (time buckets)
        anomaly engine: cost/task EWMA z-score breach OR p95 latency ≥ 3× baseline
   ▼
Cloud:  emit anomaly_event(severity, metric, baseline, observed)
   ▼
        → Alerts feed in Web UI  +  Slack/Discord/Email notification
```

### 4.5 Prompt regression → one-click rollback

```
Browser: deploy prompt v8  →  Cloud agent_versions(v8) → daemon
   ▼  v8 runs start failing; cloud sees error-rate spike for v8
Cloud:  surface "revert to v7 (known-good)" suggestion in Web UI
   ▼
Browser: click Rollback → Cloud sets current_version=v7 → agent.update_prompt
   ▼
Daemon: applies v7 → next runs green again. (v8 stays immutably in history.)
```

### 4.6 Set an environment variable (zero-knowledge, never on the cloud)

```
Browser: Agent → Environment → add OPENAI_API_KEY = sk-...
   ▼  fetch target daemon's X25519 public key
Browser: encrypt value client-side (libsodium sealed box) → ciphertext
   ▼  REST: env.set { name, ciphertext }   (Supabase JWT, RBAC checked)
Cloud:  write env_var_refs(name, scope, origin=ui)  ← NAME ONLY, no value
        relay ciphertext to daemon via hub  ← ciphertext NOT persisted
   ▼  gRPC Connect stream → org:acme:daemon:macbook-01
Daemon: decrypt with private key (in OS keychain) → store value in OS keyring
        register value with Redaction Middleware → ack (name only)
   ▼
Browser: Environment list shows OPENAI_API_KEY (write-only, can't read back)

   ── alternative: set locally ──
Operator: `synapse env set OPENAI_API_KEY=sk-... --agent triage-bot`
   ▼  value → OS keyring directly (never transmitted)
Daemon: report NAME ONLY upstream → Cloud env_var_refs(origin=local)
   ▼
Browser: shows it as read-only "set locally"

At run time: daemon injects keyring vars into the agent's process env.
The cloud never held the value; compromising the cloud yields names, not secrets.
```

### 4.7 Install a plugin (capability pack) from the web

```
Browser: Marketplace/Plugins → "browser-use" → Install → pick daemon "macbook-01", agent "web-bot"
   ▼  REST: plugin.install { plugin: browser-use@1.4.0, agent: web-bot }
Cloud:  RBAC check → verify platform compat → write plugin_installs(status=installing)
        send manifest + checksum → publish plugin.install over hub
   ▼  gRPC Connect stream → org:acme:daemon:macbook-01
Daemon: verify checksum → create isolated venv → install deps → playwright install
        register `browser` MCP server + tools → apply declared permissions (Ruleset)
        attach to agent web-bot → stream status: installing → ready (+ tool list)
   ▼  status/capabilities flow up via IngestTelemetry → Supabase Realtime
Browser: plugin shows "ready"; web-bot now has browser tools on its next run
   ▼
(next run) Daemon: agent can navigate/click/screenshot via the browser MCP server,
                   all actions governed by blockers + redaction.
```

### 4.8 Crash/blip mid-run → checkpointed resume (no work lost)

```
Daemon: run rn_77 executing step 14/30 ($3.10 spent so far)
        each step → write-ahead checkpoint to local SQLite + encrypted delta synced up
   ▼
─ scenario A: network blip ─
Daemon: keeps running offline; checkpoints + telemetry buffer locally
Cloud:  misses heartbeats → daemon offline, rn_77 → "interrupted" (outcome unknown)
   ▼  network returns
Daemon: run.reconcile { rn_77: seq=22 }  → uploads work done while disconnected
Cloud:  diff vs last-synced (seq=14) → ingest seq 15–22 → rn_77 back to "running"
   ▼
Browser: live trace catches up; nothing re-run, cost not double-counted

─ scenario B: daemon process crash, machine intact ─
Daemon: restarts → reads local journal → step 14 has intent+result (committed)
        → AUTO-RESUMES at step 15. No cloud round-trip needed.

─ scenario C: machine lost / new daemon adopts ─
Cloud:  heartbeat gone for good → issues run.recover to "macbook-02" (same org)
Daemon2: pulls last-known-good checkpoint (encrypted) → decrypts with ORG RECOVERY KEY
         → resumes at the saved step cursor with full memory restored
   ▼  (mid-tool intent without result → re-run if idempotent, else pause for HITL)
```

---

## 5. Where Each Responsibility Lives

| Concern | Web UI | Cloud Backend | TUI Daemon |
|---------|:------:|:-------------:|:----------:|
| User-facing control | ● | | |
| Auth / identity / RBAC | requests | **enforces** | presents token |
| Real-time routing | subscribes (Supabase Realtime) | **brokers (gRPC hub + Supabase Realtime)** | streams (gRPC over HTTP/2) |
| Agent execution | | | **runs** |
| Provider API keys / secrets | never | never | **keychain only** |
| Agent env-var values | encrypts (write-only) | relays ciphertext, name only | **decrypts → keyring → injects** |
| PII / secret redaction | shows markers | stores redacted | **redacts on-device** |
| Prompt-injection / jailbreak guard | configures policy + shows findings | baselines + alerts on spikes | **screens in/out, neutralizes, enforces** |
| Rulesets / blockers | authored | stored | **enforced** |
| Plugins / capabilities | browse + install | catalog + relay + status | **provisions (venv/MCP), sandboxes, runs** |
| HITL gate | resolves | routes + fans out | **pauses/resumes** |
| Scheduling | authored | stored | **fires (APScheduler)** |
| Run history / logs / audit | views | **system of record** | buffers + ships |
| Checkpointing / resume | shows status + override | detect loss, hold encrypted last-known-good, orchestrate | **journals locally, auto-resumes, decrypts to recover** |
| Analytics / anomaly detection | views | **computes** | emits metrics |
| Versioning / rollback | UI + diff | **immutable store** | applies version |
| Uptime monitoring | views | **derives from heartbeats** | heartbeats |
| Marketplaces | browse/install | **hosts/brokers** | installs |
| Notifications | configures | **fans out** | triggers events |

---

## 6. Cross-Cutting Guarantees

- **Trust boundary:** raw secrets and execution never leave the user's machine. Even a
  fully-compromised cloud cannot read provider keys or customer data, because the
  daemon redacts before transmitting and holds credentials in the OS keychain.
- **Content safety:** the daemon's Input/Output Filtering middleware screens *both*
  directions — redacting PII/secrets and detecting prompt-injection / jailbreak attempts
  in untrusted inbound content and in model output — *before* anything is acted on or
  uploaded. Rules are enforced by the daemon, not the model, so a successful injection
  still can't bypass a blocker; the cloud only baselines the resulting findings to alert
  on injection spikes.
- **Durability:** the daemon commits run results locally (SQLite WAL) before shipping;
  telemetry queues offline and replays in order on reconnect (at-least-once + idempotency
  keys). The cloud is the long-term system of record.
- **Durable execution:** long runs are **checkpointed** via a local write-ahead journal,
  so a crash or blip resumes from the last consistent step instead of restarting —
  never re-running expensive or non-idempotent work. Checkpoints sync to the cloud
  **E2E-encrypted** (org recovery key) so a run survives total local loss and can resume
  on another daemon, while the cloud still can't read the state.
- **Resilience:** outbound-only daemon gRPC streams (HTTP/2 keepalive) with
  exponential-backoff reconnect; stateless gRPC hub (presence/routing state in Postgres)
  so any node serves any daemon stream; browsers auto-resubscribe to Supabase Realtime
  on reconnect.
- **Wire efficiency:** Protocol Buffers on the daemon↔hub gRPC link (compact, typed,
  HTTP/2-multiplexed), JSON on the
  Supabase↔browser link (debuggability, native to `supabase-js`).
- **Auditability everywhere:** every command (who clicked what) and every agent
  decision (what it did and why) lands in the immutable, optionally hash-chained audit
  log — a complete chain from human intent → cloud routing → on-machine action.

---

## 7. One-Paragraph Summary

A user opens the **Web UI**, clicks once to deploy an agent onto a chosen **TUI
Daemon** running on their own machine. The click travels as a command to the **Cloud
Backend**, which authenticates it, records it, and routes it over a gRPC stream (HTTP/2)
to the daemon. The daemon executes the agent locally — calling APIs or CLI tools, enforcing
rulesets, redacting secrets, and pausing for human approval when needed — while
streaming a fully-redacted reasoning trace back through the cloud to the browser in
real time. The cloud persists everything, computes analytics and anomaly alerts,
versions every prompt for instant rollback, monitors daemon uptime, and fans out
notifications and HITL approvals to Slack, Discord, and email. Three products, one
seamless control loop: **see in the browser, broker in the cloud, run on the machine.**
