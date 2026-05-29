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
   ┌──────────────┐        WSS + HTTPS        ┌──────────────────┐        WSS         ┌──────────────────┐
   │   Web UI     │ ◄───────────────────────► │  Cloud Backend   │ ◄────────────────► │  TUI Daemon(s)   │
   │  (browser)   │     commands / telemetry  │   (broker +      │   commands /       │  (user machines) │
   │ CONTROL PLANE│                           │    historian)    │   telemetry        │   DATA PLANE     │
   └──────────────┘                           └──────────────────┘                    └──────────────────┘
        sees                                    routes + stores                          executes + protects
```

Three invariants define every interaction:

1. **The browser and the daemon never talk directly.** The cloud brokers everything.
2. **The cloud never executes agents or holds raw secrets.** Execution and credentials
   stay on the daemon; the cloud stores config, policy, and (pre-redacted) telemetry.
3. **The daemon connects outbound-only.** No inbound ports on user machines; the
   WebSocket is always initiated from the daemon to the cloud.

---

## 2. Connection Establishment

### Daemon ↔ Cloud
1. User installs `synapse-worker`, runs `synapse login` → **OAuth device-code flow**.
2. Daemon receives a refresh token (stored in OS keychain) + access token.
3. Daemon opens an outbound **WSS** to the cloud, authenticates with the access token,
   and registers (name, tags, platform, version).
4. Cloud marks the daemon **online**, records presence in Redis, subscribes it to its
   `org:{id}:daemon:{id}` channel.
5. Daemon heartbeats every 15s → cloud derives uptime + offline alerts.

### Browser ↔ Cloud
1. User logs in via **OAuth auth-code + PKCE**.
2. Browser opens a **WSS** to the cloud and subscribes to the resources in view
   (fleet-level on the dashboard, agent-level on a detail page).

The cloud is the only endpoint either side knows about.

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
| Configure MCP / blockers | persist policy | `mcp.configure` |
| Approve/deny HITL | write audit + decision | `hitl.resolve` |
| Rollback to version | set `current_version` | `agent.update_prompt` |

### Upstream: telemetry (Daemon → Cloud → Browser)

While an agent runs, the daemon streams a reasoning trace. The cloud persists it
(Postgres records, ClickHouse metrics/logs, S3 blobs) **and** republishes it live to
any subscribed browser:

| Daemon emits | Cloud does | Browser sees |
|--------------|-----------|--------------|
| prompt / completion chunks | persist trace + republish | live trace viewer |
| tool call + result (redacted) | store `tool_calls` | tool logs, trace |
| token usage + cost | aggregate metrics | analytics, running cost |
| run finished (status, totals) | finalize `runs` | run history, notification |
| `hitl.request` | create gate, fan out | approvals queue + Slack/Discord/Email |
| heartbeat / health | update presence | daemon uptime |
| anomaly-relevant metrics | feed anomaly engine | alerts feed |

---

## 4. End-to-End Walkthroughs

### 4.1 Create and run an agent (one click → live)

```
Browser: New Agent → pick daemon "macbook-01", type=CLI (claude code)
   │  WS: agent.create
   ▼
Cloud:  validate RBAC → write agents + agent_versions(v1) → publish agent.deploy
   │  WS → org:acme:daemon:macbook-01
   ▼
Daemon: write agent def to ~/.synapse/agents/ → ack
   │
Browser: "Run now"  ──WS: agent.run──►  Cloud (create runs row) ──►  Daemon
   ▼
Daemon: render prompt → spawn `claude` subprocess → stream stdout
   │  every chunk → Redaction Middleware → upload queue → WS to cloud
   ▼
Cloud:  persist trace/metrics → republish to org:acme:agent:{id}
   ▼
Browser: live trace viewer updates token-by-token, running cost ticks up
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
   ▼  WS → target daemon
Daemon: executes → telemetry flows back exactly as in 4.1
```

### 4.4 Anomaly detection → alert

```
Daemon: streams per-run cost/latency continuously
   ▼
Cloud:  async workers roll metrics into ClickHouse buckets
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

---

## 5. Where Each Responsibility Lives

| Concern | Web UI | Cloud Backend | TUI Daemon |
|---------|:------:|:-------------:|:----------:|
| User-facing control | ● | | |
| Auth / identity / RBAC | requests | **enforces** | presents token |
| Real-time routing | subscribes | **brokers (Redis pub/sub)** | streams |
| Agent execution | | | **runs** |
| Provider API keys / secrets | never | never | **keychain only** |
| PII / secret redaction | shows markers | stores redacted | **redacts on-device** |
| Rulesets / blockers | authored | stored | **enforced** |
| HITL gate | resolves | routes + fans out | **pauses/resumes** |
| Scheduling | authored | stored | **fires (APScheduler)** |
| Run history / logs / audit | views | **system of record** | buffers + ships |
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
- **Durability:** the daemon commits run results locally (SQLite WAL) before shipping;
  telemetry queues offline and replays in order on reconnect (at-least-once + idempotency
  keys). The cloud is the long-term system of record.
- **Resilience:** outbound-only daemon sockets with exponential-backoff reconnect;
  stateless cloud realtime tier (state in Redis) so any node serves any socket;
  browser auto-resubscribes on reconnect.
- **Wire efficiency:** MessagePack on daemon↔cloud links (volume), JSON on
  cloud↔browser (debuggability).
- **Auditability everywhere:** every command (who clicked what) and every agent
  decision (what it did and why) lands in the immutable, optionally hash-chained audit
  log — a complete chain from human intent → cloud routing → on-machine action.

---

## 7. One-Paragraph Summary

A user opens the **Web UI**, clicks once to deploy an agent onto a chosen **TUI
Daemon** running on their own machine. The click travels as a command to the **Cloud
Backend**, which authenticates it, records it, and routes it over a WebSocket to the
daemon. The daemon executes the agent locally — calling APIs or CLI tools, enforcing
rulesets, redacting secrets, and pausing for human approval when needed — while
streaming a fully-redacted reasoning trace back through the cloud to the browser in
real time. The cloud persists everything, computes analytics and anomaly alerts,
versions every prompt for instant rollback, monitors daemon uptime, and fans out
notifications and HITL approvals to Slack, Discord, and email. Three products, one
seamless control loop: **see in the browser, broker in the cloud, run on the machine.**
