-- 0010 — Web UI view fields: env-var non-secret value, HITL severity, agent_skills, org plan.
-- Additive only; safe to apply over the existing schema (idempotent guards throughout).

-- ── env_var_refs: secret flag + non-secret plaintext value ───────────────────
-- Secrets stay E2E write-only to the daemon (no value stored). Non-secret vars
-- (e.g. LOG_LEVEL=info) may carry a readable plaintext value for the UI.
alter table env_var_refs
  add column if not exists secret boolean not null default true,
  add column if not exists value_plain text;
alter table env_var_refs
  drop constraint if exists env_var_plain_only_when_not_secret;
alter table env_var_refs
  add constraint env_var_plain_only_when_not_secret
  check (not secret or value_plain is null);

-- ── HITL severity (Approvals queue) ──────────────────────────────────────────
do $$ begin
  if not exists (select 1 from pg_type where typname = 'hitl_severity') then
    create type hitl_severity as enum ('block','require-approval');
  end if;
end $$;
alter table hitl_requests
  add column if not exists severity hitl_severity not null default 'require-approval';

-- ── agent_skills (first-class workspace skills attached to an agent) ──────────
create table if not exists agent_skills (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  name text not null,
  scope text,                                   -- 'all platforms' | 'macOS · Linux' | 'Windows'
  bytes int not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists agent_skills_agent_idx on agent_skills (agent_id);

alter table agent_skills enable row level security;
drop policy if exists agent_skills_sel on agent_skills;
create policy agent_skills_sel on agent_skills for select to authenticated
  using (org_id in (select public.user_org_ids()));
drop policy if exists agent_skills_write on agent_skills;
create policy agent_skills_write on agent_skills for all to authenticated
  using (public.user_has_role(org_id, array['owner','admin','operator']::membership_role[]))
  with check (public.user_has_role(org_id, array['owner','admin','operator']::membership_role[]));

-- ── organizations: default plan in settings jsonb (no DDL) ────────────────────
update organizations set settings = jsonb_set(settings, '{plan}', '"Team"', true)
  where settings->>'plan' is null;
