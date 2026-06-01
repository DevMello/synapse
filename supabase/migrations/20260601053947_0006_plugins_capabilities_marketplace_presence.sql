-- ── plugins (catalog of installable capability packs) ─────────────────────────
create table plugins (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  kind capability_kind not null,
  versions jsonb not null default '[]'::jsonb,
  platforms text[] not null default '{}',
  declared_permissions jsonb not null default '{}'::jsonb,
  manifest_ref text,
  checksum text,
  signature text,
  ratings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index on plugins (name);

-- ── daemon_capabilities (DAEMON tier: provisioned/enabled on a host) ──────────
create table daemon_capabilities (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  daemon_id uuid not null references daemons(id) on delete cascade,
  plugin_id uuid references plugins(id) on delete set null,
  plugin_version text,
  kind capability_kind not null,
  install_status capability_status not null default 'installing',
  exposed_tools text[] not null default '{}',
  endpoint text,                                    -- configured MCP endpoint/args
  args jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on daemon_capabilities (daemon_id);

-- ── agent_capabilities (AGENT tier: per-agent selection) ──────────────────────
create table agent_capabilities (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  daemon_capability_id uuid not null references daemon_capabilities(id) on delete cascade,
  enabled boolean not null default true,
  auto_attached boolean not null default false,     -- built-in defaults (fs/fetch/git/memory)
  attached_by uuid references users(id) on delete set null,
  attached_at timestamptz not null default now(),
  unique (agent_id, daemon_capability_id)
);
create index on agent_capabilities (agent_id);

-- ── marketplace listings + installs ──────────────────────────────────────────
create table marketplace_listings (
  id uuid primary key default gen_random_uuid(),
  kind listing_kind not null,
  name text not null,
  description text,
  platforms text[] not null default '{}',
  required_tools jsonb not null default '[]'::jsonb,
  permissions jsonb not null default '{}'::jsonb,
  version text,
  ratings jsonb not null default '{}'::jsonb,
  manifest_ref text,
  checksum text,
  signature text,
  created_at timestamptz not null default now()
);
create index on marketplace_listings (kind);

create table marketplace_installs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  listing_id uuid not null references marketplace_listings(id) on delete cascade,
  agent_id uuid references agents(id) on delete set null,
  daemon_id uuid references daemons(id) on delete set null,
  installed_by uuid references users(id) on delete set null,
  created_at timestamptz not null default now()
);
create index on marketplace_installs (org_id);

-- ── daemon_presence (TTL heartbeat; hub routing/uptime) ───────────────────────
create table daemon_presence (
  daemon_id uuid primary key references daemons(id) on delete cascade,
  org_id uuid not null references organizations(id) on delete cascade,
  hub_node text,                                    -- which hub node holds the Connect stream
  last_heartbeat timestamptz not null default now(),
  expires_at timestamptz not null
);
create index on daemon_presence (org_id);
create index on daemon_presence (expires_at);

-- ── anomaly_events ────────────────────────────────────────────────────────────
create table anomaly_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid references agents(id) on delete cascade,
  daemon_id uuid references daemons(id) on delete cascade,
  detector text not null,                           -- 'cost_spike','latency_regression',...
  severity anomaly_severity not null default 'warning',
  metric text,
  baseline numeric,
  observed numeric,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index on anomaly_events (org_id, created_at desc);
