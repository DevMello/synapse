-- Partitions don't inherit the parent's RLS enablement. Enable RLS on the default
-- partitions so direct access is blocked; queries through the parent table still
-- apply the parent's org-scoped policies, and service_role (backend) bypasses RLS.
alter table logs_default enable row level security;
alter table metrics_default enable row level security;
alter table reasoning_traces_default enable row level security;
