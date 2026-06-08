# Web UI → Supabase data migration (feat/web-supabase)

**Branch:** `feat/web-supabase` (off main `16888ac`), pushed to origin DevMello/synapse.
HEAD `4119c47`. Final step pending: user opens PR `feat/web-supabase` → `main`.
Design doc: `docs/tasks/webui-migrate.md`.

**What it does:** replaces the Web UI's hardcoded mock fleet (`synapse_web/src/data/mock.ts`)
with live Supabase data, behind the existing hook seam. Every hook now queries Supabase when
`isSupabaseConfigured` (env vars set) and falls back to mock otherwise — so the build stays
green and the app still boots on mock with no env (design/CI). Mock file is retained as the
fallback + fixtures.

**Live Supabase project:** `synapse` = project id `gpxfylwhwdsswbgicgby` (ACTIVE_HEALTHY, PG17),
org `vercel_icfg_AYgZBXhIJsIx5nXMaD88kydl`. Migrations 0010/0011 were applied **directly to
this live project** (user chose live over a dev branch). Anon key/URL NOT in repo; a future
`.env` (VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY) flips the app to live.

**Schema added (additive):**
- `tools/supabase/migrations/..0010_web_ui_view_fields.sql` — `env_var_refs.secret`+`value_plain`
  (+check), `hitl_severity` enum + `hitl_requests.severity`, `agent_skills` table + RLS,
  org `settings.plan` backfill.
- `..0011_web_ui_views_realtime.sql` — `agent_overview` & `daemon_overview` `security_invoker`
  views (engine/model/prompt + run rollups; cpu/mem/active_runs), Realtime publication adds.
  NOTE: partitioned `logs`/`reasoning_traces` publish via their `_default` partitions.

**Client architecture (foundation, commits d573efe/791aa2e):**
- `src/lib/database.types.ts` generated from live; typed client `createClient<Database>`.
- `src/api/queries.ts` is now a **barrel** re-exporting per-domain `src/api/queries/<d>.ts`;
  per-domain `src/api/adapters/<d>.ts` map DB Row → UI type (`src/types.ts` unchanged).
  `src/api/format.ts` `relativeTime`. New `useCapabilityDefs` hook (replaces `data.CAP_DEFS`).
- Per-agent hooks (env/memory/versions/prompt/skills/logs/trace) resolve the id via
  `useCurrentAgent()` internally — tab call sites unchanged.
- `src/lib/queryClient.ts` singleton so `Common.daemonName` reads `["daemons"]` cache sync.
- `src/lib/auth.tsx` `AuthGate` — requires a Supabase session before the shell when configured,
  bypasses in mock mode; mounted in `main.tsx`.
- `src/api/realtime.ts` — `subscribeFleet(qc)` (Dashboard) + `useAgentRealtime(agentId)`
  (AgentDetail) invalidate query cache on postgres_changes.

**Sync `data.*` → hooks converted:** Shell, Common (daemonName via cache), AgentDetail
(useAgent + loading guard), Settings, Connect, agent tabs Overview/Tools/Plugins/Editor
(useDaemon/useCapabilityDefs). Screens already on hooks (Dashboard, Daemons, Runs, Agents,
Alerts, Memory, Environment, Versions, Logs, Analytics…) went live with no change.

**MERGED TO MAIN** via PR #25 (merge commit `9334cc1`), plus follow-up `e6599f8`
(constraint fix + seed + daemonName cache-warm). main builds green.

**Live-data verification DONE** (against project gpxfylwhwdsswbgicgby):
- `tools/supabase/seed.sql` written + applied — reproduces the mock "busy fleet" as real
  rows + a confirmed demo operator **avery@northwind.test / synapse123** (auth.users inserted
  via SQL; must set the token text cols to '' or GoTrue returns "Database error querying
  schema"). Local `synapse_web/.env` (gitignored) holds the URL + anon key.
- Verified in-browser: AuthGate sign-in → Dashboard renders live (3/4 daemons online, spend
  today $8.80 = sum of 8 seeded runs, top agents by engine from agent_versions.config),
  Agent Detail Environment tab (secrets WRITE-ONLY, non-secret LOG_LEVEL/NORTHWIND_ENV values
  shown). Zero console errors. agent_overview/daemon_overview rollups + relativeTime + enum
  maps + RLS all confirmed working end-to-end.

**Bugs found & fixed during verification:**
- migration 0010 `env_var_refs` check was inverted (`secret or value_plain is null` rejected
  non-secret-with-value). Fixed in 0010 + migration `0012`. Adapter `toEnvVar` was correct.
- `Common.daemonName` (sync, reads ["daemons"] cache) showed the raw daemon uuid on a
  deep-linked Agent Detail page (cache cold). Fixed: AgentDetail calls `useDaemons()` to warm it.

Note: demo seed rows + the avery@ auth user now live in the production `synapse` project.

**/batch note:** this was run via /batch. Background worktree subagents are DENIED Bash/
PowerShell in this environment, so all 16 workers blocked at `git merge` (STEP 0) — the
coordinator implemented every unit directly instead. For future parallel work here, worktree
agents can't run git/npm/gh; do the work inline or pre-seed worktrees.

See [[web_ui_build]] for the prior Web UI build.
