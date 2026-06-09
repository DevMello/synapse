-- ── recovery_codes (TOTP/FIDO backup codes; hashes only, never plaintext) ─────
create table recovery_codes (
  id         uuid        primary key default gen_random_uuid(),
  user_id    uuid        not null references auth.users(id) on delete cascade,
  code_hash  text        not null,
  used_at    timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, code_hash)
);
-- RLS: enable but grant NO policies to authenticated — service_role only
alter table recovery_codes enable row level security;

-- ── users: track whether MFA has been enrolled ────────────────────────────────
alter table users add column mfa_enrolled bool not null default false;
-- Block direct client writes; only service_role (the backend) may flip this flag.
revoke update (mfa_enrolled) on users from authenticated;

-- ── org_security_policy (one row per org, owner-managed) ─────────────────────
create table org_security_policy (
  org_id           uuid primary key references organizations(id) on delete cascade,
  require_mfa      bool        not null default false,
  mfa_grace_until  timestamptz,
  step_up_max_age  int         not null default 900,  -- seconds; default 15 min
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- RLS: members can read the policy; only owners may insert/update
alter table org_security_policy enable row level security;

create policy org_security_policy_sel on org_security_policy
  for select to authenticated
  using (org_id in (select public.user_org_ids()));

create policy org_security_policy_write on org_security_policy
  for all to authenticated
  using (public.user_has_role(org_id, array['owner']::membership_role[]))
  with check (public.user_has_role(org_id, array['owner']::membership_role[]));

-- ── audit_events: action column is plain text; no DDL needed ─────────────────
-- New event kinds used by the MFA feature (recorded at runtime by service_role):
--   'mfa_enrolled'        – user completes TOTP/FIDO setup
--   'recovery_code_used'  – a backup code was consumed
--   'mfa_factor_reset'    – an admin resets a user's MFA factors
