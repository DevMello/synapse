---
name: tui-daemon-build
description: TUI Worker Daemon is implemented (synapse_worker/, 16 units on master) — build conventions, seams, and test strategy for extending it
metadata:
  type: project
---

The **TUI Worker Daemon** (`synapse_worker/`) is now implemented on `master` — no longer
docs-only. Built as a committed **foundation + 16 parallel feature units** (run in 8
batches of 2 via worktree subagents, merged conflict-free), mirroring how
[[cloud-backend-build]] was built. ~92 modules, 282 worker tests; `python -c "from
synapse_worker.app import build_daemon; build_daemon()"` assembles 18 handled commands, 5
background services, both guardrail filters, and the RulesetEngine. PyPI name
`synapse-worker`; console script `synapse`.

**Why:** executed the `/batch docs/tui-daemon.md` plan; the daemon speaks the Cloud
Backend's EXISTING JSON wire protocol exactly (do not change it) — the cloud is the
contract (`synapse_cloud/ws_hub`, `message_registry.py`, the routers' command sends).

**How to apply — conventions any new daemon feature MUST follow (these keep changes
conflict-free; same spirit as the cloud build):**
- **Command handlers auto-discover**: drop a `synapse_worker/commands/*.py` using
  `@on_command("<type>")` from `synapse_worker.router`. `app.build_daemon()` pkgutil-imports
  the package. NEVER edit `app.py` or `router.py`.
- **Long-running services auto-discover**: `@register_service("name")` (from
  `synapse_worker.services`) on a factory `(daemon)->obj` with `async run()/stop()`;
  `run_daemon()` gathers them. (connection, scheduler, health, memory_sync, checkpoint_recovery.)
- **Upstream frames** (daemon→cloud) go ONLY through `get_uplink().send(msg_type, payload,
  *, channel="control"|"telemetry")` — never open a socket (Unit 1/`connection/` owns the
  real `WebSocketUplink`, installed via `set_uplink()` at run()). The uplink durably enqueues
  to the SQLite `outbound_queue` FIRST (row seq == wire seq), then flushes; cloud acks by seq.
- **CLI subcommands**: new `synapse_worker/cli/cmd_*.py` exposing `register(app)`; `cli/main.py`
  auto-discovers them. **TUI panes**: `@register_pane` + a module under `tui/panes/`.
- **Guardrail/ruleset/keystore/uplink are SEAMS with permissive/in-memory defaults**
  (`filtering/base.py` pass-through chain, `ruleset/base.py` PermissiveRuleset,
  `crypto.py` InMemoryKeystore) so the daemon imports clean with any subset of units. Real
  impls register at import via a `commands/*_boot.py` (redaction, injection, ruleset, auth keystore).
- **All durable state via `store.py`** (`get_store()`, SQLite WAL). Schema is in `store.py`
  `_SCHEMA` (agents, schedules, outbound_queue, run_history, hitl_state, checkpoints, memory
  + memory_journal, env_names, capabilities, agent_capabilities, idempotency_seen, kv). Add
  tables additively in your own module (`CREATE TABLE IF NOT EXISTS`) — do NOT rewrite `_SCHEMA`.
- **Wire envelope is `wire.py`** — the single source of truth, matched to the cloud:
  cloud→daemon `{"type":"command","seq","command_type","payload","idempotency_key"}` → ack
  `{"type":"ack","ack":seq}`; daemon→cloud `{"type":<msg>,"seq","payload"}`; heartbeat/ping.

**Key wire facts learned (cloud is authoritative):** telemetry trace = `telemetry.trace`
{run_id,agent_id,role,content_redacted}; metrics `telemetry.metric` {name,value}; run end
`run.finished` {run_id,status(succeeded|failed|cancelled),cost_usd,tokens_in,tokens_out};
checkpoint `run.checkpoint` {run_id,seq,step_cursor,status,cost_so_far_usd,payload_b64
(E2E-sealed)}; `hitl.request`→correlate the cloud's `hitl.resolve` {hitl_id,run_id,decision}
by **run_id** (daemon doesn't know the cloud id at request time); `env.set` carries only
{name,ciphertext} (agent_id is in the idempotency_key `env.set:{agent}:{name}`); capability
status `capability.status` {daemon_capability_id,status,exposed_tools}; memory `memory.delta`
(telemetry, redacted) / `memory.sync` (one op/cmd). `daemon.update`/`daemon.ping`/`skill.install`
are handled defensively but the cloud doesn't currently push them.

**Integration hardening (2026-06-02, PR #1):** the daemon now sends `daemon.register`
{name,tags,platform,version} on control-channel connect (cloud handler in
`routers/daemons.py` updates the daemons row, org+id scoped, partial-frame safe) — this
is the §2.3 "registering on connect" step. The cloud now also handles the daemon's
`run.recover.ack` {run_id,agent_id,plan} (`routers/recovery.py`, audit-only). Fixed a
daemon revocation **hot-loop**: on a 4401 where token refresh fails, `manager._channel_loop`
must back off (not `continue`) — `_handle_token_expiry()` returns bool success now. `client_cert`
is wired into the WS TLS ctx (mTLS). Live loop verified by `tools/tests/live_cloud_smoke`.

**Tests**: self-contained under `tests/worker/` (NO Supabase, NO network) with their own
`conftest.py` — tmp `~/.synapse` via `SYNAPSE_HOME`, `SYNAPSE_WORKER_ENV=test`, all
singletons reset per test, plus a **`MockCloud` WS hub** fixture (`tools/tests/worker/mock_cloud.py`)
speaking the cloud frames. Tests + supabase migrations live under **`tools/`** (`tools/tests/`,
`tools/supabase/migrations/`; pytest `testpaths=["tools/tests"]`). Run
`.venv/Scripts/python.exe -m pytest tools/tests/worker/` (283 pass).
**LIVE end-to-end**: `python -m tools.tests.live_cloud_smoke` boots the REAL cloud (uvicorn + real
Supabase) and drives the actual daemon stack over live WebSockets — verifies presence/online,
cloud→daemon command+ack, and daemon→cloud upstream persisted in Supabase (PASS, exits clean).
It caught a bug MockCloud couldn't: the health emitter shipped the whole snapshot dict as a
`telemetry.metric` value, but cloud `metrics.value` is `double precision` (Postgres 22P02) —
`telemetry.metric` values MUST be numeric; `emit_snapshot` now sends scalar per-field metrics
only (full snapshot rides `daemon.pong`). Also: `hitl_requests.agent_id`/`run_id` are uuid
columns — daemon-supplied ids there must be valid UUIDs. The
**venv has no pip** — install with `uv pip install --python .venv/Scripts/python.exe -e
".[worker,dev]"` (UV_LINK_MODE=copy). venv Python is 3.11; daemon targets 3.11+.

**Crypto/keychain**: keystore service `"synapse:daemon"`, keys `access_token`/`refresh_token`/
`daemon_private_key`/`daemon_public_key`/`org_recovery_private_key`/`org_recovery_public_key`.
Env values → keyring `synapse:agent:{id}:env` / `synapse:shared:env`. X25519 sealed box
(`crypto.seal/seal_open`). Gotchas fixed during build: `paths.secure_write` needs `O_BINARY`
on Windows (CRLF corruption); never name a Textual `Widget` helper `_render` (clobbers an
internal); don't cancel `self._task` in a Textual `on_unmount`. See [[project-overview]].
