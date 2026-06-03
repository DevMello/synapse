-- ── generic org-scoped tables: members read; operator+ write ──────────────────
do $$
declare t text;
declare org_scoped text[] := array[
  'daemons','agents','agent_versions','schedules','runs','tool_calls',
  'run_checkpoints','agent_memory','agent_memory_rollups','gateways','webhooks',
  'notification_channels','hitl_requests','env_var_refs','daemon_capabilities',
  'agent_capabilities','marketplace_installs','daemon_presence','anomaly_events',
  'logs','metrics','reasoning_traces','metric_rollups'
];
begin
  foreach t in array org_scoped loop
    execute format('alter table %I enable row level security', t);
    execute format($p$create policy %I on %I for select to authenticated
                      using (org_id in (select public.user_org_ids()))$p$,
                   t||'_sel', t);
    execute format($p$create policy %I on %I for all to authenticated
                      using (public.user_has_role(org_id, array['owner','admin','operator']::membership_role[]))
                      with check (public.user_has_role(org_id, array['owner','admin','operator']::membership_role[]))$p$,
                   t||'_write', t);
  end loop;
end $$;

-- ── organizations ─────────────────────────────────────────────────────────────
alter table organizations enable row level security;
create policy organizations_sel on organizations for select to authenticated
  using (id in (select public.user_org_ids()));
create policy organizations_write on organizations for all to authenticated
  using (public.user_has_role(id, array['owner','admin']::membership_role[]))
  with check (public.user_has_role(id, array['owner','admin']::membership_role[]));

-- ── users ──────────────────────────────────────────────────────────────────────
alter table users enable row level security;
create policy users_sel on users for select to authenticated
  using (
    id = auth.uid()
    or id in (select m.user_id from public.memberships m
              where m.org_id in (select public.user_org_ids()))
  );
create policy users_self_upsert on users for insert to authenticated
  with check (id = auth.uid());
create policy users_self_update on users for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

-- ── memberships ────────────────────────────────────────────────────────────────
alter table memberships enable row level security;
create policy memberships_sel on memberships for select to authenticated
  using (org_id in (select public.user_org_ids()));
create policy memberships_write on memberships for all to authenticated
  using (public.user_has_role(org_id, array['owner','admin']::membership_role[]))
  with check (public.user_has_role(org_id, array['owner','admin']::membership_role[]));

-- ── audit_events: append-only — members read, no user writes (service_role only) ─
alter table audit_events enable row level security;
create policy audit_events_sel on audit_events for select to authenticated
  using (org_id in (select public.user_org_ids()));
revoke insert, update, delete on audit_events from authenticated, anon;

-- ── device_authorizations: backend (service_role) only ───────────────────────
alter table device_authorizations enable row level security;

-- ── global catalogs: any authenticated user may browse; writes service_role only ─
alter table plugins enable row level security;
create policy plugins_sel on plugins for select to authenticated using (true);
alter table marketplace_listings enable row level security;
create policy listings_sel on marketplace_listings for select to authenticated using (true);
