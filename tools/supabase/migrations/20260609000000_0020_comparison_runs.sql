-- 0020 — Model Comparison Runs (possible-features §10). A HUMAN launches a one-off
-- "Compare models" run that executes ONE agent task across several models in parallel as
-- a `run_groups` of `comparison_variant` runs. It is a manual evaluation tool (E1): not
-- schedulable, not a new principal, and — by design — performs NO real side effects until
-- a human picks a winner (E3 draft mode). Each variant is an ordinary `runs` row, so the
-- telemetry/cost/tool_call tables are reused as-is; this migration only adds the run-group
-- envelope + a few flags that distinguish a simulated dry-run call from an executed one.
-- New audit_events action kinds ('comparison.launched','winner.selected',
-- 'winner.promoted_live') need no DDL (action is text).

-- ── run_groups — the comparison envelope (§10.10). One row per "Compare models" launch;
-- each selected model becomes a `comparison_variant` run pointing back here. Members
-- read+write within their org (manual/human-driven, like agent_flows — there is no signed
-- grant for comparison; §10.4). ─────────────────────────────────────────────────────────
create table run_groups (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  agent_version int,
  daemon_id uuid references daemons(id) on delete set null,    -- where the variants run
  input jsonb not null default '{}'::jsonb,                    -- the pinned task (§10.3)
  selected_models text[] not null default '{}',               -- the models compared
  status text not null default 'running',                      -- running | ready_for_review | closed
  winner_run_id uuid references runs(id) on delete set null,    -- set when a human picks (§10.7)
  total_cost_usd numeric(12,6) not null default 0,            -- group aggregate (§10.8)
  group_cost_cap numeric(12,6),                                -- hard group cap (null = none)
  max_parallel_variants int not null default 3,                -- §10.4 concurrency bound
  created_by uuid references users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint run_groups_status_check check (status in ('running','ready_for_review','closed'))
);
create index on run_groups (org_id, created_at desc);
create index on run_groups (agent_id, created_at desc);
create index on run_groups (daemon_id);

-- ── runs comparison columns — every variant is a normal run, tagged back to its group and
-- carrying which model produced it. `mode` distinguishes a comparison variant from a normal
-- run (and the later live promotion of the winner is a fresh `normal` run — E4). ──────────
alter table runs
  add column if not exists run_group_id uuid references run_groups(id) on delete cascade,
  add column if not exists variant_model text,
  add column if not exists is_winner boolean not null default false,
  add column if not exists mode text not null default 'normal';
alter table runs
  drop constraint if exists runs_mode_check;
alter table runs
  add constraint runs_mode_check
  check (mode in ('normal','comparison_variant'));
create index if not exists runs_run_group_idx on runs (run_group_id);

-- ── tool_calls draft-mode flags — distinguish a simulated dry-run side effect (the call the
-- model WOULD have made) from a real executed one (§10.5). Read-only calls execute for real
-- (simulated=false, proposed_action=false); side-effecting calls in a comparison are
-- recorded but not executed (simulated=true, proposed_action=true). ───────────────────────
alter table tool_calls
  add column if not exists simulated boolean not null default false,
  add column if not exists proposed_action boolean not null default false;

-- ── hitl_requests draft-mode flag — a "would have paused for approval" marker carries no
-- real gate; it is recorded as a per-model human-intervention data point (§10.5/§10.6). ───
alter table hitl_requests
  add column if not exists simulated boolean not null default false;

-- ── RLS — run_groups are member-authored (read+write own org), like agent_flows. The
-- variant `runs` rows reuse the existing runs RLS (already org-scoped, migration 0008). ───
alter table run_groups enable row level security;
create policy run_groups_sel on run_groups for select to authenticated
  using (org_id in (select public.user_org_ids()));
create policy run_groups_ins on run_groups for insert to authenticated
  with check (org_id in (select public.user_org_ids()));
create policy run_groups_upd on run_groups for update to authenticated
  using (org_id in (select public.user_org_ids()))
  with check (org_id in (select public.user_org_ids()));
create policy run_groups_del on run_groups for delete to authenticated
  using (org_id in (select public.user_org_ids()));
