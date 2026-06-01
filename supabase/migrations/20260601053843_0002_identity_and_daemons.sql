-- ── organizations ───────────────────────────────────────────────────────────
create table organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  settings jsonb not null default '{}'::jsonb,
  recovery_public_key text,                       -- org X25519 pubkey (checkpoint encryption)
  created_at timestamptz not null default now()
);

-- ── users (app profile; id == auth.users.id) ─────────────────────────────────
create table users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  created_at timestamptz not null default now()
);

-- ── memberships (user ↔ org, with role) ──────────────────────────────────────
create table memberships (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  role membership_role not null default 'viewer',
  created_at timestamptz not null default now(),
  unique (org_id, user_id)
);
create index on memberships (user_id);
create index on memberships (org_id);

-- ── daemons (registered workers) ─────────────────────────────────────────────
create table daemons (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  tags text[] not null default '{}',
  platform text,                                  -- e.g. 'darwin-arm64'
  version text,
  status daemon_status not null default 'offline',
  -- device identity (powers "logged in on my-macbook-pro, last seen 2m ago")
  hostname text,
  os_version text,
  last_ip inet,
  last_seen timestamptz,
  -- auth
  refresh_token_hash text,
  refresh_token_issued_at timestamptz,
  revoked_at timestamptz,                          -- null = active
  -- e2e env-var relay
  e2e_public_key text,                             -- X25519 pubkey; private half stays on daemon
  created_at timestamptz not null default now()
);
create index on daemons (org_id);
create index on daemons (org_id, status);

-- ── device_authorizations (RFC 8628 device-code login) ───────────────────────
create table device_authorizations (
  id uuid primary key default gen_random_uuid(),
  device_code_hash text not null unique,           -- opaque code, stored hashed
  user_code text not null unique,                  -- human 'ABCD-1234'
  status device_auth_status not null default 'pending',
  -- requesting device metadata
  hostname text,
  os_version text,
  daemon_version text,
  request_ip inet,
  -- bound on approval
  org_id uuid references organizations(id) on delete cascade,
  user_id uuid references users(id) on delete set null,
  daemon_id uuid references daemons(id) on delete set null,
  interval_seconds int not null default 5,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index on device_authorizations (user_code);
create index on device_authorizations (expires_at);
