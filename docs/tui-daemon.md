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

[[tools]]               # MCP servers, local tools
name = "github"
type = "mcp"
endpoint = "stdio:///usr/local/bin/github-mcp"
```

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

---

## 5. Security Posture

- Secrets (provider API keys, daemon refresh token) live **only** in the OS keychain.
- Outbound-only WSS connection — the daemon **never opens an inbound port**, so no
  firewall changes and no attack surface from the public internet.
- Redaction + rulesets enforced locally; the cloud cannot exfiltrate raw secrets even
  if compromised, because they are masked before transmission.
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
| Secret storage | OS keychain (`keyring`) |
| Packaging | PyPI (`synapse-worker`), pipx |

See **[integration.md](integration.md)** for how the daemon, cloud, and Web UI form
a single system.
