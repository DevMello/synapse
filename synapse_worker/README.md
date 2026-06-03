# synapse-worker

The **TUI Worker Daemon** of [Synapse](../docs/tui-daemon.md) — the agent that lives on
your machine. A Python daemon that connects outbound-only to the Synapse cloud over a
WebSocket, executes agents (API-based LLMs *and* CLI tools like `claude`, `aider`,
`gemini`), **redacts PII/secrets before anything leaves the box**, enforces per-agent
rulesets, pauses for human approval, checkpoints long runs, and ships a rich terminal UI.

> Control plane in the browser, broker in the cloud, **execution on your machine**. Raw
> secrets and execution never leave your hardware.

## Install

```bash
pipx install synapse-worker        # recommended (isolated)
# or
pip install synapse-worker
```

Python **3.11+**. Cross-platform: Windows 10+, macOS 12+, Linux (glibc 2.31+).

## First-run pairing

```bash
synapse login           # OAuth 2.0 device-code flow — no password typed in the terminal
synapse init            # interactive setup: daemon name, tags, workdir, resource caps
synapse daemon install  # register as a system service (systemd / launchd / Windows Service)
synapse daemon start
```

`synapse login` opens the device-code flow: the CLI prints a `user_code` (`ABCD-1234`) +
URL (and a QR), you approve it in the already-authenticated Web UI, and the daemon stores
a short-lived, **revocable** access token + a rotating refresh token in the **OS keychain**
(an encrypted `0600` file is the fallback on headless boxes). On first pair the daemon also
generates an X25519 keypair — its **private key never leaves the machine**; the public key
is registered with the cloud so the Web UI can encrypt env-var values only this daemon can
open.

## Everyday commands

| Command | What it does |
|---------|--------------|
| `synapse tui` | live terminal dashboard — agents, streaming trace, logs, approvals, daemon vitals |
| `synapse daemon run\|start\|stop\|status` | run the daemon (foreground) or manage the service |
| `synapse env set\|list\|rm` | manage an agent's env vars (values → OS keyring, names only to the cloud) |
| `synapse plugin search\|install\|list\|remove` | provision capabilities (browser-use, terminal-use, MCP servers) on this host |
| `synapse agent attach\|detach\|capabilities` | select which provisioned capabilities an agent may use |
| `synapse version` / `synapse health` | version + a local health snapshot |

## What runs on the machine (not the cloud)

- **Execution** — API and CLI agents run in supervised, resource-capped processes with a
  scrubbed environment; CLI token/cost accounting via `ccusage`.
- **On-device guardrails** — a two-layer streaming filter: **Layer A** redacts secrets/PII
  (regex + entropy + optional Presidio) into stable salted tokens; **Layer B** detects and
  neutralizes prompt-injection / jailbreak attempts. Both run *before* any byte is uploaded.
- **Ruleset engine** — per-agent command blockers, write-path guards, network allow-lists,
  capability gating, and cost/tool-call caps. Enforced by the daemon, not the model.
- **HITL gates** — sensitive actions pause the run for an approve/deny decision (Web UI,
  Slack/Discord/Email, or the local TUI).
- **Durable execution** — long runs are checkpointed to a local SQLite write-ahead journal
  and resumed from the last consistent step after a crash or network blip; checkpoints sync
  to the cloud E2E-encrypted (org recovery key) so a run survives total local loss.
- **Agent memory** — every agent gets a persistent, local-first memory store (SQLite by
  default; optional vector backend), redacted before any sync.

## Architecture (one line)

A single asyncio process: a dual-channel WebSocket client (control + telemetry,
daemon-initiated so **no inbound port is ever opened**) drives a command router, an agent
runtime (API + CLI adapters), the guardrail middleware, the ruleset engine, a scheduler
(APScheduler), a local SQLite store, a plugin runtime, and a Textual TUI.

See [`docs/tui-daemon.md`](../docs/tui-daemon.md) for the full design and
[`docs/integration.md`](../docs/integration.md) for how the daemon, cloud, and Web UI form
one system.
