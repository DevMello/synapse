-- Synapse Web UI demo seed — the "busy fleet" from synapse_web/src/data/mock.ts,
-- as real rows. Reproduces the mock UI against a real backend so the migration can
-- be verified screen-by-screen. Safe to run on a fresh dev/demo project; do NOT run
-- against a project with real org data (it inserts a fixed demo org + operator).
--
-- Demo operator login: avery@northwind.test / synapse123
-- Apply after migrations 0001–0012. Idempotent where natural keys exist.

-- ── Demo auth user (confirmed email user) ────────────────────────────────────
insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, created_at, updated_at,
  raw_app_meta_data, raw_user_meta_data,
  confirmation_token, recovery_token, email_change, email_change_token_new,
  email_change_token_current, phone_change, phone_change_token, reauthentication_token
) values (
  '00000000-0000-0000-0000-000000000000',
  '22222222-2222-2222-2222-222222222222',
  'authenticated','authenticated','avery@northwind.test',
  crypt('synapse123', gen_salt('bf')),
  now(), now(), now(),
  '{"provider":"email","providers":["email"]}'::jsonb, '{}'::jsonb,
  '', '', '', '', '', '', '', ''
) on conflict (id) do nothing;

insert into auth.identities (
  id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at
) values (
  gen_random_uuid(), '22222222-2222-2222-2222-222222222222',
  '22222222-2222-2222-2222-222222222222',
  '{"sub":"22222222-2222-2222-2222-222222222222","email":"avery@northwind.test"}'::jsonb,
  'email', now(), now(), now()
) on conflict (provider_id, provider) do nothing;

-- ── Org / operator / membership ──────────────────────────────────────────────
insert into organizations (id, name, settings) values
  ('11111111-1111-1111-1111-111111111111','northwind','{"plan":"Team"}'::jsonb)
  on conflict (id) do update set settings = excluded.settings;
insert into users (id, email, display_name) values
  ('22222222-2222-2222-2222-222222222222','avery@northwind.test','Avery Koss')
  on conflict (id) do update set display_name = excluded.display_name;
insert into memberships (org_id, user_id, role) values
  ('11111111-1111-1111-1111-111111111111','22222222-2222-2222-2222-222222222222','owner')
  on conflict (org_id, user_id) do update set role = excluded.role;

-- ── Daemons + presence + latest cpu/mem metrics ──────────────────────────────
insert into daemons (id, org_id, name, tags, platform, version, status, hostname, os_version, last_ip, last_seen) values
 ('aa000000-0000-0000-0000-0000000000d1','11111111-1111-1111-1111-111111111111','my-macbook-pro','{laptop,apple-silicon}','darwin/arm64','synapsed 1.4.2','online','my-macbook-pro.local','macOS 15.3','192.168.1.24', now() - interval '2 min'),
 ('aa000000-0000-0000-0000-0000000000d2','11111111-1111-1111-1111-111111111111','ci-runner-04','{ci,linux,gpu}','linux/amd64','synapsed 1.4.2','online','ci-runner-04','Ubuntu 22.04 LTS','10.0.4.18', now() - interval '10 sec'),
 ('aa000000-0000-0000-0000-0000000000d3','11111111-1111-1111-1111-111111111111','edge-box-sf','{edge,linux}','linux/amd64','synapsed 1.4.1','online','edge-box-sf','Debian 12','73.202.88.10', now() - interval '40 sec'),
 ('aa000000-0000-0000-0000-0000000000d4','11111111-1111-1111-1111-111111111111','studio-win','{workstation,windows}','windows/amd64','synapsed 1.3.9','offline','studio-win','Windows 11 Pro','192.168.1.51', now() - interval '3 hour')
 on conflict (id) do update set status=excluded.status, last_seen=excluded.last_seen;

