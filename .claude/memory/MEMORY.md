# Synapse — Memory Index

- [Project Overview](project_overview.md) — 3-product agent-manager platform (Web UI, Cloud Backend, TUI Daemon); docs in docs/.
- [Cloud Backend Build](cloud_backend_build.md) — Cloud Backend now implemented on master (16 units); build conventions, seams, real-Supabase test strategy.
- [TUI Daemon Build](tui_daemon_build.md) — TUI Worker Daemon now implemented on master (synapse_worker/, 16 units); auto-discovery seams, wire-contract facts, self-contained test strategy.
- [Web UI Build](web_ui_build.md) — Synapse.html implemented as Vite+React+TS SPA under synapse_web/ on feat/web-ui; foundation + 22 parallel stub-fill units (batches of 2); unit/PR status table.
- [Web UI → Supabase migration](web_supabase_migration.md) — feat/web-supabase: mock fleet replaced by live Supabase (project gpxfylwhwdsswbgicgby); migrations 0010/0011, per-domain query/adapter modules, AuthGate, Realtime; merged PR #25, live-data verified.
- [Org structure feature](org_structure_feature.md) — PR #26: Members & RBAC wired to memberships + org_invitations (0013), team/business-unit hierarchy (0014) in Settings; live-verified.
- [Agent Orchestration MVP](agent_orchestration_mvp.md) — PR #27 (open): possible-features §2 run_agent path across schema (0015) + cloud (ed25519 grants) + daemon (broker/MCP/lineage) + web (Orchestration tab); 6+14 tests pass.
- [Native Handoff Protocol](native_handoff_feature.md) — PR #60 MERGED to main: possible-features §11 full-stack (0019 schema + cloud chain_crypto/handoff router + daemon handoff broker/runner/mcp + award-winning web Flow Canvas under src/screens/flow/); 5+13 tests; build green. §11 graduated out of possible-features.md. Migration 0019 NOT yet applied to live.
- [Model Comparison Runs](comparison_feature.md) — feat/model-comparison: possible-features §10 full-stack (0020 schema + cloud comparison router/pricing + daemon group executor/draft-mode shim/agentic tool loop in api_adapter + web Compare tab & comparison screen under src/screens/comparison/); 12+8 tests, 330+ worker green, build green, MOCK-verified. §10 graduated to a stub. Migration 0020 NOT yet applied to live.
