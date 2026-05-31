# Synapse — TUI Worker Daemon

> The agent that lives on the user's machine. A Python package the user installs,
> running as a persistent daemon that executes agents, redacts secrets, and bridges
> the local environment to the Synapse cloud over a gRPC stream (HTTP/2).

---

## 1. Purpose & Role

The TUI Worker Daemon ("the worker", "the daemon") is the **execution substrate** of
Synapse. The Web UI and Cloud Backend are the *control plane*; the daemon is the
*data plane*. Nothing the user configures in the browser ever runs in the cloud — it
runs here, on the user's own hardware, inside the user's own environment, with the
user's own credentials.

It serves three jobs:

1. **Connection** — establish and maintain a secure, authenticated, bidirectional
   **gRPC stream (HTTP/2)** to the Cloud Backend so the browser can drive it in real time.
2. **Execution** — run agents (API-based LLM agents *and* CLI tools like `claude`,
   `aider`, `gemini`, shell scripts) inside isolated, monitored processes on a
   schedule, webhook, or manual trigger.
3. **Protection** — redact PII/secrets *before* anything leaves the machine, enforce
   per-agent rulesets/blockers, and pause for Human-in-the-Loop approval on sensitive
   actions.

It is called "TUI" because, in addition to running headless as a daemon/service, it
ships a **rich terminal user interface** (built with [Textual](https://textual.textualize.io/))
for local operators who want to watch live agent output, tail logs, approve HITL
gates, and manage the daemon without a browser.

---

## 2. Distribution & Installation

### Package

- Published to **PyPI** as `synapse-worker`.
- Python **3.11+** (uses `asyncio.TaskGroup`, `tomllib`, modern typing).
- Cross-platform: Windows 10+, macOS 12+, Linux (glibc 2.31+).

```bash
pipx install synapse-worker        # recommended (isolated)
# or
pip install synapse-worker
```

### First-run pairing

```bash
synapse login          # opens browser, OAuth device-code flow, stores a daemon token
synapse init           # interactive setup: daemon name, tags, workdir, resource caps
synapse daemon install # registers as a system service (see below)
synapse daemon start
```

`synapse login` uses the **OAuth 2.0 Device Authorization Grant**: the CLI prints a
short code + URL, the user approves in the browser (already authenticated to Synapse),
and the daemon receives a long-lived **refresh token** + short-lived **access token**.
The refresh token is stored in the OS keychain (Keychain on macOS, Credential Manager
on Windows, Secret Service / libsecret on Linux), never in plaintext on disk.

On first pairing the daemon also generates an **end-to-end encryption keypair**
(X25519, libsodium). The **private key stays in the OS keychain and never leaves the
machine**; the **public key is registered with the cloud**. This is what the Web UI
uses to encrypt env-var values so the cloud can only ever relay opaque ciphertext (see
[§4.10](#410-environment-variable-vault)).

The daemon also receives (via the user's authenticated session) the **org recovery key**
— an org-scoped X25519 keypair whose private half is held only in the keychains of
authorized daemons. Checkpoints are encrypted to its public key before being synced to
the cloud, so any authorized daemon in the org can decrypt and **resume an interrupted
run** even if the original machine is gone (see [§4.12](#412-checkpointing-resume--recovery)).

### Running as a service

| OS | Mechanism |
|----|-----------|
| Linux | `systemd` user unit (or system unit with `--system`) |
| macOS | `launchd` LaunchAgent / LaunchDaemon plist |
| Windows | Windows Service via `pywin32` / NSSM-style shim |

`synapse daemon install` generates and registers the appropriate unit. The daemon
auto-restarts on crash and on boot, and reconnects to the cloud automatically.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        synapse-worker (single process)               │
│                                                                       │
│  ┌────────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │  Connection     │   │   Control Loop   │   │   Textual TUI      │  │
│  │  Manager        │◄─►│   (asyncio core) │◄─►│   (optional front) │  │
│  │  - gRPC client  │   │   - dispatcher   │   └────────────────────┘  │
│  │  - reconnect    │   │   - heartbeat    │                           │
│  │  - auth refresh │   │   - cmd router   │                           │
│  └────────────────┘   └────────┬─────────┘                           │
│                                  │                                     │
│        ┌─────────────────────────┼──────────────────────────┐         │
│        ▼                         ▼                          ▼         │
│  ┌───────────┐         ┌──────────────────┐        ┌───────────────┐  │
│  │ Scheduler │         │  Agent Runtime   │        │  Local Store  │  │
│  │ (APScheduler)       │  (per-run process│        │  (SQLite +    │  │
│  │ cron/interval│      │   supervisor)    │        │   WAL queue)  │  │
│  └───────────┘         └────────┬─────────┘        └───────────────┘  │
│                                  │                                     │
│   ┌──────────────────────────────┼──────────────────────────────┐    │
│   ▼              ▼               ▼              ▼                ▼    │
│ ┌────────┐  ┌─────────┐   ┌────────────┐  ┌──────────┐   ┌──────────┐│
│ │ API    │  │ CLI     │   │ Redaction  │  │ Ruleset  │   │ HITL     ││
│ │ Adapter│  │ Adapter │   │ Middleware │  │ Engine   │   │ Gatekeeper││
│ └────────┘  └─────────┘   └────────────┘  └──────────┘   └──────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### Concurrency model

- Single process, **asyncio** event loop core.
- Each **agent run** is a supervised child: API runs use async HTTP clients in-loop;
  CLI runs spawn a subprocess (`asyncio.create_subprocess_exec`) with streamed
  stdout/stderr. CPU-bound redaction passes run in a `ProcessPoolExecutor`.
- A global + per-agent **concurrency limiter** (semaphores) prevents resource
  exhaustion. Configurable `max_concurrent_runs`, `max_memory_mb`, `cpu_quota`.

---

## 4. Components in Detail

### 4.1 Connection Manager

- Maintains a single outbound **gRPC connection (HTTP/2)** to the Cloud Backend, opened
  with `grpcio` (grpc.aio async client). Two RPCs multiplex over the one connection:
  - **`Connect(stream DaemonMessage) → stream CloudMessage`** — a long-lived
    **bidirectional-streaming** RPC carrying control + HITL both ways. The daemon (the
    client) always initiates it, so no inbound port is ever opened.
  - **`IngestTelemetry(stream TelemetryFrame) → TelemetryAck`** — a separate
    **client-streaming** RPC for the high-volume trace/metric firehose, on its own HTTP/2
    stream so a flood of trace chunks can't head-of-line-block control or HITL messages.
- **Liveness**: HTTP/2 **keepalive PINGs** (grpc keepalive params) detect a dead
  transport; an app-level heartbeat message every 15s drives cloud presence/uptime.
- **Reconnect**: exponential backoff with jitter (1s → 60s cap); a dropped stream is
  re-opened and both RPCs re-established.
- **Auth**: presents the daemon access token as gRPC call **metadata**
  (`authorization: Bearer …`) when opening each stream; transparently refreshes via the
  refresh token on an `UNAUTHENTICATED` status and re-opens. Optionally pinned with
  **mTLS** (daemon client cert) since the daemon has a stable identity.
- **Offline buffering**: while disconnected, all telemetry (logs, metrics, run results)
  is durably queued in the local SQLite WAL store and **replayed in order** on
  reconnect with at-least-once delivery (idempotency keys dedupe server-side). gRPC gives
  ordered delivery *within* a stream but no redelivery across reconnects, so these
  app-level sequence numbers + acks remain the source of truth — not the transport.
- **Reconnect reconciliation**: on every reconnect the daemon sends a `run.reconcile`
  message (on the `Connect` stream) listing its in-flight/finished runs and their latest
  checkpoint sequence numbers, so the cloud and daemon agree on state and any work done
  offline is uploaded (see [§4.12](#412-checkpointing-resume--recovery)).
- All messages are **Protocol Buffers** (the `.proto` schema is the wire contract);
  large log blobs are chunked across `TelemetryFrame`s.

### 4.2 Control Loop / Command Router

Receives commands from the cloud as `CloudMessage`s on the `Connect` stream and routes
them (each `CloudMessage` carries a oneof command payload + an idempotency key):

| Command | Action |
|---------|--------|
| `agent.deploy` | install/update an agent definition locally |
| `agent.run` | trigger an immediate run |
| `agent.cancel` | kill a running agent process |
| `agent.update_prompt` | apply a new prompt version |
| `schedule.set` | register/replace a cron/interval schedule |
| `skill.install` | install a skill for an agent/platform |
| `mcp.configure` | wire up an MCP server for an agent |
| `plugin.install` | provision a capability pack (MCP/script/workspace) + attach to an agent |
| `plugin.remove` | detach + uninstall a plugin |
| `env.set` | decrypt an E2E-encrypted env var and store it in the keyring |
| `env.delete` | remove an env var from the keyring |
| `hitl.resolve` | deliver an approve/deny decision to a paused run |
| `run.recover` | adopt + resume an interrupted run from its last-known-good checkpoint |
| `daemon.update` | self-update the worker package |
| `daemon.ping` | uptime/health probe |

### 4.3 Agent Runtime

The heart of execution. An **agent definition** (synced from the cloud) is a manifest:

```toml
# ~/.synapse/agents/triage-bot/agent.toml
[agent]
id = "agt_8f3..."
name = "triage-bot"
type = "api"            # "api" | "cli"
platform = "any"        # "any" | "windows" | "macos" | "linux"
version = 7             # active prompt version

[api]                   # when type = "api"
provider = "anthropic"  # anthropic | openai | google | openrouter | custom
model = "claude-opus-4-7"
max_tokens = 4096
temperature = 0.2

[cli]                   # when type = "cli"
command = "claude"
args = ["-p", "{{prompt}}", "--output-format", "json"]
cwd = "/home/user/repos/app"

[limits]
max_cost_usd = 2.00
timeout_sec = 600
max_tool_calls = 50

[[tools]]               # provided by default capabilities or installed plugins (§4.11)
name = "github"
type = "mcp"
endpoint = "stdio:///usr/local/bin/github-mcp"
```

- An agent's available tools come from the **default built-in MCP servers** plus any
  **plugins** attached to it (see [§4.11](#411-plugin-runtime--capability-packs)).
- **Prompts, skills, rulesets** live as versioned files under the agent dir and are
  rendered with a templating engine (`{{var}}`) at run time.
- The runtime captures a **full reasoning trace**: every prompt, completion, tool
  call, tool result, token count, latency, and cost, streamed live to the cloud and
  persisted locally.
- The runtime is **checkpointed**: it writes a durable session-state checkpoint after
  each step/tool call so a crash or network blip never loses progress or forces a
  re-run of expensive work (see [§4.12](#412-checkpointing-resume--recovery)).

#### API Adapter

- Pluggable providers (Anthropic, OpenAI, Google, OpenRouter, local Ollama, custom
  base URL). Normalizes streaming, tool-use, and usage accounting to a common shape.
- Computes **cost per run** from token usage × provider price table (kept fresh by
  the cloud).

#### CLI Adapter

- Wraps arbitrary command-line agents (`claude`, `aider`, `gemini`, custom scripts).
- Streams stdout/stderr line-by-line, parses structured output (JSON) when available,
  enforces timeouts, and captures exit codes.
- Runs in a sandboxed working dir with a scrubbed environment (only whitelisted env
  vars + injected secrets from the keychain).

### 4.4 Scheduler

- Built on **APScheduler** with a SQLite jobstore (survives restarts).
- Supports cron expressions, fixed intervals, and one-shot scheduled runs.
- Schedules are authored in the Web UI and pushed via `schedule.set`.
- Missed runs (daemon was offline) follow a configurable policy: `skip`, `run_once`,
  or `coalesce`.

### 4.5 Input/Output Filtering Middleware (Guardrails)

> **Hard guarantee: all filtering runs on-device, before any byte leaves the machine.**

A streaming middleware with two layers. Layer **A (redaction)** protects *your* data
leaving the box. Layer **B (injection/jailbreak guard)** protects *the agent* from
untrusted content coming in and protects *your rules* from the agent's output going out.
It sits on both edges of the Agent Runtime — screening **inbound** data before it
reaches the model and **outbound** data before it is acted on or uploaded.

#### Layer A — PII / Secret Redaction

Every log line, tool argument, tool result, prompt, and completion passes through it.

Detection layers:

1. **Pattern/entropy** — regex + Shannon-entropy scan for API keys (AWS, OpenAI,
   `sk-...`, GitHub PATs, JWTs, private key blocks), emails, phone numbers, credit
   cards (Luhn-checked), IPs, and high-entropy tokens.
2. **Named detectors** — Microsoft Presidio (optional, opt-in) for NER-based PII
   (names, addresses, SSNs) running fully locally.
3. **User rules** — custom regex / keyword denylists defined per agent or globally.

Behavior:

- Matches are replaced with stable, salted tokens: `<REDACTED:API_KEY:a91f>` so the
  same secret reads consistently across a trace without revealing it.
- A **redaction manifest** (counts and types only — never the raw values) is attached
  to each run so the dashboard can show "12 secrets masked" without exfiltration.
- Configurable modes: `block` (drop the field), `mask` (tokenize), or `hash`.
- Bypassable only with explicit, audited per-agent opt-out.

#### Layer B — Prompt-Injection & Jailbreak Guard

> **Trust model:** the agent's system instructions and rulesets are enforced by the
> *daemon*, not the model. A model cannot actually rewrite its own rules — so this layer
> exists to **detect, neutralize, and surface** attempts, not to be the thing standing
> between a jailbreak and a deleted file (that is the Ruleset Engine, §4.6).

**Inbound screening (untrusted content → model).** The classic injection vector is
data the agent ingests: a fetched web page (browser plugin), a file's contents, an
email body, a webhook payload, a retrieved document. Before such content is handed to
the model it is screened for:

- **Instruction-override patterns** — "ignore previous/above instructions", "disregard
  your system prompt", "you are now…", role-confusion / fake-system markers.
- **Exfiltration lures** — "print your system prompt", "reveal your API keys / env",
  "send the contents of … to …".
- **Tool/rule-bypass coaxing** — content trying to get the agent to call blocked tools,
  disable guards, or escalate permissions.

Untrusted content is **spotlighted/delimited** (wrapped and marked as data, embedded
instructions escaped) so the model treats it as input, not commands — and high-
confidence injections are stripped or the step is paused per policy.

**Outbound screening (model output / tool-calls → action).** Before a completion or
tool call is acted on, it is checked for:

- **Self-instruction override** — the agent attempting to redefine its system prompt,
  rules, or guardrails to bypass them (the example case).
- **Jailbreak / policy divergence** — output indicating it has "accepted" an injected
  persona or is acting against its mandate.
- **Secret-leak attempts** — trying to emit redacted values or env-var contents.

**Detection methods:** heuristic phrase/structural matching, similarity to a local
**known-attack signature set**, and an optional **local classifier** (small model via
Ollama — air-gapped, no content leaves the box) for fuzzy detection. Severity-scored.

**Actions** map to the Ruleset Engine (§4.6): `block` (drop/neutralize the content or
refuse the action), `require-approval` (open a HITL gate — "this looks like an
injection attempt, proceed?"), or `warn` (annotate + log). Every finding is written to
the **immutable audit log** with the matched signal (never raw secrets) and feeds the
cloud's **injection-attempt anomaly detector** (§6 of the backend).

**Config (per agent / global):** which directions to screen (inbound/outbound/both),
sensitivity, whether to enable the local classifier, and the default action per
severity. Like redaction, opt-out is explicit and audited.

### 4.6 Ruleset / Blocker Engine

Per-agent policy enforced **before and during** execution:

- **Command blockers** — deny-list / allow-list for shell commands and tool calls
  (e.g. block `rm -rf`, `git push --force`, `DROP TABLE`).
- **Path guards** — restrict filesystem writes to allowed directories.
- **MCP gating** — control which MCP servers/tools an agent may invoke.
- **Network policy** — allow-list of outbound hosts.
- **Cost/usage caps** — hard-stop a run that exceeds `max_cost_usd` or `max_tool_calls`.

Violations either **block** (abort the action), **require HITL approval**, or **warn
and log**, per rule severity.

### 4.7 HITL Gatekeeper

When a ruleset marks an action as sensitive (or an agent explicitly requests
approval), the run **pauses** and:

1. The runtime emits a `hitl.request` frame to the cloud with the proposed action,
   its full context/diff, and the reasoning trace so far.
2. The cloud fans out an approval prompt to the configured channel (Slack / Discord /
   Email / Web UI).
3. The run blocks (with a configurable timeout → default deny) until a
   `hitl.resolve {approve|deny, actor, reason}` arrives.
4. The local TUI also shows the pending gate so an at-keyboard operator can approve.

The pause is real: the child process is suspended / awaiting, not polled.

### 4.8 Local Store

- **SQLite (WAL mode)** for: agent definitions, schedules, the outbound telemetry
  queue, run history cache, HITL state, and the **run checkpoint / write-ahead journal**
  (§4.12).
- Acts as the **durability boundary** — a run's results (and each checkpoint) are
  committed locally first, then shipped. Nothing is lost if the network or cloud is down.

### 4.9 Textual TUI (local front-end)

Optional but first-class. `synapse tui` opens an interactive terminal dashboard:

- **Agents** pane — list, status, last run, next scheduled run.
- **Live** pane — streaming reasoning trace of the active run (tokens, tool calls).
- **Logs** pane — searchable, filterable, with redaction markers visible.
- **Approvals** pane — pending HITL gates with approve/deny keybindings.
- **Daemon** pane — connection status, uptime, resource usage, version.

### 4.10 Environment Variable Vault

Manages the env vars an agent's runs execute with. **Values live only in the OS keyring
on this machine — never on the cloud, and never in plaintext on disk.** Two ways in:

**1. Pushed from the Web UI (end-to-end encrypted).**
- The browser encrypts each value to this daemon's **X25519 public key** (libsodium
  sealed box) and sends only ciphertext.
- The cloud relays it as an opaque blob via `env.set`. The daemon decrypts it with the
  **private key held in the OS keychain** and writes the value to the keyring under a
  per-agent namespace (e.g. service `synapse:agent:{id}:env`, key = var name).
- The cloud never holds the plaintext and cannot decrypt the ciphertext — it has no
  access to the private key.

**2. Set locally on the daemon.**

```bash
synapse env set OPENAI_API_KEY=sk-... --agent triage-bot   # stored in keyring
synapse env set LOG_LEVEL=debug --agent triage-bot --plain # non-secret
synapse env list --agent triage-bot                         # names only (no values)
synapse env rm OPENAI_API_KEY --agent triage-bot
synapse env set DEPLOY_ENV=prod --shared                    # daemon/org-wide shared set
```

- Locally-set vars are stored in the same keyring namespace. The daemon reports their
  **names only** (never values) up to the cloud so the Web UI can show them as
  read-only "set locally" entries.

**Resolution & injection at run time.**
- On each run, the runtime loads the agent's effective environment: **shared set →
  agent set**, with a documented precedence where **locally-set vars override
  cloud-pushed vars** of the same name (so an at-keyboard operator can always override).
- For **CLI agents**, vars are injected into the subprocess environment (on top of the
  otherwise-scrubbed env). For **API agents**, they are available to the adapter/tooling.
- Every loaded secret value is **registered with the Redaction Middleware** for that
  run, so it is masked in logs even if the agent echoes it.

### 4.11 Plugin Runtime & Capability Packs

Plugins are **installable capabilities** that give an agent new *actions* (vs. skills,
which give it knowledge). A plugin is provisioned on the daemon and attached to one or
more agents; the user installs them from the Web UI and they load onto the agent running
on the selected daemon.

#### Default (built-in) capabilities

The daemon ships with a set of **default MCP servers** available to any agent without
installation — typically `filesystem`, `fetch`/HTTP, and `git`. These are the baseline;
everything else is an installable plugin.

#### Plugin kinds

| Kind | What it is | Examples |
|------|-----------|----------|
| `mcp` | a quick-install of an MCP server the agent can call | GitHub, Slack, Postgres MCP |
| `script` | local tools/scripts the runtime exposes as callable tools | a custom `screenshot` or `lint` tool |
| `workspace` | an isolated coding environment for a project | Python venv, Node/`nvm`, repo checkout |
| `composite` | a bundle of the above with setup steps | **browser-use**, **terminal-use**, **file-explorer** |

First-party packs called out in the spec:

- **Browser use** — Playwright-driven browser automation (navigate, click, screenshot),
  shipped as a composite plugin that creates a venv, installs Playwright + a browser,
  and registers a `browser` MCP server.
- **Terminal use** — a **sandboxed shell** tool with the ruleset/blocker engine wired
  in (so denied commands and HITL gates apply to shell actions).
- **File explorer** — scoped filesystem browse/read/write tools bounded to allowed paths.
- **Custom coding environments** — per-project `workspace` plugins that provision an
  isolated **virtual environment** (Python venv, Node version, etc.) + a working dir, so
  CLI coding agents (`claude`, `aider`) run in a reproducible, isolated environment. The
  workspace becomes the agent's `cwd`.

#### Plugin manifest

```toml
# ~/.synapse/plugins/browser-use/plugin.toml
[plugin]
id = "plg_4a1..."
name = "browser-use"
version = "1.4.0"
kind = "composite"
platforms = ["windows", "macos", "linux"]

[install]
runtime = "python"                       # daemon creates an isolated venv
deps = ["browser-use>=0.2", "playwright>=1.44"]
post_install = ["playwright install chromium"]

[[provides.mcp]]                         # tools exposed via an MCP server
name = "browser"
transport = "stdio"
command = "python -m browser_use.mcp"

[[provides.tool]]                        # or a local script tool
name = "screenshot"
exec = "scripts/screenshot.py"

[permissions]                            # enforced by the Ruleset Engine (§4.6)
network = ["*"]
filesystem = ["./downloads"]
requires_hitl = false
```

#### Install & lifecycle (on receiving `plugin.install`)

1. **Resolve** the manifest (from the cloud's plugin catalog / marketplace).
2. **Check platform** compatibility against this daemon's OS.
3. **Provision** in isolation: create a dedicated venv/workspace under
   `~/.synapse/plugins/{name}/`, install deps, run `post_install`.
4. **Register** the plugin's MCP servers and/or script tools with the Agent Runtime and
   apply its declared `permissions` to the Ruleset Engine.
5. **Attach** to the target agent(s); report status (`installing → ready | failed`) and
   the resulting tool capabilities upstream for display in the Web UI.

Plugins are **versioned and removable** (`plugin.remove` detaches and tears down the
venv/workspace). Health of long-running plugin processes (e.g. an MCP server) feeds the
same heartbeat/uptime stream as the daemon.

#### Local CLI

```bash
synapse plugin search browser                       # browse the catalog
synapse plugin install browser-use --agent web-bot  # provision + attach
synapse plugin list --agent web-bot                 # installed + status
synapse plugin remove browser-use --agent web-bot
synapse plugin install ./my-plugin                  # install a local/unpublished pack
```

#### Isolation & safety

- Each plugin runs in its **own venv/sandbox**; declared `permissions` are enforced by
  the Ruleset Engine, and all plugin output passes through the Redaction Middleware.
- A `composite`/`script` plugin's executables are **signature/checksum-verified** against
  the catalog before running, same as daemon self-updates.

### 4.12 Checkpointing, Resume & Recovery

Agent runs last minutes to hours and may involve expensive API calls and partial file
operations. A crash or network blip must **never** force a restart from scratch. The
daemon implements **durable execution**: every run advances through a write-ahead
journal so it can be resumed from its last consistent point.

#### What a checkpoint contains

A checkpoint is a monotonically-numbered snapshot of **session state** for one run:

- `run_id`, `agent_version`, and a **step cursor** (which step/turn is next).
- **Agent memory**: the conversation/messages, scratchpad, and accumulated context.
- **Current tool call**: its intent, an **idempotency key**, and status
  (`pending → in_flight → committed`) plus the result once it returns.
- **Progress markers**: completed sub-tasks and a **file-operation journal** (what was
  written/changed, with hashes) for idempotent replay.
- **Accounting so far**: tokens and cost, so resumed runs don't double-count or blow
  past `max_cost_usd`.

#### Write-ahead journaling (how it stays consistent)

Checkpoints are written to the **local SQLite WAL store** as an append-only journal:

1. **Before** executing a tool call, record `intent` (+ idempotency key) and commit.
2. Execute the tool.
3. **After** it returns, record `result` and advance the step cursor.

On resume the runtime reads the journal:

- A step with `intent` **and** `result` → already done, **skip** (no re-run, no
  duplicate side effect).
- A step with `intent` but **no** `result` → the crash happened mid-tool. The runtime
  applies the agent's **resume policy** for ambiguous in-flight steps: re-run if the
  tool is declared **idempotent**, else **pause for HITL** ("did this push happen?")
  rather than risk a duplicate side effect.

#### Cloud sync of checkpoints (durable backup, zero-knowledge)

- Checkpoints are also shipped to the cloud as the **last-known-good state** so a run
  survives total local loss (disk failure, machine reinstall, or moving the run to
  another daemon).
- Because session memory can contain sensitive data, the **checkpoint payload is
  E2E-encrypted** to an **org recovery key** (X25519; private key held in the keychain
  of authorized daemons in the org) before upload — reusing the env-var crypto pattern.
  The cloud stores **opaque ciphertext** plus non-sensitive **plaintext metadata** only
  (run_id, sequence number, step cursor, status, cost) for orchestration and dashboards.
- Sync is **incremental** (journal deltas) and best-effort while online; if offline,
  checkpoints queue locally and upload on reconnect.

#### Recovery scenarios

| Failure | What happens |
|---------|--------------|
| **Daemon process crash, machine intact** | On restart the daemon reads the local journal and **auto-resumes** every interrupted run from its last consistent step — no cloud round-trip needed. |
| **Network blip, run still executing** | The run keeps going offline; checkpoints + telemetry buffer locally. On reconnect the daemon sends `run.reconcile` and **uploads the work it completed while disconnected**; live streaming resumes. |
| **Local store lost / new daemon adopts the run** | The cloud detects heartbeat loss, marks the run `interrupted`, and on a suitable daemon reconnect issues `run.recover`. That daemon **pulls the cloud's last-known-good (encrypted) checkpoint**, decrypts it with the org recovery key, and resumes. |

#### Resume policy (per agent)

`auto-resume` (default) · `resume-with-approval` · `restart` · `abort`. Auto-resume
honors the idempotency/HITL safety check above, so "without manual intervention" never
means "blindly repeat a dangerous action."

---

## 5. Security Posture

- Secrets (provider API keys, daemon refresh token) live **only** in the OS keychain.
- Outbound-only gRPC/HTTP-2 connection — the daemon (the gRPC client) **never opens an
  inbound port**, so no firewall changes and no attack surface from the public internet.
  Even the server→daemon command stream rides the daemon-initiated bidirectional RPC.
- Redaction + rulesets enforced locally; the cloud cannot exfiltrate raw secrets even
  if compromised, because they are masked before transmission.
- **Env vars are E2E-encrypted**: the daemon's X25519 private key never leaves the
  keychain, so env-var values pushed from the Web UI are unreadable by the cloud — it
  only ever relays ciphertext. Values rest in the OS keyring, never on disk or cloud.
- Per-run process isolation with scrubbed env and resource quotas.
- Self-update packages are signature-verified before install.

---

## 6. Uptime & Health Reporting

- Emits a heartbeat + health snapshot (CPU, mem, disk, active runs, queue depth,
  worker version) every 15s.
- The cloud derives **per-daemon uptime monitoring** and alerts from this stream
  (missed heartbeats → `daemon.offline` event → notifications).

---

## 7. Tech Stack Summary

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| Async core | `asyncio` |
| TUI | Textual |
| CLI | Typer / Click |
| Transport / RPC | gRPC over HTTP/2 (`grpcio`, grpc.aio async client) |
| Wire format | Protocol Buffers (`grpcio-tools` codegen) |
| Scheduler | APScheduler |
| Local store | SQLite (WAL) |
| PII detection | regex + entropy + optional Presidio |
| Service mgmt | systemd / launchd / Windows Service |
| Secret / env-var storage | OS keychain (`keyring`) |
| E2E encryption | X25519 sealed box (`PyNaCl` / libsodium) |
| Plugins / capabilities | MCP servers + scripts; isolated venvs/workspaces per plugin |
| Durable execution | SQLite write-ahead checkpoint journal + idempotency keys |
| Packaging | PyPI (`synapse-worker`), pipx |

See **[integration.md](integration.md)** for how the daemon, cloud, and Web UI form
a single system.
