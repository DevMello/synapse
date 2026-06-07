-- 0014 — team / business-unit hierarchy within an org. Teams self-nest via
-- parent_team_id; team_memberships assign org users to teams. Org-scoped RLS
-- (members read, owner/admin write) mirrors memberships. This adds structure +
-- assignment; it does NOT change agent/run RLS (data stays org-scoped for now).
create table teams (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  parent_team_id uuid references teams(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);
create index on teams (org_id);
create index on teams (parent_team_id);

create table team_memberships (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  team_id uuid not null references teams(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (team_id, user_id)
);
create index on team_memberships (team_id);
create index on team_memberships (org_id);

alter table teams enable row level security;
create policy teams_sel on teams for select to authenticated
  using (org_id in (select public.user_org_ids()));
create policy teams_write on teams for all to authenticated
  using (public.user_has_role(org_id, array['owner','admin']::membership_role[]))
  with check (public.user_has_role(org_id, array['owner','admin']::membership_role[]));

alter table team_memberships enable row level security;
create policy team_memberships_sel on team_memberships for select to authenticated
  using (org_id in (select public.user_org_ids()));
create policy team_memberships_write on team_memberships for all to authenticated
  using (public.user_has_role(org_id, array['owner','admin']::membership_role[]))
  with check (public.user_has_role(org_id, array['owner','admin']::membership_role[]));
