-- 0011 — Web UI read views + Realtime publication.
-- Views are security_invoker so the caller's RLS (org_id ∈ user_org_ids()) applies.
-- Requires PG15+ (synapse project is PG17).

-- ── agent_overview: one row per agent with engine/model/prompt + run rollups ──
create or replace view agent_overview
with (security_invoker = true) as
select
  a.id,
  a.org_id,
  a.daemon_id,
  a.name,
  a.type,
  a.status,
  a.current_version,
  cv.prompt,
  coalesce(cv.config->>'engine', 'API')               as engine,
  coalesce(cv.config->>'model', '')                   as model,
  coalesce(cv.config->>'description', '')             as description,
  coalesce(rt.runs_total, 0)                          as runs_total,
  coalesce(rt.spend_today, 0)                         as spend_today,
  coalesce(rt.tokens_today, 0)                        as tokens_today,
  coalesce(rt.err_rate, 0)                            as err_rate,
  rt.last_run_at,
  nr.next_run_at,
  exists (
    select 1 from webhooks w where w.agent_id = a.id and w.enabled
  )                                                   as has_webhook,
  a.updated_at
from agents a
left join agent_versions cv
  on cv.agent_id = a.id and cv.version = a.current_version
left join lateral (
  select
    count(*)                                                                       as runs_total,
    sum(case when r.created_at::date = now()::date then r.cost_usd else 0 end)     as spend_today,
    sum(case when r.created_at::date = now()::date
             then r.tokens_in + r.tokens_out else 0 end)                          as tokens_today,
    round(
      (count(*) filter (where r.status = 'failed'))::numeric
      / nullif(count(*), 0) * 100, 1)                                              as err_rate,
    max(r.started_at)                                                             as last_run_at
  from runs r where r.agent_id = a.id
) rt on true
left join lateral (
  select min(s.run_at) as next_run_at
  from schedules s
  where s.agent_id = a.id and s.enabled and s.run_at > now()
) nr on true;

-- ── daemon_overview: one row per daemon with latest cpu/mem + active runs ─────
create or replace view daemon_overview
with (security_invoker = true) as
select
  d.id,
  d.org_id,
  d.name,
  d.hostname,
  d.os_version,
  d.last_ip,
  d.status,
  d.version,
  d.tags,
  d.platform,
  d.last_seen,
  coalesce(cpu.value, 0)            as cpu,
  coalesce(mem.value, 0)           as mem,
  coalesce(ar.active_runs, 0)      as active_runs,
  pres.last_heartbeat,
  pres.expires_at
from daemons d
left join lateral (
  select m.value from metrics m
  where m.daemon_id = d.id and m.name = 'cpu_pct'
  order by m.created_at desc limit 1
) cpu on true
left join lateral (
  select m.value from metrics m
  where m.daemon_id = d.id and m.name = 'mem_pct'
  order by m.created_at desc limit 1
) mem on true
left join lateral (
  select count(*) as active_runs from runs r
  where r.daemon_id = d.id and r.status = 'running'
) ar on true
left join daemon_presence pres on pres.daemon_id = d.id;

-- ── Realtime publication (RLS still gates per-subscriber delivery) ────────────
do $$
declare t text;
declare tbls text[] := array[
  'runs','hitl_requests','anomaly_events','logs','reasoning_traces','daemon_presence'
];
begin
  foreach t in array tbls loop
    if not exists (
      select 1 from pg_publication_tables
      where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t
    ) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;
