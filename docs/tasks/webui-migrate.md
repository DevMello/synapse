# Task: Migrate the Web UI from hardcoded mock data to Supabase

**Goal.** Replace the typed mock fleet that currently backs every Web UI screen with
live data from the Supabase project, with **zero changes to the screens themselves**.
The migration lands almost entirely behind one seam (`src/api/queries.ts`), plus a small
additive schema migration, a row→view-model adapter layer, a seed script, and Realtime
wiring.

This document is the implementation plan: what to change, in what order, and which
schema gaps to close first.

---

## 1. Where the data lives today

The Web UI renders **entirely** from one file:

- [`synapse_web/src/data/mock.ts`](../../synapse_web/src/data/mock.ts) — the typed "busy
  fleet": `ORG`, `daemons`, `agents`, `runs`, `approvals`, `alerts`, `envVars`, `memory`,
  `logLines`, `skills`, `versions`, `templates`, `PROMPT`, `traceLines`, `CAP_DEFS`.

Screens **never import `mock.ts` directly**. They go through TanStack Query hooks in:

- [`synapse_web/src/api/queries.ts`](../../synapse_web/src/api/queries.ts) — `useOrg`,
  `useDaemons`, `useDaemon`, `useAgents`, `useAgent`, `useRuns`, `useApprovals`,
  `useAlerts`, `useEnvVars`, `useMemory`, `useLogLines`, `useSkills`, `useVersions`,
  `useTemplates`, `usePrompt`, `useTraceLines`. Each currently resolves a mock value
  through `mockQuery()` (a `Promise.resolve`).

The Supabase client already exists as a stub:

- [`synapse_web/src/lib/supabase.ts`](../../synapse_web/src/lib/supabase.ts) — builds a
  real client when `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` are set, otherwise
  `null` (and `isSupabaseConfigured === false`). The app silently runs on mock until the
  project is configured.

The domain types every screen consumes:

- [`synapse_web/src/types.ts`](../../synapse_web/src/types.ts) — `Org`, `Daemon`, `Agent`,
  `Run`, `Approval`, `Alert`, `EnvVar`, `MemoryEntry`, `LogLine`, `Skill`, `Version`,
  `Template`, `TraceLine`, `Capability`, etc.

**Implication:** the migration is concentrated. `queries.ts` is the single swap point.
Screens, types, and components do not change (except a few enum-label helpers).

---

## 2. Where the data should live — the schema already exists

The Supabase schema is **already written** under
[`tools/supabase/migrations/`](../../tools/supabase/migrations/) (9 migrations,
applied 2026-06-01). It is RLS-scoped by `org_id` via the JWT, exactly as
[`docs/web-ui.md` §2](../web-ui.md) prescribes (browser → Supabase Auth/Realtime/data API
directly; slow config via the data API + Cloud Backend REST, fast telemetry via Realtime).

Tables that map cleanly to the mock shapes:

| Mock export (`mock.ts`) | UI type | Backing table(s) | Migration |
|---|---|---|---|
| `ORG` | `Org` | `organizations` (+ current user for operator/initials) | 0002 |
| `daemons` | `Daemon` | `daemons`, `daemon_presence`, `metrics` (cpu/mem/heartbeat) | 0002, 0006, 0007 |
| `agents` | `Agent` | `agents`, `agent_versions`, `metric_rollups` (spend/runs/errRate) | 0004, 0007 |
| `versions` | `Version` | `agent_versions` | 0004 |
| `PROMPT` | `string` | `agent_versions.prompt` (current version) | 0004 |
| `runs` | `Run` | `runs` (agent name denormalized via join) | 0004 |
| `approvals` | `Approval` | `hitl_requests` | 0005 |
| `alerts` | `Alert` | `anomaly_events` | 0006 |
| `envVars` | `EnvVar` | `env_var_refs` (metadata only) | 0005 |
| `memory` | `MemoryEntry` | `agent_memory`, `agent_memory_rollups` | 0005 |
| `logLines` | `LogLine` | `logs` (partitioned) | 0007 |
| `traceLines` | `TraceLine` | `reasoning_traces` (partitioned) | 0007 |
| `templates` | `Template` | `marketplace_listings` (kind `agent`) + a built-in "Blank" | 0006 |
| `CAP_DEFS` + per-daemon state | `Capability` | `plugins`, `daemon_capabilities`, `agent_capabilities` | 0006 |
| `skills` | `Skill` | **gap — see §3** | — |

