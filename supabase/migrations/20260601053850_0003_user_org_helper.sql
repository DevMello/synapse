create or replace function public.user_org_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select m.org_id from public.memberships m where m.user_id = auth.uid()
$$;

-- role check helper: does the current user hold one of the given roles in an org?
create or replace function public.user_has_role(target_org uuid, roles membership_role[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.memberships m
    where m.user_id = auth.uid()
      and m.org_id = target_org
      and m.role = any(roles)
  )
$$;
