-- 0019 — Native Handoff Protocol (possible-features §11). An agent passes the current
-- task to a successor along a HUMAN-PRE-APPROVED chain (planner → critic → executor).
-- It is the constrained, medium-risk sibling of §2 Orchestration: NO create/edit, NO
-- fan-out. The chain is authored on a visual Flow Canvas (`agent_flows`, editable UX);
-- on publish it COMPILES into a cloud-signed `agent_chain_grants` (the enforced artifact
-- the daemon verifies + enforces locally, exactly like §2's orchestration grant).
-- Reuses §2's run-lineage columns (root_run_id/parent_run_id/depth); adds hop/handoff_mode/
-- flow_id. New audit_events action kinds ('agent.handoff') need no DDL (action is text).

-- ── agent_flows — the editable visual design authored on the canvas (UX, not security).
-- `nodes`/`edges`/`settings` are jsonb; on publish the design compiles into a signed
-- agent_chain_grants row (`published_grant_id`). Members read+write within their org. ──
create table agent_flows (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  daemon_id uuid references daemons(id) on delete set null,   -- H2: all nodes on one daemon
  name text not null default 'Untitled flow',
  version int not null default 1,
  status text not null default 'draft',                        -- draft | published | archived
  nodes jsonb not null default '[]'::jsonb,                    -- [{id, agent_id|kind, x, y, ...}]
  edges jsonb not null default '[]'::jsonb,                    -- [{id, from, to, mode, when, mapping}]
  settings jsonb not null default
    '{"max_hops":8,"chain_budget_usd":5.0,"max_payload_bytes":32768,"modes":["tail","return"],"routing":"first_match"}'::jsonb,
  published_grant_id uuid,                                      -- fk set after publish (below)
  created_by uuid references users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_flows_status_check check (status in ('draft','published','archived'))
);
create index on agent_flows (org_id);
create index on agent_flows (daemon_id);

-- ── agent_chain_grants — the signed edge-graph grant (§11.4), compiled from a published
-- agent_flows design. Minted + signed CLOUD-SIDE; cached + verified OFFLINE on the daemon.
-- Only the cloud (service role) writes these because the signature is minted server-side. ──
create table agent_chain_grants (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references organizations(id) on delete cascade,
  daemon_id uuid not null references daemons(id) on delete cascade,   -- H2: same-daemon only
  flow_id uuid references agent_flows(id) on delete set null,         -- which design produced it
  granted_by uuid references users(id) on delete set null,            -- grant ⊆ this human's authority
  edges jsonb not null default '[]'::jsonb,                           -- H3: the ONLY handoffs allowed
  routing text not null default 'first_match',                       -- H7: take ONE edge per hop
  max_hops int not null default 8,                                   -- loop guard
  chain_budget_usd numeric(12,6) not null default 5.0,               -- shared across the whole chain
  max_payload_bytes int not null default 32768,                      -- H4: bounded context transfer
  modes text[] not null default '{tail,return}',
  key_id text,                                                        -- which cloud signing key
  signature text,                                                    -- base64 ed25519 over canonical core
  expires_at timestamptz not null,
  revoked_at timestamptz,                                            -- null = active
  created_at timestamptz not null default now()
);
create index on agent_chain_grants (org_id);
create index on agent_chain_grants (daemon_id);
create index on agent_chain_grants (flow_id);

alter table agent_flows
  add constraint agent_flows_grant_fk
  foreign key (published_grant_id) references agent_chain_grants(id) on delete set null;

-- ── runs handoff lineage — reuses §2's root_run_id/parent_run_id/depth/initiator columns
-- (migration 0015); adds the handoff-specific hop/mode/flow_id. ──────────────────────────
alter table runs
  add column if not exists hop int not null default 0,
  add column if not exists handoff_mode text,                        -- tail | return
  add column if not exists flow_id uuid references agent_flows(id) on delete set null;
alter table runs
  drop constraint if exists runs_handoff_mode_check;
alter table runs
  add constraint runs_handoff_mode_check
  check (handoff_mode is null or handoff_mode in ('tail','return'));

-- ── RLS — flows are member-authored (read+write own org); chain grants are read-only to
-- members and written server-side (signed) like §2's orchestration grants. ──────────────
alter table agent_flows enable row level security;
create policy agent_flows_sel on agent_flows for select to authenticated
  using (org_id in (select public.user_org_ids()));
create policy agent_flows_ins on agent_flows for insert to authenticated
  with check (org_id in (select public.user_org_ids()));
create policy agent_flows_upd on agent_flows for update to authenticated
  using (org_id in (select public.user_org_ids()))
  with check (org_id in (select public.user_org_ids()));
create policy agent_flows_del on agent_flows for delete to authenticated
  using (org_id in (select public.user_org_ids()));

alter table agent_chain_grants enable row level security;
create policy acg_sel on agent_chain_grants for select to authenticated
  using (org_id in (select public.user_org_ids()));
-- writes: service role only — grants must be minted (signed) through the cloud endpoint
