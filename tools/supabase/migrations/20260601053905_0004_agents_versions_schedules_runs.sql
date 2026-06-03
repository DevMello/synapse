-- ── agents ───────────────────────────────────────────────────────────────────
create table agents (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  daemon_id uuid references daemons(id) on delete set null,   -- owning daemon
  name text not null,
  type agent_type not null,
  platform text,
  current_version int,                                         -- -> agent_versions.version
  status agent_status not null default 'active',
  limits jsonb not null default '{}'::jsonb,                   -- cost/tool-call caps etc.
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on agents (org_id);
create index on agents (daemon_id);

-- ── agent_versions (immutable prompt/config snapshots) ────────────────────────
create table agent_versions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  version int not null,
  prompt text,
  config jsonb not null default '{}'::jsonb,
  author_user_id uuid references users(id) on delete set null,
  message text,
  tags text[] not null default '{}',                            -- 'known-good','production'
  created_at timestamptz not null default now(),
  unique (agent_id, version)
);
create index on agent_versions (agent_id, version desc);

-- ── schedules ─────────────────────────────────────────────────────────────────
create table schedules (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  kind schedule_kind not null,
  cron_expr text,
  interval_seconds int,
  run_at timestamptz,
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);
create index on schedules (agent_id);

-- ── runs ───────────────────────────────────────────────────────────────────────
create table runs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  agent_version int,
  daemon_id uuid references daemons(id) on delete set null,
  trigger trigger_source not null default 'manual',
  status run_status not null default 'pending',
  started_at timestamptz,
  ended_at timestamptz,
  cost_usd numeric(12,6) not null default 0,
  tokens_in bigint not null default 0,
  tokens_out bigint not null default 0,
  exit_code int,
  redaction_summary jsonb,
  idempotency_key text,
  created_at timestamptz not null default now()
);
create index on runs (org_id, created_at desc);
create index on runs (agent_id, created_at desc);
create index on runs (daemon_id);
create unique index on runs (org_id, idempotency_key) where idempotency_key is not null;

-- ── tool_calls (per-run tool invocations, redacted) ───────────────────────────
create table tool_calls (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  run_id uuid not null references runs(id) on delete cascade,
  name text not null,
  args_redacted jsonb,
  result_redacted jsonb,
  latency_ms int,
  cost_usd numeric(12,6) not null default 0,
  created_at timestamptz not null default now()
);
create index on tool_calls (run_id);