RLS is already enabled (migration 0008/0009): authenticated members `select` any
org-scoped row where `org_id ∈ user_org_ids()`; `operator+` may write. Global catalogs
(`plugins`, `marketplace_listings`) are readable by any authenticated user. **No RLS work
is required for read paths** — the anon key + a signed-in session is sufficient.

---

## 3. Schema gaps to close (one additive migration: `0010`)

The schema is ~90% sufficient. The mock carries a handful of fields the tables don't yet
hold. Create **one new migration**
`tools/supabase/migrations/<ts>_0010_web_ui_view_fields.sql` (additive only — no
destructive changes; existing data unaffected). Apply via the Supabase MCP
`apply_migration` (remote) or `supabase db push` (local stack).

### 3.1 Organization plan + presentation

`Org` needs `plan` ("Team"). `operator`/`initials` are **derived from the signed-in user**
(`users.display_name`), not stored on the org.

```sql
-- store plan in the existing settings jsonb (no column needed):
--   organizations.settings->>'plan'
-- Backfill existing rows:
update organizations set settings = jsonb_set(settings, '{plan}', '"Team"', true)
  where settings->>'plan' is null;
```

No DDL — use the existing `settings` jsonb. The adapter reads `settings->>'plan'`.

### 3.2 Agent engine + model + display type

`Agent` shows `engine` ("Claude Code", "Codex", "Gemini CLI", "API"), `model`
("claude-sonnet-4"), and a display `type` ("CLI tool" / "API model"). The DB has
`agents.type` as enum `('api','cli')` only. `engine`/`model` belong to the **current
version's config**:

```sql
-- agent_versions.config jsonb already exists; standardize the keys:
--   config->>'engine'   e.g. 'Claude Code'
--   config->>'model'    e.g. 'claude-sonnet-4'
```

No DDL. Adapter maps `agents.type` (`cli`→"CLI tool", `api`→"API model") and reads
`engine`/`model` from the current `agent_versions.config`. Also map
`agent_status` (`active`/`paused`/`archived`) → the UI's `AgentStatus`
(`running`/`idle`/`passed`/`offline`); the live running/idle distinction comes from
whether the agent has an in-flight `run` and whether its daemon is online (see §5 adapter
notes).

### 3.3 Non-secret env var values

`EnvVar` shows a plaintext `value` for **non-secret** vars (`LOG_LEVEL=info`).
`env_var_refs` deliberately stores **metadata only** (secrets are E2E write-only to the
daemon, per web-ui.md §4.8). Add a nullable plaintext column used **only** when `secret`
is false:

```sql
alter table env_var_refs
  add column secret      boolean not null default true,
  add column value_plain text;            -- non-null ONLY when secret = false
alter table env_var_refs
  add constraint env_var_plain_only_when_not_secret
  check (secret or value_plain is null);
```

Adapter: `secret = env_var_refs.secret`; `value = secret ? undefined : value_plain`;
`origin` maps `ui`→"cloud", `local`→"local"; `by`/`updated` from `updated_by`/`updated_at`.

### 3.4 HITL severity

`Approval.severity` is `'block' | 'require-approval'`. `hitl_requests` has no severity
column (it carries `action` + `context` jsonb). Add it:

```sql
create type hitl_severity as enum ('block','require-approval');
alter table hitl_requests add column severity hitl_severity not null default 'require-approval';
```

Adapter pulls `daemon` name via join on `daemon_id`, `command`/`reason`/`context` out of
the `context` jsonb (keys: `command`, `reason`, `context_label`).

### 3.5 Alert presentation fields

`Alert` shows `type`, `icon`, `title`, `detail`. `anomaly_events` has `detector`,
`severity`, `metric`, `baseline`, `observed`, `detail` (jsonb). Map without DDL:

- `type`  ← `detector` (`'cost_spike'`→`'cost'`, `'prompt_injection'`→`'prompt-injection'`, `'daemon_offline'`→`'offline'`)
- `icon`  ← derived in the adapter from `type` (`cost`→`trending-up`, `offline`→`wifi-off`, `prompt-injection`→`shield-alert`)
- `title` ← `detail->>'title'` (write a human title when the detector fires) or composed in adapter
- `detail`← `detail->>'message'`
- `sev`   ← `anomaly_severity` (`warning`→"warn", `info`→"info", `critical`→"warn")

Optionally add `title text` and `message text` columns to `anomaly_events` if you prefer
not to compose strings in the adapter. Recommended: **compose in the adapter** (zero DDL).

