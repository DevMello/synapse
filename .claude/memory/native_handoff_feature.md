# Native Handoff Protocol (Feature 11, §11) — feat/handoff-protocol

PR #60 **MERGED to main** (merge `2e824cf`); §11 graduated out of docs/possible-features.md
to a stub (commit `119877b`). Implements possible-features
§11 end-to-end — the constrained, medium-risk sibling of §2 Orchestration ([[agent_orchestration_mvp]]):
a sequential **baton-pass** along a human-pre-approved chain on ONE daemon (no create/edit,
no fan-out), authored on a bespoke **Flow Canvas**. Built inline by the coordinator (worktree
subagents can't run shell here — see [[web_supabase_migration]] /batch note).

**Schema:** migration `0019_native_handoff` **APPLIED to live `gpxfylwhwdsswbgicgby`** (2026-06-13
via the Supabase MCP, alongside 0018 + 0020, to bring live in sync with `main`). `agent_flows`
(editable canvas design: nodes/edges/settings jsonb, status draft/published, published_grant_id),
`agent_chain_grants` (signed edge graph compiled on publish), `runs` += hop/handoff_mode/flow_id.
RLS: flows member read+write; chain grants member-read / service-role-write. Reuses §2's
root_run_id/parent_run_id/depth.

**Cloud** (`synapse_cloud/`): `chain_crypto.py` (`chain_grant_core` + reuses orchestration_crypto's
ed25519 key + `canonical_bytes`/`sign_core` — daemon trusts ONE cloud key). `routers/handoff.py`:
`POST /flows/{id}/publish` (validate §11 envelope: single daemon H2, no production nodes §4,
valid modes → compile node→agent edges, drop structural nodes → sign → push `chain.grant` →
mark published), `POST /chain-grants/{id}/revoke` (+ reuse `orchestration.halt`), inbound
`@on_daemon_message("agent.handoff")` audit + successor lineage. Flow CRUD stays direct Supabase.

**Daemon** (`synapse_worker/`): `handoff/broker.py` `authorize_handoff` (verify sig+expiry+
same-daemon+**edge-in-graph H3**+mode+hop+budget; `edge_in_grant`; chain_grants cache;
`grant_for_edge`/`successors`). `handoff/runner.py` `handoff()` (redact envelope via Layer A +
`max_payload_bytes` cap H4 → `lineage_append` reusing orchestrator's WAL with verb='handoff' →
async `agent.handoff` → dispatch successor `agent.run` carrying root_run_id). `handoff/mcp_server.py`
(`synapse.handoff`/`handoff_return`/`list_chain`). `commands/handoff.py` (`chain.grant` cache,
`chain.revoke` drop; halt reuses §2's `orchestration.halt` since hops share orchestration_lineage).
`store.py` += `chain_grants` table.

**Web** (`synapse_web/`): the **award-winning Flow Canvas** (hand-rolled, no graph dep) under
`src/screens/flow/`: `FlowCanvas.tsx` (pan/zoom + pointer interactions + draft-run trace),
`useFlowGraph.ts` (graph state), `validate.ts` (live §11 validation), `templates.ts` (seed +
Planner▸Critic▸Executor / Draft▸Review-loop▸Publish), `canvas/` (geometry, FlowNode, FlowEdge,
NodePalette, Inspector, Toolbar, ConsentModal, TraceBanner). `screens/Flows.tsx` library.
`styles/flow-canvas.css` (warm editorial: dotted grid, accent-glow active edge, node pulse).
Data: `api/queries/flows.ts` (+ in-memory MOCK store so the canvas is fully interactive offline),
`adapters/flows.ts`, `queries/flowTrace.ts`. `/flows` + `/flows/:flowId` routes; "Operate" nav.

**Verified:** 5 cloud unit + 13 daemon handoff tests pass (38 incl. orchestration regression).
Web `npm run build` green (FlowCanvas its own 26kB lazy chunk). Canvas live-verified in MOCK
mode via accessibility snapshots (library → open → validation → publish consent → published),
zero console errors.

**Gotchas:**
- `broker.canonical_bytes` MUST stay byte-identical to `orchestration_crypto.canonical_bytes`
  (chain_crypto reuses it). Edges are sorted in `chain_grant_core` so signature is draw-order-independent.
- Preview SCREENSHOT tool times out (30s) on every page in this env (incl. plain auth) — use
  `preview_snapshot` (accessibility tree) as proof instead.
- Local `synapse_web/.env` (gitignored) puts the app in LIVE Supabase mode → AuthGate blocks +
  agent_flows tables missing. To demo the canvas, move `.env` aside → mock mode (no auth, seeded
  flow renders), then restore.
- Fixed a PRE-EXISTING duplicate `activeOrgId`/`setActiveOrgId` in `store/ui.ts` (interface +
  impl) that was failing `tsc` on main.

**Deferred:** apply 0019 to live + live publish/revoke integration test; feature-flag/consent
gating at org level (off-by-default §4); `handoff` capability auto-wiring into the live runtime;
return-mode resume (recorded, not yet resumed); field-mapping expression editor.