insert into daemon_presence (daemon_id, org_id, hub_node, last_heartbeat, expires_at) values
 ('aa000000-0000-0000-0000-0000000000d1','11111111-1111-1111-1111-111111111111','hub-1', now(), now() + interval '1 min'),
 ('aa000000-0000-0000-0000-0000000000d2','11111111-1111-1111-1111-111111111111','hub-1', now(), now() + interval '1 min'),
 ('aa000000-0000-0000-0000-0000000000d3','11111111-1111-1111-1111-111111111111','hub-2', now(), now() + interval '1 min')
 on conflict (daemon_id) do update set last_heartbeat=excluded.last_heartbeat, expires_at=excluded.expires_at;

insert into metrics (org_id, daemon_id, name, value, created_at) values
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','cpu_pct',38,now()),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','mem_pct',61,now()),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d2','cpu_pct',72,now()),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d2','mem_pct',54,now()),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d3','cpu_pct',21,now()),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d3','mem_pct',33,now());

-- ── Plugin catalog + daemon-tier capabilities ────────────────────────────────
insert into plugins (id, name, kind, platforms) values
 ('cc000000-0000-0000-0000-0000000000f1','filesystem','mcp','{darwin,linux,windows}'),
 ('cc000000-0000-0000-0000-0000000000f2','fetch','mcp','{darwin,linux,windows}'),
 ('cc000000-0000-0000-0000-0000000000f3','git','mcp','{darwin,linux,windows}'),
 ('cc000000-0000-0000-0000-0000000000f4','memory','mcp','{darwin,linux,windows}'),
 ('cc000000-0000-0000-0000-0000000000f5','github','mcp','{darwin,linux,windows}'),
 ('cc000000-0000-0000-0000-0000000000f6','browser use','script','{darwin,linux}'),
 ('cc000000-0000-0000-0000-0000000000f7','terminal use','script','{darwin,linux,windows}'),
 ('cc000000-0000-0000-0000-0000000000f8','postgres','mcp','{darwin,linux}'),
 ('cc000000-0000-0000-0000-0000000000f9','slack','mcp','{darwin,linux,windows}')
 on conflict (id) do nothing;

insert into daemon_capabilities (org_id, daemon_id, plugin_id, kind, install_status) values
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','cc000000-0000-0000-0000-0000000000f1','mcp','ready'),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','cc000000-0000-0000-0000-0000000000f2','mcp','ready'),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','cc000000-0000-0000-0000-0000000000f3','mcp','ready'),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','cc000000-0000-0000-0000-0000000000f4','mcp','ready'),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','cc000000-0000-0000-0000-0000000000f5','mcp','ready'),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','cc000000-0000-0000-0000-0000000000f6','script','ready'),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d2','cc000000-0000-0000-0000-0000000000f3','mcp','ready'),
 ('11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d3','cc000000-0000-0000-0000-0000000000f9','mcp','ready');

-- ── Agents + versions (config carries engine/model/description) ───────────────
insert into agents (id, org_id, daemon_id, name, type, current_version, status) values
 ('bb000000-0000-0000-0000-0000000000a1','11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','pr-reviewer','cli',12,'active'),
 ('bb000000-0000-0000-0000-0000000000a2','11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d2','codex-builder','cli',1,'active'),
 ('bb000000-0000-0000-0000-0000000000a3','11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d3','support-triage','api',1,'active'),
 ('bb000000-0000-0000-0000-0000000000a4','11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d2','doc-writer','cli',1,'paused'),
 ('bb000000-0000-0000-0000-0000000000a5','11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d1','data-backfill','api',1,'active'),
 ('bb000000-0000-0000-0000-0000000000a6','11111111-1111-1111-1111-111111111111','aa000000-0000-0000-0000-0000000000d4','release-notes','api',1,'archived')
 on conflict (id) do update set current_version=excluded.current_version, status=excluded.status;