### 3.6 Skills (the one real gap)

`mock.skills` (`review-checklist`, `security-scan`, `win-codesign`) has **no backing
table**. Skills are agent-attached workspace capabilities. Two options:

- **(A) Reuse `agent_capabilities`** with `kind = 'workspace'` (capability_kind already has
  `'workspace'`). Skill `name`/`scope`/`size` live in the linked `daemon_capabilities`
  (`exposed_tools`/`args`). Lowest-cost; no DDL.
- **(B) Dedicated table** if skills become first-class:

```sql
create table agent_skills (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  name text not null,
  scope text,                       -- 'all platforms' | 'macOS · Linux' | 'Windows'
  bytes int not null default 0,
  created_at timestamptz not null default now()
);
create index on agent_skills (agent_id);
-- add 'agent_skills' to the org_scoped[] array in the RLS migration pattern (§4)
```

**Recommendation: (B)** — it's the only table the schema is genuinely missing, the UI's
Editor/Skills surface treats them as first-class, and the RLS pattern extends trivially.

### 3.7 Derived daemon runtime (cpu/mem/uptime/heartbeat/activeRuns)

These are **telemetry-derived**, not base-table columns:

- `cpu`, `mem` ← latest `metrics` rows (`name in ('cpu_pct','mem_pct')`) for the daemon.
- `activeRuns` ← `count(runs where daemon_id = d.id and status = 'running')`.
- `uptime` ← rolling % from `daemon_presence` heartbeat history / `metric_rollups`.
- `heartbeat[]` ← last 12 presence buckets (1 = alive, 0 = missed) from `daemon_presence`
  history or a `metric_rollups` bucket. If no history source exists yet, the adapter may
  emit a flat `[1,1,…]` for online daemons until rollups populate.
- `lastSeen` ← relative-time format of `daemons.last_seen`.

No DDL; provide a Postgres **view or RPC** `daemon_overview` that left-joins presence +
the latest metrics so the UI fetches one row per daemon (see §4).

### 3.8 Agent rollup stats (spendToday/runsTotal/errRate/tokensToday/lastRun/nextRun)

Also derived:

- `spendToday`, `tokensToday` ← `sum` over today's `runs` (or `metric_rollups` daily
  bucket) for the agent.
- `runsTotal` ← `count(runs where agent_id = a.id)`.
- `errRate` ← `failed / total` over a window.
- `lastRun` ← `max(runs.started_at)`; `nextRun` ← next `schedules` fire time or
  `'on webhook'` if a `webhooks` row exists, else `'manual'`.

Expose via an `agent_overview` view/RPC (§4) so the Agents list is one query, not N+1.

---

## 4. Database-side helpers (views + Realtime publication)

Add to migration `0010` (or a sibling `0011`):

