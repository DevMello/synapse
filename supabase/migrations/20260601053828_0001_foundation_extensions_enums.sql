create extension if not exists pgcrypto;

create type membership_role as enum ('owner','admin','operator','viewer');
create type daemon_status as enum ('online','offline','revoked');
create type device_auth_status as enum ('pending','authorized','denied','expired');
create type agent_type as enum ('api','cli');
create type agent_status as enum ('active','paused','archived');
create type run_status as enum ('pending','running','succeeded','failed','cancelled','interrupted','recovering','resumed');
create type trigger_source as enum ('manual','schedule','webhook','recovery');
create type schedule_kind as enum ('cron','interval','one_shot');
create type capability_kind as enum ('mcp','script','workspace','composite');
create type capability_status as enum ('installing','ready','failed');
create type hitl_status as enum ('pending','approved','denied','expired');
create type notification_channel_kind as enum ('slack','discord','email','in_app');
create type env_var_origin as enum ('ui','local');
create type env_var_scope as enum ('agent','shared');
create type anomaly_severity as enum ('info','warning','critical');
create type listing_kind as enum ('agent','skill','plugin');
