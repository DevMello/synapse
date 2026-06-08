# Web UI Build — Synapse.html implementation (in progress)

**Branch:** `feat/web-ui` (based on `fix/tui-cloud-integration` tip 57865b6; foundation
commit 46a8f53, pushed to origin DevMello/synapse). Worker PRs target **`feat/web-ui`**,
not main. Final: one merge of feat/web-ui → main.

**What it is:** greenfield React+TS+Vite SPA under `synapse_web/` implementing the Claude
Design `Synapse.html` prototype at full depth, per docs/web-ui.md. Stack: react-router,
TanStack Query (src/api/queries.ts seam over typed mock data), Zustand (src/store/ui.ts),
Supabase client stub, Recharts, CodeMirror 6. Bespoke design CSS kept verbatim in
src/styles/ (colors_and_type/effects/app.css). Prototype vendored at
`synapse_web/design-reference/` for pixel porting.

**Parallelization:** foundation scaffolded EVERY screen/tab as a registered stub
(build green from start). Each worker fills exactly ONE file. Launched in **batches of 2**
(user request — survive usage exhaustion). E2e gate: `npm run build` green + dev render check.

**Design source:** bundle decompressed to
`C:/Users/pranav/AppData/Local/Temp/design_extract/synapse/` (also vendored in-repo).

## Unit status (22 units)

| # | Unit | File (under synapse_web/src) | Status | PR |
|---|------|------|--------|----|
| 1 | Dashboard | screens/Dashboard.tsx | DONE | #3 |
| 2 | Daemons | screens/Daemons.tsx | DONE | #2 |
| 3 | Connect-a-device | screens/Connect.tsx | DONE | #4 |
| 4 | Agents + wizard (hero1) | screens/Agents.tsx | DONE | #5 |
| 5 | Agent Overview | screens/agent/tabs/Overview.tsx | DONE | #6 |
| 6 | Editor (CodeMirror) | screens/agent/tabs/Editor.tsx | DONE | #8 |
| 7 | Versions | screens/agent/tabs/Versions.tsx | DONE | #7 |
| 8 | Schedule | screens/agent/tabs/Schedule.tsx | DONE | #9 |
| 9 | Tools/MCP | screens/agent/tabs/Tools.tsx | DONE | #10 |
| 10 | Plugins | screens/agent/tabs/Plugins.tsx | DONE | #12 |
| 11 | Environment | screens/agent/tabs/Environment.tsx | DONE | #11 |
| 12 | Memory | screens/agent/tabs/Memory.tsx | DONE | #13 |
| 13 | Runs + Live Trace (hero2) | screens/agent/tabs/Runs.tsx (+Trace/Terminal) | DONE | #14 |
| 14 | Logs | screens/agent/tabs/Logs.tsx | DONE | #15 |
| 15 | Analytics (Recharts) | screens/agent/tabs/Analytics.tsx | DONE | #16 |
| 16 | Global Runs | screens/Runs.tsx | DONE | #17 |
| 17 | Approvals (hero3) | screens/Approvals.tsx | DONE | #18 |
| 18 | Alerts | screens/Alerts.tsx | DONE | #19 |
| 19 | Marketplace | screens/Marketplace.tsx | DONE | #20 |
| 20 | Notifications + Webhooks | screens/Notifications.tsx, screens/Webhooks.tsx | DONE | #21 |
| 21 | Settings & RBAC | screens/Settings.tsx | DONE | #22 |
| 22 | Tweaks panel | screens/Tweaks.tsx | DONE | #23 |

**COMPLETE + MERGED TO MAIN** (e5ca322, --no-ff, pushed 316793d..e5ca322; full-merge also
carried base commits 0e0ec8d daemon<->cloud hardening + 57865b6 secret removal). main builds
GREEN (958 modules, strict tsc, chunk-size advisory only).

**tui-cloud-integration also merged to main** (28b9637): the branch's stashed WIP — daemon
registers its X25519 pubkey in daemon.register → cloud daemons.e2e_public_key, the backend
for the Web UI Environment tab's env-var sealing (§4.6) — committed (021b1f7) + merged; 35 tests pass.

**Bundle code-split** (feat/web-bundle-split, PR #24, OPEN against main): lazy routes + lazy
Agent Detail tabs (CodeMirror/Recharts become async chunks) + manualChunks vendor grouping.
Initial JS 1,425kB→~385kB (447→~126kB gzip). Build clean; Editor/Analytics verified live, no
console errors. Files: vite.config.ts, src/router.tsx, src/components/Shell.tsx,
src/screens/agent/AgentDetail.tsx. Pattern for future lazy work: Suspense boundary in
AppLayout (Shell.tsx) + per-tab Suspense in AgentDetail.tsx.

All 22 units landed as PRs #2–#23 against feat/web-ui. All 22 feature branches
merged into feat/web-ui (zero conflicts — each owned a distinct file) and pushed
(46a8f53..cc8d8df). Integrated build GREEN: `npm run build` → 958 modules, strict tsc clean,
only a chunk-size advisory. Dev server boots with no console errors; Dashboard renders on-brand
(verified via screenshot). Remaining: user opens single PR feat/web-ui → main.

Note: integrated bundle is ~1.4MB (Recharts + CodeMirror) — future: code-split via manualChunks.
Windows gotcha: stray esbuild.exe/node from worker dev servers can lock node_modules; kill them
before `npm ci` in the main checkout.

Source refs per unit: see plan `~/.claude/plans/reactive-noodling-marble.md`. Prototype
files map: Dashboard.jsx, Daemons.jsx, Connect.jsx, Agents.jsx, AgentDetail.jsx (Overview),
AgentTabs1.jsx (Editor/Versions/Schedule), AgentTabs2.jsx (Tools/Plugins/Environment),
AgentTabs3.jsx (Memory/Runs/Logs/Analytics), Trace.jsx+Terminal.jsx, Views.jsx (Runs/
Approvals/Alerts/Marketplace/Webhooks/Notifications/Settings), tweaks-panel.jsx.

**GOTCHA (worktree base):** spawned worktree agents are created from an OLD base commit
(316793d), NOT feat/web-ui HEAD — so the synapse_web foundation is missing until they sync.
Every worker prompt MUST tell them: first `git merge feat/web-ui` (fast-forward) into their
worktree branch (or `git fetch origin && git merge --ff-only origin/feat/web-ui`) so the
foundation is present, THEN implement. Daemons worker (unit 2) handled this manually and
landed PR #2 fine; bake the step into all remaining prompts.

**To resume:** spawn next pending pair as worktree background workers, PRs → feat/web-ui.
