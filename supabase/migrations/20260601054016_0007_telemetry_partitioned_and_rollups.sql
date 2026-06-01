create table logs (
  id uuid not null default gen_random_uuid(),
  org_id uuid not null,
  run_id uuid,
  agent_id uuid,
  daemon_id uuid,
  level text,
  message text,
  fields jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (id, created_at)
) partition by range (created_at);
create table logs_default partition of logs default;
create index on logs using brin (created_at);
create index on logs (org_id, created_at desc);
create index on logs (run_id);

create table metrics (
  id uuid not null default gen_random_uuid(),
  org_id uuid not null,
  run_id uuid,
  agent_id uuid,
  daemon_id uuid,
  name text not null,
  value double precision not null,
  labels jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (id, created_at)
) partition by range (created_at);
create table metrics_default partition of metrics default;
create index on metrics using brin (created_at);
create index on metrics (org_id, name, created_at desc);
create index on metrics (agent_id, name, created_at desc);

create table reasoning_traces (
  id uuid not null default gen_random_uuid(),
  org_id uuid not null,
  run_id uuid,
  agent_id uuid,
  seq bigint,
  role text,
  content_redacted text,
  blob_ref text,
  created_at timestamptz not null default now(),
  primary key (id, created_at)
) partition by range (created_at);
create table reasoning_traces_default partition of reasoning_traces default;
create index on reasoning_traces using brin (created_at);
create index on reasoning_traces (run_id, seq);

create table metric_rollups (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid references agents(id) on delete cascade,
  daemon_id uuid references daemons(id) on delete cascade,
  metric text not null,
  bucket text not null,
  bucket_start timestamptz not null,
  count bigint not null default 0,
  sum double precision not null default 0,
  min double precision,
  max double precision,
  avg double precision,
  p95 double precision,
  ewma double precision,
  created_at timestamptz not null default now()
);
create unique index metric_rollups_uniq on metric_rollups (
  org_id,
  coalesce(agent_id,'00000000-0000-0000-0000-000000000000'::uuid),
  coalesce(daemon_id,'00000000-0000-0000-0000-000000000000'::uuid),
  metric, bucket, bucket_start
);
create index on metric_rollups (org_id, metric, bucket, bucket_start desc);
