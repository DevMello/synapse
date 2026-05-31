# Synapse — TUI Worker Daemon

> The agent that lives on the user's machine. A Python package the user installs,
> running as a persistent daemon that executes agents, redacts secrets, and bridges
> the local environment to the Synapse cloud over a WebSocket.

---

## 1. Purpose & Role

The TUI Worker Daemon ("the worker", "the daemon") is the **execution substrate** of
Synapse. The Web UI and Cloud Backend are the *control plane*; the daemon is the
*data plane*. Nothing the user configures in the browser ever runs in the cloud — it
runs here, on the user's own hardware, inside the user's own environment, with the
user's own credentials.

It serves three jobs:

1. **Connection** — establish and maintain a secure, authenticated, bidirectional
   WebSocket to the Cloud Backend so the browser can drive it in real time.
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
│  │  - WS client    │   │   - dispatcher   │   └────────────────────┘  │
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

- Maintains a single multiplexed **WebSocket** (WSS) to the Cloud Backend.
- **Heartbeat**: sends `ping` every 15s; if 3 missed pongs, tears down and reconnects.
- **Reconnect**: exponential backoff with jitter (1s → 60s cap).
- **Auth**: presents access token on connect; transparently refreshes via the refresh
  token when a `401`/`token_expired` frame arrives.
- **Offline buffering**: while disconnected, all telemetry (logs, metrics, run results)
  is durably queued in the local SQLite WAL store and **replayed in order** on
  reconnect with at-least-once delivery (idempotency keys dedupe server-side).
- All frames are **MessagePack** for compactness; large log blobs are chunked.

### 4.2 Control Loop / Command Router

Receives commands from the cloud and routes them:

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

### 4.5 Redaction Middleware (PII / Secret Masking)

> **Hard guarantee: redaction runs on-device, before any byte leaves the machine.**

A streaming middleware that sits between the Agent Runtime's telemetry output and the
Connection Manager's upload queue. Every log line, tool argument, tool result, prompt,
and completion passes through it.

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
  queue, run history cache, and HITL state.
- Acts as the **durability boundary** — a run's results are committed locally first,
  then shipped. Nothing is lost if the network or cloud is down.

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

---

## 5. Security Posture

- Secrets (provider API keys, daemon refresh token) live **only** in the OS keychain.
- Outbound-only WSS connection — the daemon **never opens an inbound port**, so no
  firewall changes and no attack surface from the public internet.
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
| WebSocket client | `websockets` / `aiohttp` |
| Wire format | MessagePack |
| Scheduler | APScheduler |
| Local store | SQLite (WAL) |
| PII detection | regex + entropy + optional Presidio |
| Service mgmt | systemd / launchd / Windows Service |
| Secret / env-var storage | OS keychain (`keyring`) |
| E2E encryption | X25519 sealed box (`PyNaCl` / libsodium) |
| Plugins / capabilities | MCP servers + scripts; isolated venvs/workspaces per plugin |
| Packaging | PyPI (`synapse-worker`), pipx |

See **[integration.md](integration.md)** for how the daemon, cloud, and Web UI form
a single system.
