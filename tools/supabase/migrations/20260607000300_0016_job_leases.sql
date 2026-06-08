-- 0016 — job_leases: single-execution guard for the in-process periodic scheduler.
-- Replaces the Arq/Redis worker. The scheduler claims a per-job lease with a conditional
-- UPDATE so only one app instance runs each tick; the check is fail-open (a missing/erroring
-- table still lets a single instance run). Service-role only (internal; no authenticated RLS).
create table if not exists job_leases (
  job          text primary key,
  locked_until timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
alter table job_leases enable row level security;
-- No policies for authenticated/anon: only the service role (the backend) touches this.
