# Model Comparison Runs (Feature 3, §10) — feat/model-comparison

Implements possible-features §10 end-to-end — a **human-driven evaluation tool** that runs ONE
agent task across several models in parallel as a **run group** of **draft-mode variants**, then
shows a side-by-side comparison; the human picks a winner that can be re-run live. The lower-risk
sibling of §2 Orchestration ([[agent_orchestration_mvp]]) / §11 Handoff ([[native_handoff_feature]]):
NO new principal, NO unattended action, NO real side effects until a human chooses (E1–E5). §10
graduated to a stub in docs/possible-features.md. Built inline by the coordinator (worktree subagents
can't run shell here — see the /batch note in [[web_supabase_migration]]).

**Decisions (E1–E5):** E1 manual/on-demand only; E2 human picks winner (no judge LLM); E3 draft
mode (read-only tools run; side-effecting + HITL simulated); E4 promote = a fresh live single-model
re-run, not a replay; E5 API agents only in v1.

**Schema:** migration `0020_comparison_runs` **APPLIED to live `gpxfylwhwdsswbgicgby`** (2026-06-13,
via the Supabase MCP `apply_migration`; security advisors show no new issues — run_groups has RLS +
policies). `synapse_web/src/lib/database.types.ts` updated with the run_groups table + the
runs/tool_calls/hitl_requests columns (spliced by hand, NOT a full regenerate: regenerating from live
drops the §11 handoff types because 0017/0018/0019 are still unapplied to live — the repo types are
intentionally ahead of live). `run_groups` (agent_id, daemon_id, input
jsonb, selected_models[], status running/ready_for_review/closed, winner_run_id, total_cost_usd,
group_cost_cap, max_parallel_variants); `runs +=` run_group_id/variant_model/is_winner/mode(normal|
comparison_variant); `tool_calls +=` simulated/proposed_action; `hitl_requests +=` simulated. RLS:
run_groups member read+write (manual/human-driven, like agent_flows). NO signed grant (§10.4).

**Daemon** (`synapse_worker/`): the **agentic tool loop** lives in the rewritten
`runtime/api_adapter.py` (Anthropic tool_use/tool_result + OpenAI tool_calls/role:tool message
threading; bounded by max_tool_calls+1, tools dropped on the last turn to force a text answer;
google/ollama stay single-shot). `runtime/tools.py` = `ToolExecutor` seam + `DefaultToolExecutor`
+ `classify_tool` (read_only|side_effecting|hitl_gated; manifest `[[tools]].blast_radius` wins,
unknown → side_effecting conservative). `RunContext.tool_executor` + a `tool_executor=` param on
`RunEngine.run_agent` inject the shim per-variant. `comparison/draft_shim.py` `DraftToolExecutor`
wraps an inner executor: read-only runs for real, side-effecting/HITL recorded (Layer-A redacted)
+ simulated stub; `DraftCollector` gathers proposed_actions/simulated_hitl/tool_calls.
`comparison/executor.py` `run_group` forks N variants (Semaphore(max_parallel_variants)), clones the
manifest overriding ONLY api.provider/model (§10.3), enforces a group cost cap (hard-stops not-yet-
started variants), persists to `comparison_groups`/`comparison_variants`/`_proposed_actions`/`_sim_hitl`
(appended to store.py `_SCHEMA`), and emits `comparison.variant_finished` / `comparison.group_ready`
tagged with run_group_id/variant_model. `commands/comparison.py` `agent.compare` (launch background)
/ `comparison.cancel`. Variant run ids are real UUIDs so the cloud can persist them into `runs.id`.

**Cloud** (`synapse_cloud/`): `comparison_pricing.py` (static per-Mtok price map + estimate_variant/
estimate_group; unknown model → estimated=False not billed). `routers/comparison.py`: GET
`/agents/{id}/comparison-models` (catalog + per-model estimate + has_credentials from env_var_refs by
daemon, §10.9), POST `/agents/{id}/comparisons` (validate API-only + non-production, create run_groups,
estimate, send `agent.compare`, audit comparison.launched), `/comparisons/{id}/cancel`, `/winner`
(set is_winner + winner_run_id), `/promote` (fresh normal agent.run of the winner, E4). Inbound
`@on_daemon_message("comparison.variant_finished")` upserts the variant run (mode=comparison_variant)
+ tool_calls/hitl rows; `comparison.group_ready` flips status + rolls up total_cost.

**Web** (`synapse_web/`): `types.ts` (RunGroup/ComparisonVariant/AvailableModel/ProposedAction);
`api/queries/comparisons.ts` (REST via apiPost/apiGet + Supabase reads + MOCK store) +
`adapters/comparisons.ts`; barrel `api/queries.ts`. `screens/comparison/CompareLauncher.tsx` (model
multi-select grouped by provider, per-model estimate + running total, cap override, N× confirm),
`ComparisonView.tsx` (per-model columns: output/cost/tokens/latency/tool calls/proposed actions/
"would have paused" markers/errors; sortable summary cheapest/fastest/fewest-interventions; line diff;
winner select → "Run winner for real"; draft-mode caveat banner), `screens/Comparisons.tsx` library,
`screens/agent/tabs/Compare.tsx` (Compare tab, API-only gate), `styles/comparison.css` (`.cmp-*`,
reuses design tokens). `/comparisons` + `/comparisons/:groupId` routes; "Compare" nav under Operate.
The Supabase read path casts the client (`run_groups` not in generated database.types until 0020 is
applied) → MOCK mode is the offline demo, seeded by `screens/comparison/templates.ts`.

**Verified:** 12 daemon (`tools/tests/worker/test_comparison.py`) + 8 cloud unit
(`tools/tests/test_comparison.py`, pricing/estimate + API-only validation, no new-table DB) tests
pass; full worker suite 330+ green (no regression from the adapter/engine changes); cloud + daemon
assemble clean. Web `npm run build` green (Compare/Comparisons/ComparisonView own chunks). Live-verified
in MOCK mode via preview_snapshot: library → group view (3 columns, issue_refund flagged "would pause",
intervention counts) → select winner (column highlights + "Run winner for real" appears) → launcher
(6 models/3 providers, gpt-5-mini disabled no-key, estimate + N× confirm) → launch navigates to new
group. Zero console errors. (preview_screenshot still times out 30s in this env — snapshots only.)

**Code-review fixes applied:** (1) cancel/finish race — `cancel_group` marks `_cancelled` so
`run_group`'s normal completion doesn't clobber the terminal `cancelled` status back to
`ready_for_review` (regression test added); (2) `handle_variant_finished` bails+audits if the group/
agent_id can't be resolved (runs.agent_id is NOT NULL); (3) select_winner clear-winner query narrowed.

**Gotchas:**
- The daemon API adapter was single-shot before this; the agentic loop is NEW. `_post` stays the only
  network seam — tests inject canned multi-turn bodies (no network/keys). Single-shot back-compat: with
  no `[[tools]]`, max_iters=1 (one turn), identical to the old behavior — existing runtime tests pass.
- Migration 0020 is now applied to live + `database.types.ts` carries the comparison tables, so the
  Supabase read path is type-correct (the `sb()` cast in queries/comparisons.ts is now belt-and-braces,
  not load-bearing). LIVE end-to-end over a real daemon still needs the `comparison` capability bound
  per-run by the engine (same deferred wiring as §2's MCP) + DB-integration endpoint tests. To demo
  offline, move `synapse_web/.env` aside (MOCK).
- **Do NOT** run a full `generate_typescript_types` against live and overwrite database.types.ts: live
  lacks 0017/0018/0019, so a clean regenerate DROPS the handoff (`agent_flows`, `runs.hop`, …) types and
  breaks `tsc`. Splice new tables/columns by hand until 0017–0019 are also applied to live.
- `comparison.variant_finished` carries proposed_actions/tool_calls so the cloud can populate
  `tool_calls` rows (simulated/proposed_action) — the web reads those from Supabase for the columns.

**Deferred:** apply 0020 to live + DB-integration endpoint/inbound tests; live model-pinning for the
**promote** path (the re-run currently executes with the agent's configured model; the winning model
is recorded in audit + runs.variant_model but the daemon doesn't yet honor a per-run model override);
provider rate-limit backoff on fan-out; feature-flag/consent + production-exclusion gating at org level
(off-by-default §4); semantic diff/grading beyond the textual line diff.