1. **`agent_overview` view** — `agents` ⋈ current `agent_versions` (engine/model/prompt) ⋈
   aggregated `runs`/`metric_rollups` (spend/tokens/runsTotal/errRate/lastRun) ⋈
   `schedules`/`webhooks` (nextRun). One row per agent. Inherits RLS from base tables
   (define as `security_invoker = true` so the caller's RLS applies).
2. **`daemon_overview` view** — `daemons` ⋈ `daemon_presence` ⋈ latest `metrics`
   (cpu/mem) ⋈ active-run count. One row per daemon. `security_invoker = true`.
3. **Realtime publication** — add the live tables to `supabase_realtime` so the UI's
   Realtime subscriptions (web-ui.md §5) deliver patches:

```sql
alter publication supabase_realtime add table runs;
alter publication supabase_realtime add table hitl_requests;
alter publication supabase_realtime add table anomaly_events;
alter publication supabase_realtime add table logs;
alter publication supabase_realtime add table reasoning_traces;
alter publication supabase_realtime add table daemon_presence;
-- (RLS still gates what each subscriber actually receives)
```

> ⚠️ `security_invoker` views require Postgres 15+ (Supabase default). Verify with the MCP
> `list_extensions` / project info before relying on it; otherwise gate the views behind a
> `security definer` RPC that re-checks `user_org_ids()`.

---

## 5. Client-side migration (the core of the work)

### 5.1 Generate types

Run the Supabase MCP `generate_typescript_types` (or
`supabase gen types typescript`) and write the result to
`synapse_web/src/lib/database.types.ts`. Type the client:
`createClient<Database>(url, anonKey)` in `src/lib/supabase.ts`.

### 5.2 Add an adapter layer (DB row → UI view model)

The DB stores **timestamps, enums, and normalized rows**; the UI types expect
**display strings** ("2 min ago", "CLI tool", `heartbeat[]`). Do **not** change `types.ts`.
Instead add `synapse_web/src/api/adapters.ts` with pure mappers:

- `toOrg(orgRow, userRow)` → `Org` (initials from display_name, plan from settings).
- `toDaemon(daemonOverviewRow)` → `Daemon` (relative-time `lastSeen`, status `revoked`→
  treat as offline for the UI's two-state `DaemonStatus`).
- `toAgent(agentOverviewRow)` → `Agent` (enum→label, status derivation, rollup fields).
- `toRun`, `toApproval`, `toAlert`, `toEnvVar`, `toMemoryEntry`, `toLogLine`,
  `toVersion`, `toTemplate`, `toSkill`, `toTraceLine`.
- A shared `relativeTime(ts)` helper (e.g. `date-fns/formatDistanceToNowStrict`) — add
  `date-fns` to `synapse_web/package.json` if not present.

Keep ID shape stable: the mock uses string ids like `a-prr`/`d-mbp`; the DB uses uuids.
Screens treat ids as opaque strings, so uuids are a drop-in. (The seed in §6 keeps the
human ids only as `name`s, not ids.)

### 5.3 Rewrite `queries.ts` hook by hook

For each hook, branch on `isSupabaseConfigured`: when false, keep the existing
`mockQuery(...)` path (so the app still boots with no project — useful for design work and
CI); when true, run the real query and map through the adapter. Pattern:

```ts
export function useDaemons(): UseQueryResult<Daemon[]> {
  return useQuery({
    queryKey: ["daemons"],
    queryFn: async () => {
      if (!supabase) return mock.daemons;                      // fallback
      const { data, error } = await supabase.from("daemon_overview").select("*");
      if (error) throw error;
      return data.map(toDaemon);
    },
  });
}
```

Per-hook source of truth:

| Hook | Query |
|---|---|
| `useOrg` | `organizations` (the user's org) + `users` (current) → `toOrg` |
| `useDaemons` / `useDaemon` | `daemon_overview` view |
| `useAgents` / `useAgent` | `agent_overview` view |
| `useRuns` | `runs` ⋈ `agents` (denormalize agent name), order `created_at desc`, limit |
| `useApprovals` | `hitl_requests` where `status='pending'` ⋈ `agents`/`daemons` |
| `useAlerts` | `anomaly_events` order `created_at desc` |
| `useEnvVars` | `env_var_refs` for the agent (Environment tab) |
| `useMemory` | `agent_memory` for the agent (+ `agent_memory_rollups` for footprint) |
| `useLogLines` | `logs` for the run/agent, order `created_at` |
| `useSkills` | `agent_skills` (§3.6) for the agent |
| `useVersions` | `agent_versions` for the agent, order `version desc` |
| `usePrompt` | `agent_versions.prompt` of the agent's `current_version` |
| `useTemplates` | `marketplace_listings` where `kind='agent'` + a synthetic "Blank" |
| `useTraceLines` | `reasoning_traces` for the run, order `seq` |

> **Scope note:** `useEnvVars`, `useMemory`, `useSkills`, `useVersions`, `usePrompt`,
> `useTraceLines`, `useLogLines` are **per-agent/per-run** in reality but take no argument
> today (they resolve the single mock agent). Add the `agentId`/`runId` parameter when
> wiring them, threading it from the Agent Detail route param. This is the only screen-
> adjacent change and is mechanical.

Keep the synchronous `export const data = mock;` accessor working for any component that
cross-references the snapshot, **or** replace its few call sites with hook reads. Grep for
`api/queries` `.data` usage before removing it.

### 5.4 Realtime (live-by-default, web-ui.md §5)

After reads work, add subscriptions so the UI stays live without refetch. Create
`synapse_web/src/api/realtime.ts`: on mount of a live view, `supabase.channel(...)` →
`postgres_changes` on the relevant table filtered by `org_id`, and on each event
`queryClient.setQueryData([...], patch)` or `invalidateQueries`. Start with `runs`,
`hitl_requests`, `anomaly_events`, `daemon_presence`. Resubscribe on reconnect
(`supabase-js` handles the socket; re-establish channels in an effect).

### 5.5 Auth

The data API and Realtime require a signed-in session (RLS keys off `auth.uid()`).
web-ui.md §1/§3 puts **Supabase Auth** + the **Connect-a-device** flow first. Ensure a
session exists before the hooks run: add a minimal auth gate (sign-in screen / existing
session check via `supabase.auth.getSession()`) ahead of the app shell. Without a session,
RLS returns **zero rows** (not an error) — the app would look empty, which is the tell-tale
sign auth wasn't wired.

---

## 6. Seed data (so a fresh project isn't empty)

The mock fleet is also useful as **seed data** for a demo/staging org. Port `mock.ts` into
`tools/supabase/seed.sql` (or a `supabase/seed.sql` consumed by `supabase db reset`):

- one `organizations` row (`northwind`, `settings.plan = 'Team'`),
- a `users` + `memberships` row for the demo operator (Avery Koss, `owner`),
- the 4 `daemons`, 6 `agents` (+ `agent_versions` carrying `PROMPT`/engine/model),
  `schedules`, the 8 `runs`, 3 `hitl_requests`, 3 `anomaly_events`, env var refs, memory
  entries, versions, plugins/capabilities, marketplace listings, skills.

This lets `supabase db reset` reproduce today's exact UI against a real backend, which is
the cleanest way to verify the migration screen-by-screen (the rendered UI should be
pixel-identical to the mock build).

---

## 7. Order of operations

1. **Schema** — write + apply migration `0010` (§3 fields, §4 views + Realtime publication)
   and, if chosen, the `agent_skills` table. Use the Supabase MCP (`apply_migration`,
   `list_tables`, `get_advisors` to catch RLS/index warnings) or the local CLI.
2. **Seed** — load `seed.sql` into a dev/staging project so there's data to fetch.
3. **Types** — `generate_typescript_types` → `database.types.ts`; type the client.
4. **Adapters** — `src/api/adapters.ts` with the pure row→view-model mappers + `relativeTime`.
5. **Reads** — rewrite `queries.ts` hook by hook (keep the mock fallback branch). Add the
   `agentId`/`runId` params to the per-agent hooks and thread them from the route.
6. **Auth gate** — ensure a Supabase session before the shell mounts.
7. **Realtime** — subscriptions for `runs`/`hitl_requests`/`anomaly_events`/`daemon_presence`.
8. **Verify** — `.env` with `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`, then
   `npm run build` (strict tsc must stay green) and a dev-server render check; compare each
   screen against the seeded fleet. Run `get_advisors` once more for security/perf lint.
9. **Cleanup** — once every hook is live and verified, `mock.ts` can be demoted to
   test-fixture / Storybook use (keep it; the `isSupabaseConfigured === false` fallback and
   CI/design workflows still rely on it).

---

## 8. Risks & gotchas

- **Empty UI, no error** — the #1 symptom of missing auth or wrong `org_id` in the JWT.
  RLS returns zero rows silently. Verify `supabase.auth.getSession()` and that the user has
  a `memberships` row before debugging queries.
- **`security_invoker` views** need PG15+; otherwise the view runs as owner and **bypasses
  RLS** (data leak across orgs). Confirm the Postgres version or use `security definer` RPCs
  that re-filter on `user_org_ids()`.
- **Relative-time drift** — mock strings ("2 min ago") are frozen; real timestamps move.
  Format in the adapter and let TanStack's `staleTime`/Realtime keep them fresh; don't store
  formatted strings.
- **Enum mismatches** — `agent_type` (`api`/`cli`) ≠ UI labels; `run_status` has 8 values
  vs the UI's 4; `daemon_status` has `revoked` the UI doesn't model. All handled in the
  adapter — centralize the maps there, never in screens.
- **N+1 on lists** — fetch via the `agent_overview`/`daemon_overview` views, not per-row
  joins from the client.
- **Secrets** — never select secret env var values; `env_var_refs` holds metadata only and
  `value_plain` is constrained to non-secret rows (§3.3). Keep the E2E-to-daemon write path
  out of this migration (it already exists per the daemon `e2e_public_key` integration).
- **Realtime volume** — `logs`/`reasoning_traces` are high-frequency; subscribe only on the
  open Logs/Trace view and unsubscribe on unmount, or poll those rather than streaming.

---

## 9. Acceptance

- `npm run build` green (strict tsc) with `VITE_SUPABASE_*` set and unset (fallback intact).
- Every screen that renders mock data today renders the **seeded** equivalent from Supabase,
  RLS-gated to the signed-in org.
- Live updates: triggering a new `run` / `hitl_request` row reflects in the UI without a
  manual refresh.
- `get_advisors` reports no new security (RLS) findings.
