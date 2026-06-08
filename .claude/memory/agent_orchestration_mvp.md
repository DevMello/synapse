# Agent Orchestration MVP (Feature 1, §2) — feat/agent-orchestration

PR #27 (OPEN, not merged — high-risk experimental). Implements the **run_agent path** of
possible-features §2 end-to-end. Built directly by the coordinator (worktree subagents can't
run shell here — see [[web_supabase_migration]] /batch note).

**What it does:** an agent runs another agent **on its own daemon**, gated by a cloud-signed,
attenuated **grant** the daemon verifies + enforces **locally** (ed25519), with lineage + async
audit. D1 (daemon-local), D3 (local-enforce + async audit), §2.5 (no-escalation) honored.

**Schema:** migration `0015_agent_orchestration` (applied to live `gpxfylwhwdsswbgicgby`):
`agent_orchestration_grants` (signed), `agent_identities`, `runs` += initiator/
initiator_agent_id/root_run_id/parent_run_id/depth. RLS: members read; grants service-role-write.

**Cloud** (`synapse_cloud/`): `orchestration_crypto.py` (ed25519 sign over canonical grant
`core` — sorted-key compact JSON, delivered verbatim so the daemon hashes identical bytes;
key from `settings.grant_signing_key`, deterministic dev key when unset). `routers/
orchestration.py`: mint(sign+push `orchestration.grant`)/list/revoke(`grant.revoke`+
`orchestration.halt`); `@on_daemon_message("agent.orchestrate")` → audit + child-run lineage
upsert. 6 tests in `tools/tests/test_orchestration.py`.

**Daemon** (`synapse_worker/`): `orchestrator/broker.py` `authorize()` (the security core —
verify sig+expiry+same-daemon+verb+target+depth+no-escalation; trusted key from
`settings.grant_public_key`, NOT the key delivered with the grant). `orchestrator/mcp_server.py`
(`orchestrator.*` tools; run_agent full, create/edit→REQUIRE_HITL). `runner.py` run_agent flow.
`commands/orchestrator.py` (grant cache/revoke/halt). `store.py` += orchestration_grants +
orchestration_lineage tables. 14 tests in `tools/tests/worker/test_orchestrator.py`.

**Web** (`synapse_web/`): `api/client.ts` (REST to the FastAPI signing endpoint via
`VITE_API_BASE` + supabase session JWT — mint/revoke can't be a direct Supabase insert since the
grant is signed server-side). grants + lineage query/adapters; Agent Detail **Orchestration**
tab (mint w/ elevated consent, grants list + revoke, lineage tree). Build green; live render OK.

**Verified:** 6 cloud + 14 daemon tests pass; web build green; tab renders live no console errors.

**Gotchas:**
- The grant `core` (signed subset) is built once at mint and delivered verbatim; the daemon
  verifies the delivered core (doesn't re-derive) so byte-match is trivial. `broker.canonical_bytes`
  MUST stay identical to `orchestration_crypto.canonical_bytes`.
- Daemon `@on_command` registration is a one-time import side-effect; conftest `clear_handlers()`
  wipes it each test → in tests, **call the handler functions directly**, don't rely on re-import.
- This env is **Python 3.10.9**; the daemon targets 3.11+, so TOML/manifest tests (foundation/
  runtime/plugins/checkpoint/auth) fail on `tomllib unavailable` — PRE-EXISTING, not orchestration.
- `aiosqlite` had to be pip-installed for the worker suite here.

**Deferred (post-MVP):** create/edit-HITL in Approvals, anomaly orchestration-rate auto-trip,
fan-out concurrency, cycle detection, top-level Runs lineage column, `orchestrator` capability
auto-wiring into the live runtime (the MCP server exists + is tested but isn't yet bound per-run
by the engine).