insert into agent_versions (org_id, agent_id, version, prompt, config, author_user_id, message, tags, created_at) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1',12,'# pr-reviewer — system prompt',  '{"engine":"Claude Code","model":"claude-sonnet-4","description":"Reviews every PR against the northwind ruleset and writes a report."}'::jsonb,'22222222-2222-2222-2222-222222222222','Tighten coverage gate to 80%','{production}', now() - interval '2 hour'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1',11,'v11','{"engine":"Claude Code","model":"claude-sonnet-4"}'::jsonb,'22222222-2222-2222-2222-222222222222','Add network allow-list rule','{known-good}', now() - interval '1 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1',10,'v10','{"engine":"Claude Code","model":"claude-sonnet-4"}'::jsonb,'22222222-2222-2222-2222-222222222222','Rewrite voice section','{}', now() - interval '3 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1',9,'v9','{"engine":"Claude Code","model":"claude-sonnet-4"}'::jsonb,'22222222-2222-2222-2222-222222222222','Initial review ruleset','{}', now() - interval '5 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a2',1,'# codex-builder','{"engine":"Codex","model":"gpt-5-codex","description":"Implements scoped tickets and opens PRs on the build queue."}'::jsonb,'22222222-2222-2222-2222-222222222222','init','{production}', now() - interval '4 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a3',1,'# support-triage','{"engine":"API","model":"claude-sonnet-4","description":"Triages inbound tickets, drafts replies, escalates with HITL."}'::jsonb,'22222222-2222-2222-2222-222222222222','init','{}', now() - interval '6 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a4',1,'# doc-writer','{"engine":"Gemini CLI","model":"gemini-2.5-pro","description":"Keeps the docs site in sync with shipped changes."}'::jsonb,'22222222-2222-2222-2222-222222222222','init','{}', now() - interval '7 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a5',1,'# data-backfill','{"engine":"API","model":"claude-haiku-4","description":"One-shot backfill jobs over the analytics warehouse."}'::jsonb,'22222222-2222-2222-2222-222222222222','init','{}', now() - interval '8 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a6',1,'# release-notes','{"engine":"API","model":"claude-sonnet-4","description":"Drafts release notes from the merged-PR log each Friday."}'::jsonb,'22222222-2222-2222-2222-222222222222','init','{}', now() - interval '9 day')
 on conflict (agent_id, version) do nothing;

insert into schedules (org_id, agent_id, kind, run_at, enabled) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a2','one_shot', now() + interval '5 hour', true),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a4','one_shot', now() + interval '8 hour', true);

insert into webhooks (org_id, agent_id, token, enabled) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','tok-prr-1',true),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a3','tok-sup-1',true)
 on conflict (token) do nothing;

insert into runs (org_id, agent_id, daemon_id, trigger, status, started_at, ended_at, cost_usd, tokens_in, tokens_out, exit_code, created_at) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','aa000000-0000-0000-0000-0000000000d1','webhook','running', now()-interval '2 min', null, 0.41, 60000, 32000, null, now()-interval '2 min'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a2','aa000000-0000-0000-0000-0000000000d2','schedule','running', now()-interval '6 min', null, 2.10, 250000, 160000, null, now()-interval '6 min'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a3','aa000000-0000-0000-0000-0000000000d3','webhook','running', now()-interval '12 sec', null, 0.04, 5000, 3200, null, now()-interval '12 sec'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','aa000000-0000-0000-0000-0000000000d1','webhook','failed', now()-interval '18 min', now()-interval '16 min', 0.22, 30000, 21000, 1, now()-interval '18 min'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a5','aa000000-0000-0000-0000-0000000000d1','manual','succeeded', now()-interval '20 min', now()-interval '17 min', 0.31, 35000, 25000, 0, now()-interval '20 min'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a2','aa000000-0000-0000-0000-0000000000d2','schedule','succeeded', now()-interval '42 min', now()-interval '31 min', 4.80, 600000, 380000, 0, now()-interval '42 min'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','aa000000-0000-0000-0000-0000000000d1','webhook','recovering', now()-interval '1 hour', null, 0.18, 22000, 17000, null, now()-interval '1 hour'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a4','aa000000-0000-0000-0000-0000000000d2','schedule','succeeded', now()-interval '1 hour', now()-interval '57 min', 0.74, 120000, 100000, 0, now()-interval '1 hour');

