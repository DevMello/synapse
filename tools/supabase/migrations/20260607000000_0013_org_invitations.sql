-- 0013 — org invitations (invite-by-email). The browser can't resolve an arbitrary
-- email to a user id (RLS on users only exposes users who already share an org — and
-- that's correct: it prevents email enumeration). So invites are modelled as pending
-- rows keyed by email; a backend/trigger links them to a membership on signup/accept.
create type invitation_status as enum ('pending', 'accepted', 'revoked');

create table org_invitations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  email text not null,
  role membership_role not null default 'viewer',
  status invitation_status not null default 'pending',
  invited_by uuid references users(id) on delete set null,
  token text not null default encode(gen_random_bytes(16), 'hex'),
  created_at timestamptz not null default now(),
  accepted_at timestamptz
);
create unique index org_invitations_pending_uniq
  on org_invitations (org_id, lower(email)) where status = 'pending';
create index on org_invitations (org_id);

alter table org_invitations enable row level security;
create policy org_invitations_sel on org_invitations for select to authenticated
  using (org_id in (select public.user_org_ids()));
create policy org_invitations_write on org_invitations for all to authenticated
  using (public.user_has_role(org_id, array['owner','admin']::membership_role[]))
  with check (public.user_has_role(org_id, array['owner','admin']::membership_role[]));
