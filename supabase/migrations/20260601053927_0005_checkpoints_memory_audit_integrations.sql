-- ── run_checkpoints (plaintext metadata + ref to E2E-encrypted blob) ──────────
create table run_checkpoints (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  run_id uuid not null references runs(id) on delete cascade,
  seq bigint not null,                              -- monotonic checkpoint sequence
  step_cursor int,
  status run_status,
  cost_so_far_usd numeric(12,6) not null default 0,
  daemon_id uuid references daemons(id) on delete set null,
  payload_blob_ref text,                            -- Storage key; cloud cannot decrypt
  created_at timestamptz not null default now(),
  unique (run_id, seq)
);
create index on run_checkpoints (run_id, seq desc);

-- ── agent_memory (REDACTED plaintext snapshot under RLS, NOT E2E) ─────────────
create table agent_memory (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  namespace text not null default 'default',
  key text not null,
  value_redacted jsonb,
  text_redacted text,
  tags text[] not null default '{}',
  embedding_ref text,
  version int not null default 1,
  bytes int not null default 0,
  updated_by text,                                  -- 'daemon' | 'operator:<user_id>'
  updated_at timestamptz not null default now(),
  unique (agent_id, namespace, key)
);
create index on agent_memory (agent_id);

-- per-agent memory rollups
create table agent_memory_rollups (
  agent_id uuid primary key references agents(id) on delete cascade,
  org_id uuid not null references organizations(id) on delete cascade,
  entry_count int not null default 0,
  total_bytes bigint not null default 0,
  provider text,
  updated_at timestamptz not null default now()
);

-- ── audit_events (append-only, optional hash-chain) ───────────────────────────
create table audit_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  actor text,                                       -- 'user:<id>' | 'daemon:<id>' | 'system'
  action text not null,
  resource_type text,
  resource_id text,
  run_id uuid references runs(id) on delete set null,
  detail jsonb not null default '{}'::jsonb,        -- redacted
  prev_hash text,
  hash text,
  created_at timestamptz not null default now()
);
create index on audit_events (org_id, created_at desc);
create index on audit_events (run_id);

-- ── gateways (outbound integrations agents may use) ───────────────────────────
create table gateways (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid references agents(id) on delete cascade,
  name text not null,
  kind text not null,                               -- http | queue | mcp | api
  config jsonb not null default '{}'::jsonb,        -- policy only; no creds
  created_at timestamptz not null default now()
);
create index on gateways (org_id);

-- ── webhooks (inbound triggers) ───────────────────────────────────────────────
create table webhooks (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  token text not null unique,                       -- path segment /hooks/{token}
  secret_hash text,                                 -- HMAC secret (hashed)
  payload_template jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);
create index on webhooks (agent_id);

-- ── notification_channels ─────────────────────────────────────────────────────
create table notification_channels (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  kind notification_channel_kind not null,
  config jsonb not null default '{}'::jsonb,        -- webhook url / email addr / etc.
  routing_rules jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);
create index on notification_channels (org_id);

-- ── hitl_requests (approval gates) ────────────────────────────────────────────
create table hitl_requests (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  run_id uuid references runs(id) on delete cascade,
  agent_id uuid references agents(id) on delete cascade,
  daemon_id uuid references daemons(id) on delete set null,
  action text not null,
  context jsonb,                                    -- redacted proposed action + reasoning
  status hitl_status not null default 'pending',
  resolved_by uuid references users(id) on delete set null,
  resolution_reason text,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index on hitl_requests (org_id, status);
create index on hitl_requests (run_id);

-- ── env_var_refs (metadata only, never values) ────────────────────────────────
create table env_var_refs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  agent_id uuid references agents(id) on delete cascade,
  daemon_id uuid references daemons(id) on delete cascade,
  name text not null,
  scope env_var_scope not null default 'agent',
  origin env_var_origin not null default 'ui',
  updated_by text,
  updated_at timestamptz not null default now(),
  unique (agent_id, name)
);
create index on env_var_refs (daemon_id);