insert into hitl_requests (org_id, agent_id, daemon_id, action, context, status, severity, created_at) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a2','aa000000-0000-0000-0000-0000000000d2','Force-push to protected branch','{"command":"git push --force origin main","reason":"Rebase resolved 3 conflicts; history rewritten to keep a linear log.","context_label":"12 commits · main ← feature/payment-retries"}'::jsonb,'pending','block', now()-interval '3 min'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a3','aa000000-0000-0000-0000-0000000000d3','Send refund via Stripe API','{"command":"POST /v1/refunds amount=4200 currency=usd","reason":"Customer #88213 reported a duplicate charge; confirmed in the ledger.","context_label":"ticket #5521 · customer #88213"}'::jsonb,'pending','require-approval', now()-interval '8 min'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','aa000000-0000-0000-0000-0000000000d1','Delete files outside repo root','{"command":"rm -rf ~/.cache/northwind/tmp","reason":"Cleanup wants to remove a stale 2.1 GB cache dir outside the repo guard.","context_label":"run #2211 · path guard tripped"}'::jsonb,'pending','require-approval', now()-interval '18 min');

insert into anomaly_events (org_id, agent_id, daemon_id, detector, severity, metric, baseline, observed, detail, created_at) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a3',null,'prompt_injection','warning','override attempts',1,14,'{"title":"Prompt-injection spike on support-triage","message":"Inbound ticket content repeatedly tried to override instructions. 14 blocked, agent auto-paused."}'::jsonb, now()-interval '5 min'),
 ('11111111-1111-1111-1111-111111111111',null,'aa000000-0000-0000-0000-0000000000d4','daemon_offline','warning','last heartbeat',30,10800,'{"title":"Daemon offline: studio-win","message":"No heartbeat from studio-win for 3 hours. 1 agent (release-notes) unavailable."}'::jsonb, now()-interval '3 hour'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a2',null,'cost_spike','info','cost / task',0.84,2.01,'{"title":"Cost-per-task 2.4x baseline on codex-builder","message":"Nightly build run is replanning more than usual."}'::jsonb, now()-interval '34 min');

insert into env_var_refs (org_id, agent_id, name, scope, origin, secret, value_plain, updated_by, updated_at) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','OPENAI_API_KEY','agent','ui',true,null,'AK', now()-interval '2 hour'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','GITHUB_TOKEN','agent','ui',true,null,'AK', now()-interval '1 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','DATABASE_URL','agent','ui',true,null,'Jin Park', now()-interval '3 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','LOG_LEVEL','agent','ui',false,'info','AK', now()-interval '3 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','NORTHWIND_ENV','agent','ui',false,'production','AK', now()-interval '7 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','SSH_AGENT_PID','agent','local',true,null,'—', now()-interval '1 day')
 on conflict (agent_id, name) do nothing;

insert into agent_memory (org_id, agent_id, namespace, key, text_redacted, tags, bytes, updated_at) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','rules','style/line-length','Max line length is 100 chars in the northwind monorepo.','{style}',205, now()-interval '2 hour'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','facts','fact/ci-provider','CI runs on ci-runner-04 via the build queue, not GitHub Actions.','{infra}',307, now()-interval '1 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','prefs','pref/review-tone','Reviewers prefer questions over directives for non-blocking nits.','{voice}',205, now()-interval '3 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','facts','fact/coverage-tool','Coverage is measured by vitest --coverage, reported as a single %.','{testing}',205, now()-interval '4 day'),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','facts','fact/allow-list','Network allow-list lives in reports/allow-list.txt; one host per line.','{security}',307, now()-interval '5 day')
 on conflict (agent_id, namespace, key) do nothing;

insert into agent_skills (org_id, agent_id, name, scope, bytes) values
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','review-checklist','all platforms',4198),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','security-scan','macOS · Linux',2867),
 ('11111111-1111-1111-1111-111111111111','bb000000-0000-0000-0000-0000000000a1','win-codesign','Windows',1229);

insert into marketplace_listings (kind, name, description, ratings, version) values
 ('agent','PR reviewer','Reviews diffs against a ruleset, writes a report.','{"avg":4.8}'::jsonb,'1.2.0'),
 ('agent','Support triage','Triages tickets, drafts replies, escalates with HITL.','{"avg":4.6}'::jsonb,'1.1.0'),
 ('agent','Ticket builder','Implements scoped tickets and opens PRs.','{"avg":4.7}'::jsonb,'1.0.3');
