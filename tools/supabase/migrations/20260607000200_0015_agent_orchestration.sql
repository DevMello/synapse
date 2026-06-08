-- 0015 — Agent Orchestration (possible-features §2). An agent may run/create/edit
-- other agents on its OWN daemon, gated by a cloud-signed, attenuated grant the daemon
-- verifies + enforces locally. This migration adds the grant + identity tables and the
-- run lineage columns. New audit_events action kinds need no DDL (action is text).

-- ── agent_identities — per-agent machine identity (ed25519 pubkey; future use) ──
create table agent_identities (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  public_key text,                                  -- base64 ed25519 public key
  created_at timestamptz not null default now(),
  rotated_at timestamptz,
  unique (agent_id)
);
create index on agent_identities (org_id);

-- ── agent_orchestration_grants — signed, attenuated grant (minted + signed cloud-
-- side; cached + verified offline on the daemon). Only the cloud (service role)
-- writes these because the signature must be minted server-side. ─────────────────
create table agent_orchestration_grants (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,        -- the orchestrator agent
  daemon_id uuid not null references daemons(id) on delete cascade,      -- D1: same-daemon only
  granted_by uuid references users(id) on delete set null,               -- grant ⊆ this human's authority
  verbs text[] not null default '{run}',                                 -- run | create | edit
  target_allow text[] not null default '{}',                             -- agent ids / 'tag:...'
  max_depth int not null default 3,
  max_fan_out int not null default 5,
  tree_budget_usd numeric(12,6) not null default 10.0,                   -- shared across the whole tree
  protected_fields text[] not null default '{rulesets,blockers,env,capabilities,grants}',
  key_id text,                                                           -- which cloud signing key
  signature text,                                                        -- base64 ed25519 over canonical payload
  expires_at timestamptz not null,
  revoked_at timestamptz,                                                -- null = active
  created_at timestamptz not null default now()
);
create index on agent_orchestration_grants (org_id);
create index on agent_orchestration_grants (agent_id);
create index on agent_orchestration_grants (daemon_id);

-- ── runs lineage (initiator + orchestration tree) ───────────────────────────────
alter table runs
  add column if not exists initiator text not null default 'human',
  add column if not exists initiator_agent_id uuid references agents(id) on delete set null,
  add column if not exists root_run_id uuid,
  add column if not exists parent_run_id uuid,
  add column if not exists depth int not null default 0;
alter table runs
  drop constraint if exists runs_initiator_check;
alter table runs
  add constraint runs_initiator_check
  check (initiator in ('human','schedule','webhook','agent'));
create index if not exists runs_root_run_idx on runs (root_run_id);
create index if not exists runs_parent_run_idx on runs (parent_run_id);

-- ── RLS — members read; grants/identities written server-side (signed) ──────────
alter table agent_identities enable row level security;
create policy agent_identities_sel on agent_identities for select to authenticated
  using (org_id in (select public.user_org_ids()));
-- writes: service role only (no policy for authenticated)

alter table agent_orchestration_grants enable row level security;
create policy aog_sel on agent_orchestration_grants for select to authenticated
  using (org_id in (select public.user_org_ids()));
-- writes: service role only — grants must be minted (signed) through the cloud endpoint
