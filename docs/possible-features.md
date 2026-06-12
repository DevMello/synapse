# Possible / Experimental Features

> **Status: EXPERIMENTAL — design only, not in the MVP.** Everything in this document is
> **off by default**, gated behind an org-level feature flag and an explicit consent
> screen, **excluded from `production`-tagged agents**, and enabled only by an org owner.
> These features deliberately bend assumptions the rest of the platform relies on, so each
> ships with its blast-radius controls *first*. Last updated 2026-06-07.

This file collects high-risk, exploratory features that are not yet promoted into the four
core specs ([tui-daemon](tui-daemon.md), [cloud-backend](cloud-backend.md),
[web-ui](web-ui.md), [integration](integration.md)). When one graduates, §10 lists the exact
touchpoints to propagate it into.

---

## 1. Core concept — agents as a fourth principal

Until now every command in Synapse originates from one of three **principals**:

1. a **human** (Web UI click),
2. a **schedule** (APScheduler firing),
3. a **webhook** (external trigger).

Both features below introduce a fourth: an **agent** as a command/authority source. This is
powerful and dangerous, so the entire design rests on one rule:

> **Attenuated delegated authority.** An agent acts *on behalf of* the human who granted it,
> with a **strict subset** of that human's permissions, encoded in a **signed, scoped
> grant**. An agent can never do — or approve — anything the granting human could not, and
> the riskiest verbs always remain behind a live human.

### 1.1 What this preserves (the three invariants still hold)

These features do **not** break the platform's invariants
([integration §6](integration.md)):

- **Browser ⇄ daemon never talk directly** — agent-initiated commands still flow
  agent → its daemon → outbound WebSocket → cloud broker → target. The cloud still brokers.
- **Cloud never executes agents / holds raw secrets** — execution stays on the daemon;
  the cloud authorizes/audits/orchestrates only.
- **Daemon is outbound-only** — agents ride the existing daemon-initiated WebSocket
  control channel; no inbound port is opened.

What is genuinely new: an **agent identity** as a first-class principal, and a small
amount of **delegated-authority machinery** (grants, lineage, delegated approval).

### 1.2 Locked design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Orchestration is daemon-local only (v1).** An agent may run/create/edit only agents on its **own** daemon. | Eliminates lateral movement (low-trust → high-trust host) and keeps the whole orchestration tree on one machine, so lineage/budget/cycle-detection are local. Cross-daemon is deferred (§9). |
| D2 | **AI permission-editing is forbidden.** Agents may do delegated *approval* of a narrow class only; editing another agent's permissions/rulesets is **always** a human. | An agent that can edit permissions can escalate itself to root. Closes the hole entirely. |
| D3 | **Orchestration authz = local-enforce + async audit.** The cloud mints a signed grant; the daemon caches and **enforces it locally**, streaming audit up. | Fits "the daemon is the enforcement point," preserves offline durability, lowers latency. Cloud keeps revoke + kill switch. |
| D4 | **Approver policy = deterministic floor + bounded AI judgment.** A human writes hard, daemon-enforced gates; the agent adds fuzzy judgment only *on top* and can only **narrow**. | A compromised approver degrades to over-*denying* (annoying), never over-*approving* (catastrophic). This is the property that makes Feature 2 shippable at all. |

---

## 2. Feature 1 — Agent Orchestration — GRADUATED ✅

> **Graduated to core (2026-06-08).** Implemented end-to-end and merged to `main` (PR #27):
> migration `0015_agent_orchestration` (signed grants + run lineage), the cloud grant-signing
> router (`synapse_cloud/routers/orchestration.py` + `orchestration_crypto.py`), the daemon
> orchestration broker/runner/MCP (`synapse_worker/orchestrator/`), and the Agent
> **Orchestration** tab in the Web UI. It is no longer an experimental design note; the shared
> §§ 1, 4–9 framing below remains for Feature 2 (Agent-as-Approver), which is still pending.
> Off-by-default behind the §4 org-level feature flag + consent gate. See
> `.claude/memory/agent_orchestration_mvp.md`.

---

## 3. Feature 2 — Agent-as-Approver (EXTREMELY HIGH RISK)

*An agent approves a narrow class of other agents' HITL requests on your behalf. (It may
**not** edit permissions — D2.)*

### 3.1 Overview & the safety argument

HITL exists precisely as the **human backstop** for when a ruleset flags something
dangerous. Letting an AI fill that role removes the human from exactly that moment, so this
is the platform's single most dangerous feature. It is made tolerable by **D4**:

> The human writes a **deterministic floor** (hard gates enforced by the daemon, *below* the
> model). The approver agent may apply **fuzzy judgment only on top**, and can only
> **narrow** — it can **deny** anything, but can only **approve** what already passed the
> floor. Therefore a compromised/injected approver degrades to **over-denying** (a nuisance),
> **never over-approving** (a catastrophe).

The agent is framed as an **accelerator of pre-authorized decisions**, never a **grantor of
new authority**.

### 3.2 The policy envelope (deterministic floor + AI judgment)

```jsonc
// approval_delegations
{
  "delegation_id": "dlg_…",
  "approver_agent_id": "agt_supervisor",
  "delegated_by": "usr_…",                 // approver ⊆ this human's authority
  "scope_requesting_agents": ["agt_mailer", "tag:routine"],
  "floor": {                               // DETERMINISTIC — enforced by the daemon
    "action_types": ["send_email", "retry_run", "read_path"],
    "max_cost_usd": 1.00,
    "path_allow": ["./drafts", "./public"],
    "max_severity": "low"
  },
  "judgment_prompt": "Approve only if the drafted reply is on-topic and makes no commitments.",
  "non_delegable": ["secrets","destructive","financial>","permission_edit"],  // always human
  "expires_at": "2026-06-01T08:00:00Z",    // e.g. "while I'm asleep"
  "exclusions": ["self","modifiers","approver_agents"]                        // no self-dealing
}
```

- **Floor** gates (`action_types`, `max_cost_usd`, `path_allow`, `max_severity`) are checked
  by the **daemon**, below the model. If any fails → the request falls through to a human.
- **Judgment** runs only for requests that *pass the floor*; the approver returns
  `approve | deny`. `deny` always sticks; `approve` is honored only because the floor already
  cleared it.

### 3.3 Non-delegable classes & no-self-dealing

- **Always human, never delegable:** secrets access, destructive ops, financial over
  threshold, and **any permission/ruleset/capability edit** (D2).
- **No self-dealing** — a conflict-of-interest graph check forbids an approver from
  resolving: its own requests, requests from agents that can modify it, or any request that
  affects approver agents (this also blocks the "who watches the watchmen" recursion).
- **Untrusted input** — the approver reads the requesting run's context, which may carry
  attacker-controlled content, so its input is screened by the **prompt-injection guard**
  ([tui-daemon §4.5 Layer B](tui-daemon.md)). Even a fully-injected approver cannot breach
  the deterministic floor.

### 3.4 Flow

```
Agent "mailer" hits a HITL gate: send_email($0.10, ./drafts/reply.md, severity=low)
  ▼  hitl.request → cloud (existing path; HITL is cloud-mediated)
Cloud: a delegation covers (requesting_agent=mailer, action=send_email)?
  │  NO  → normal human fan-out (Slack/Web UI/…)   [unchanged]
  │  YES → route the request to approver_agent "supervisor"
  ▼
Daemon(supervisor): FLOOR check (deterministic) — type∈allow, cost<1.00, path∈allow, sev≤low
  │  floor FAILS → fall through to human
  │  floor PASSES → run supervisor's judgment on the draft
  ▼
supervisor returns approve|deny  →  hitl.resolve {
     resolved_by_type: "agent", resolving_agent_id, delegation_id, policy_rule }
  ▼
Cloud: record + audit (incl. the rule + the draft hash) → deliver decision to mailer
  ▼
Human review feed: "supervisor approved mailer/send_email at 03:14 — [view] [revoke]"
```

### 3.5 Reversibility & human oversight

- **"What your AI approved while you were away"** feed — every delegated approval with the
  authorizing rule, the request, and the outcome.
- **Retroactive revoke + auto-revert window** — a human can undo a delegated approval within
  a configurable window; reversible actions are rolled back, irreversible ones flagged.
- **Circuit breaker** — instant delegation revoke, per-window rate limits, and
  **anomaly auto-disable** (a spike in delegated approvals pauses the delegation).
- **Time/scope-boxed** — delegations expire and are scoped to specific requesting agents.

### 3.6 Data model (cloud)

- **`approval_delegations`** — the envelope in §3.2.
- **`hitl_requests`** gains: `resolved_by_type` (`human|agent`), `resolving_agent_id`,
  `delegation_id`, `policy_rule`, `reverted_at`.
- **`audit_events`** — one per delegated decision + one per human review/override.

---

## 4. Cross-cutting controls (both features)

- **Feature flag**: org-level, **off by default**; org-owner-only to enable; per-feature.
- **Consent gate**: an explicit, plain-language risk screen on first enable and on each
  grant/delegation ("this lets *software* act/approve as you, within these limits").
- **Production exclusion**: agents tagged `production` cannot be orchestration targets,
  orchestrators, approvers, or approval targets, by default.
- **Full audit + lineage**: immutable, optionally hash-chained
  ([cloud-backend §9](cloud-backend.md)); reconstructs every agent-initiated action/approval
  back to the granting human.
- **Kill switches**: "halt orchestration tree" (F1) and "revoke all delegations" (F2),
  plus per-grant/per-delegation revoke — all effective immediately (on reconnect for the
  offline daemon).
- **Anomaly tie-in**: reuse the injection-spike/anomaly detector
  ([cloud-backend §6](cloud-backend.md)) to watch orchestration rate and delegated-approval
  rate; auto-pause on spikes.

---

## 5. Consolidated data-model deltas

| Table | Change |
|-------|--------|
| `agent_identities` | **new** — per-agent machine identity |
| `agent_orchestration_grants` | **new** — signed, attenuated orchestration grant (F1) |
| `approval_delegations` | **new** — approver policy envelope (F2) |
| `runs` | += `initiator`, `initiator_agent_id`, `root_run_id`, `parent_run_id`, `depth` |
| `hitl_requests` | += `resolved_by_type`, `resolving_agent_id`, `delegation_id`, `policy_rule`, `reverted_at` |
| `audit_events` | new event kinds: orchestrate / create / edit / delegated-approval / human-override |

All new tables are **RLS-scoped by `org_id`** like the rest of the schema
([cloud-backend §4](cloud-backend.md)).

---

## 6. New daemon commands / messages

| Direction | Message | Purpose |
|-----------|---------|---------|
| Upstream | `agent.orchestrate` | audit/lineage record of a locally-enforced orchestration call (F1) |
| Downstream | `grant.revoke` | invalidate an orchestration grant (F1) |
| Downstream | `orchestration.halt` | cancel a root run + all descendants (F1) |
| Both | `hitl.request` / `hitl.resolve` | reused — `create`/`edit` gating (F1) and delegated approval (F2) |
| Downstream | `delegation.revoke` | kill an approval delegation (F2) |

---

## 7. Risk register (read before enabling)

| Feature | Worst case | Primary mitigation |
|---------|-----------|--------------------|
| F1 Orchestration | one hijacked agent drives the whole **local** fleet / burns budget | daemon-local only (D1), no-escalation intersection (§2.5), shared tree budget, `create`/`edit` HITL, kill switch |
| F1 self-modification | an agent edits itself/others to gain power | `protected_fields` un-editable, no-escalation, perm-edit is human-only (D2) |
| F2 Approver | AI rubber-stamps a dangerous action; human backstop gone | deterministic floor below the model (D4) ⇒ can't approve past the floor; non-delegable classes; no self-dealing; retroactive revoke |
| F2 escalation | approver grants new authority | **forbidden** — AI permission-editing is off entirely (D2) |
| Both | injection turns a benign agent malicious | §4.5 Layer B screening; daemon-enforced (not model-trusted) limits; anomaly auto-pause; production exclusion |

---

## 8. Open questions / future work

- **Cross-daemon orchestration (post-v1)** — would reintroduce lateral-movement risk and
  require cloud-coordinated lineage/budget across hosts; deferred behind a separate flag and
  per-daemon trust tiers.
- **Quorum / two-key delegated approval** — for a slightly higher non-delegable tier, allow
  an agent proposal + a *second agent or human* co-sign. Not in this design.
- **Grant/delegation marketplaces** — sharing vetted policy envelopes; needs signing + review.
- **Approver judgment provenance** — capturing *why* an approver approved (rationale trace)
  for the review feed.

---

## 9. Promotion checklist — where each feature lands when graduated

When a feature moves from experimental to core, propagate it (the usual all-four-docs +
memory pattern):

- **[tui-daemon.md](tui-daemon.md)** — new component section ("Experimental: Agent
  Orchestration & Delegated Approval"): `orchestrator` capability + tools, local grant
  enforcement in the SQLite WAL, the deterministic-floor approver, kill switches; add
  `agent.orchestrate` to the §4.2 command router.
- **[cloud-backend.md](cloud-backend.md)** — §4 data-model deltas (§5 here); grant minting +
  revocation; async audit ingest; anomaly tie-in; feature-flag/consent gating.
- **[integration.md](integration.md)** — two walkthroughs (agent runs a sibling; approver
  auto-resolves a routine HITL); responsibility-matrix rows; downstream/upstream table entries.
- **[web-ui.md](web-ui.md)** — elevated-grant consent flow; orchestration lineage view +
  "halt tree"; delegation editor (floor + scope + expiry); "what your AI approved" review feed.
- **`.claude/memory/project_overview.md`** — the agents-as-principals model + the four locked
  decisions + experimental/off-by-default framing.

---
---

## 10. Feature 3 — Model Comparison Runs (manual evaluation mode)

> **Independent of §§1–9.** Those sections cover the two delegation features (agents as a
> principal). This is a **separate, lower-risk feature**: a **human-driven testing tool**
> that runs one agent task across several models at once so you can compare them. It does
> **not** introduce a new principal, does **not** act unattended, and — by design — performs
> **no real side effects** until a human chooses a winner. Status: experimental, off by
> default, **API agents only** in v1.

### 10.1 Overview

A human launches a one-off **"Compare models" run** to evaluate how different LLMs handle
the *same* task. The daemon runs the task once per selected model **in parallel** as a
**run group** of **variants**, then the Web UI shows a side-by-side comparison with the
**full per-model telemetry the platform already captures** (cost, tokens, latency, tool
calls, proposed actions, human-intervention points, errors, redaction markers). The human
reviews and **picks the winner**; the winning model can then optionally be re-run **live**.

This is a **benchmarking / regression-testing aid**, not a production execution path: it is
**on-demand only** (not schedulable, not webhook-triggered) and **excluded from
`production`-tagged agents** by default.

```
Human → "Compare models" on agent "triage-bot" → select [claude-opus-4-7, gpt-5, gemini-2-pro]
  ▼
Daemon forks 3 VARIANTS from one pinned context (same prompt, input, tools, ruleset):
  ├─ variant A (claude-opus-4-7)  ─┐
  ├─ variant B (gpt-5)            ─┤  each a normal run: own model adapter, own checkpoint,
  └─ variant C (gemini-2-pro)     ─┘  own cost ledger, own redaction — DRAFT MODE (no real
                                       side effects; HITL simulated)
  ▼
Cloud aggregates the run_group; telemetry streams per variant to the browser
  ▼
Comparison view: 3 columns of {output, cost, tokens, latency, tool calls, proposed
                 actions, "would have paused for HITL" markers, errors} + output diff
  ▼
Human selects winner  →  (optional) live single-model re-run of the winner with real tools
```

### 10.2 Locked design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| E1 | **Manual, on-demand only.** A human starts it to test/compare; never scheduled or unattended. | It's an evaluation tool, not a runtime mode. Keeps the blast radius to "a human chose to spend N× to compare." |
| E2 | **Human picks the winner.** No judge/aggregator LLM, no auto-canonical model. | Simplest and most trustworthy for a test; avoids adding a model whose own judgment must be trusted. |
| E3 | **Draft mode — defer all side effects.** Read-only tools run; side-effecting tools are simulated; HITL is simulated and *recorded* as a data point. | Running N models live would cause N× duplicate side effects (N emails, N pushes). Draft mode makes the comparison safe. |
| E4 | **Promote = optional live re-run of the winner** (fresh single-model run), **not** a replay of simulated steps. | Replaying mocked steps is unsafe (state may have changed; mocked intermediate results may have been wrong). A clean live re-run is correct. |
| E5 | **API agents only (v1).** | `model` is a first-class field for API agents (provider+model). CLI agents (opaque tools) make side-effect interception and "model" selection harder; deferred. |

### 10.3 Fairness — one pinned context, only the model varies

For the comparison to mean anything, every variant must start identical. The daemon **pins
a single context snapshot** for the group and forks all variants from it:

- same **agent version** (prompt/skills/rulesets), same **input**, same **tool set**,
  same **ruleset/blocker + redaction config**, same **env** and `cwd`.
- **Only `[api].provider` + `[api].model` differ** per variant (and the model's own
  defaults — but `max_tokens`/`temperature` are pinned from the agent unless the operator
  explicitly varies them).

Outputs may still diverge legitimately — e.g. a model *chooses* to read a different file or
call a different tool. That divergence is exactly what you're measuring.

### 10.4 Fan-out executor (daemon)

The existing Agent Runtime gains a **group executor**:

1. Resolve the model list; verify provider credentials for each model exist on this daemon
   (§10.9). Build the pinned context snapshot.
2. Compute a **cost estimate per model** and a **group total**; check the group cap (§10.8).
3. Spawn **N variant runs** (bounded by a `max_parallel_variants` concurrency limit), each a
   normal run with its own model adapter, checkpoint/WAL journal, cost ledger, and the
   **draft-mode tool shim** (§10.5) installed.
4. Stream each variant's telemetry up tagged with `run_group_id` + `variant_model`.
5. On completion, mark the group `ready_for_review`. The human selects the winner (§10.7).

### 10.5 Draft-mode tool semantics (the key mechanic)

A **tool shim** sits at the daemon's tool-execution layer for every variant in a comparison
run and classifies each call:

| Tool class | Behavior in draft mode |
|------------|------------------------|
| **Read-only** (fetch, read file, DB `SELECT`, search) | **Execute normally.** No side effect; results feed the model so it can continue realistically. |
| **Side-effecting** (send_email, git push, file write, POST) | **Do not execute.** Record the *intended* call + **redacted args** as a **proposed action**; return a **simulated result** (typed stub, e.g. `{ "status": "ok", "simulated": true }`) so the model proceeds. |
| **HITL-gated** (a ruleset marks it require-approval) | **Do not page a human.** Record *"would have paused for approval here"* with the proposed action; treat as approved-for-simulation so the variant continues. This becomes the **"human intervention necessary"** metric per model. |

This reuses the existing checkpoint **tool-call intent + idempotency** machinery — the
intent is journaled exactly as normal, only the *execution* is suppressed. Each variant
therefore yields a list of **actions it *would* have taken**, fully redaction-screened.

> **Honest caveat (documented in the UI):** once a side-effecting call is mocked, the rest
> of that variant is a **best-effort simulation** — the stubbed result may not match what the
> real action would have returned, so later steps may diverge from real-world behavior. This
> is acceptable for a comparison/test; it is the reason E4 mandates a clean live re-run
> rather than replaying simulated steps.

### 10.6 Per-model data captured (all reused — nothing new to instrument)

Because each variant is an ordinary run, the comparison surfaces **every normal data point
the app already collects**, per model:

- **Final output** (the model's answer / result).
- **Cost** (USD) and **token usage** (in/out).
- **Latency** / wall-clock and step count.
- **Tool calls** — full list with (redacted) args + results, incl. which were read-only.
- **Proposed actions** — the side-effecting calls it *would* have made (draft mode).
- **Human intervention** — count + list of points it *would* have paused for HITL.
- **Errors / failures**, retries, and **redaction markers**.
- **Group aggregate** — total comparison cost, and an **output diff** across variants.

### 10.7 Selecting the winner & promoting it

- The human marks one variant `is_winner`; the **"final output" panel** shows that variant's
  output. The selection + reason are written to the audit log.
- **Optional live promotion (E4):** "Run winner for real" launches a **fresh, single-model,
  normal run** of the winning model on the same task with **live tools + real HITL** — a
  standard run, not a replay. The comparison group itself stays a read-only test artifact.

### 10.8 Cost controls

N models ≈ up to **N× spend**, so:

- **Pre-launch estimate** per model + **group total**, shown before the user confirms.
- A **group-level aggregate cost cap** (hard-stops the whole group) on top of the existing
  per-run `max_cost_usd` applied to **each** variant.
- `max_parallel_variants` bounds concurrency (resource + rate-limit friendliness).

### 10.9 Model selection — what's offered

- The multi-select lists models **whose provider credentials are available on the agent's
  daemon** (per-agent or shared env-var set, [tui-daemon §4.10](tui-daemon.md)) — you can't
  compare a model you have no key for on that host.
- Spans all configured providers (Anthropic / OpenAI / Google / OpenRouter / custom).
- Each entry shows the per-model **price estimate** for this task so the cost trade-off is
  visible at selection time.

### 10.10 Data model (mostly reuse)

| Table | Change |
|-------|--------|
| **`run_groups`** | **new** — `group_id`, `agent_id`, `agent_version`, pinned `input`, `selected_models[]`, `status` (`running`/`ready_for_review`/`closed`), `winner_run_id`, `total_cost_usd`, `created_by`, `created_at` |
| `runs` | += `run_group_id`, `variant_model`, `is_winner`, `mode` (`normal`/`comparison_variant`) |
| `tool_calls` | += `simulated` (bool) + `proposed_action` flag, so dry-run side effects are distinguishable from executed ones |
| `hitl_requests` | += `simulated` (bool) — a "would have paused" marker carries no real gate |
| `audit_events` | new kinds: comparison-launched, winner-selected, winner-promoted-live |

Every variant is a normal `run`, so `tool_calls`, telemetry, cost, checkpointing tables are
otherwise unchanged — this is the cheapness of the feature.

### 10.11 New commands / config

- **Downstream** (cloud → daemon): `agent.compare { agent_id, models[], input, group_id,
  group_cost_cap, max_parallel_variants }` — launches the group.
- **Downstream**: `comparison.cancel { group_id }` — stop all variants.
- **Upstream**: variants stream over the existing telemetry channel tagged with
  `run_group_id` / `variant_model`; group status rides the control channel.
- The winner's optional live run is just an ordinary `agent.run` with a single pinned model.

### 10.12 Web UI

- **Launcher** — on an API agent: "Compare models" → a **model multi-select** (grouped by
  provider, each with a per-model cost estimate + a running group-total), an optional cap
  override, then **Run comparison** (with a clear N× cost confirmation).
- **Comparison screen** — one **column per model**: output, cost, tokens, latency, the full
  tool-call list, the **proposed-actions** list, **"would have paused for HITL"** markers,
  and errors. Plus a **side-by-side output diff** and sortable summary (cheapest / fastest /
  fewest interventions). A banner notes draft-mode's best-effort-simulation caveat (§10.5).
- **Select winner** → marks the variant and reveals **"Run winner for real"** (E4).
- Comparison groups appear in run history as a single expandable group.

### 10.13 Risk notes (low, but not zero)

| Concern | Mitigation |
|---------|------------|
| **N× cost surprise** | pre-launch per-model + total estimate, hard group cap, N× confirmation, manual-only (E1) |
| Operator assumes draft output == real behavior | explicit best-effort-simulation caveat in UI + audit; E4 mandates a clean live re-run to actually act |
| Duplicate side effects from parallel models | **draft mode** simulates all side-effecting + HITL calls (E3) — nothing real happens during a comparison |
| Provider rate limits / resource spikes from fan-out | `max_parallel_variants` concurrency bound |
| Comparing models you lack keys for | selection limited to models with credentials on the daemon (§10.9) |

### 10.14 Open questions / future

- **CLI agents** — comparison where the CLI exposes a model flag; needs a side-effect
  interception story for opaque CLI tools (deferred per E5).
- **Optional auto-scoring** — a later, opt-in judge/aggregator for unattended eval suites
  (explicitly *not* in v1; E2 keeps the human in the loop).
- **Saved comparison suites** — re-run the same task across a fixed model panel over time to
  track regressions; would relax E1's "manual only" for a vetted eval harness.
- **More than output diff** — semantic/grading rubrics, not just textual diff.

### 10.15 Promotion checklist — where this lands when graduated

- **[tui-daemon.md](tui-daemon.md)** — Agent Runtime gains the **group executor** + the
  **draft-mode tool shim**; add `agent.compare` / `comparison.cancel` to the §4.2 command
  router; note variant telemetry tagging.
- **[cloud-backend.md](cloud-backend.md)** — §4 data model: `run_groups` + the `runs` /
  `tool_calls` / `hitl_requests` flags; group aggregation + winner selection; cost-estimate
  endpoint; manual-only + production-exclusion gating.
- **[integration.md](integration.md)** — a walkthrough (launch comparison → draft variants →
  review → select winner → optional live re-run); a responsibility-matrix row; the
  `agent.compare` downstream + tagged-telemetry upstream entries.
- **[web-ui.md](web-ui.md)** — the Compare-models launcher (multi-select + cost estimate),
  the comparison screen (per-model columns + diff + proposed-actions + HITL markers), and
  winner selection / promote-to-live.
- **`.claude/memory/project_overview.md`** — the comparison-run model + decisions E1–E5
  (manual-only, human-picks-winner, draft mode, live-rerun promote, API-only).

---

## 11. Feature 4 — Native Handoff Protocol — GRADUATED ✅

> **Graduated to core (2026-06-12).** Implemented end-to-end and merged to `main` (PR #60):
> schema migration `0019_native_handoff`, the cloud chain-grant signing router
> (`synapse_cloud/routers/handoff.py` + `chain_crypto.py`), the daemon handoff
> broker/runner/MCP (`synapse_worker/handoff/`), and the visual **Flow Canvas** Web UI
> (`synapse_web/src/screens/flow/`). It is no longer an experimental design note. Per the
> promotion checklist the canonical specs now live in the core docs
> ([web-ui.md](web-ui.md), [cloud-backend.md](cloud-backend.md), [tui-daemon.md](tui-daemon.md))
> and `.claude/memory/native_handoff_feature.md`. It remains off-by-default behind the §4
> org-level feature flag + consent gate.

---

## 12. Feature 5 — Behavioral Drift & Intent Monitoring (SAFETY feature — experimental)

> **This one *reduces* risk; it does not bend an invariant.** Unlike §§1–4 (which introduce a
> new principal) and §10 (which spends N×), this is **proactive security**: it watches whether
> an agent is *doing what it was asked to do*, and gates **high-blast-radius tool calls on the
> conversation's actual intent** — not just on static permissions. It **extends** the §4.5
> Input/Output Filtering middleware and the §4.6 Ruleset Engine; it is **off by default**
> because its value depends on classifier accuracy (false positives can strangle legitimate
> work) and it adds latency. Critically, it keeps the platform's trust model: **the AI
> *detects*, the daemon *enforces*** — a monitoring miss can never *grant* authority, only
> add friction.

### 12.1 Overview — two pillars

Traditional observability catches **errors**; this catches **divergence of intent**. Two
cooperating mechanisms run on the daemon:

- **Pillar A — Intent-Drift Detection.** Each agent has a **declared-intent envelope**
  (derived from its system prompt + an operator-confirmed allow-list of intent categories).
  When the agent's *observed behavior* leaves that envelope — system prompt says "summarize
  documents," but it starts "searching for external files" — the daemon raises an
  **intent-drift finding**, mapped to a Ruleset action (warn / require-HITL / block).
- **Pillar B — Context-Aware Tool Guardrails.** Beyond PII redaction (§4.5 Layer A) and static
  allow/deny blockers (§4.6): every tool is tagged with a **blast-radius class**, and a
  **destructive-class** call (e.g. `delete_database`) requires **just-in-time, action-scoped
  human authorization in *this* conversation** — *regardless of static permissions*. If the
  human hasn't explicitly authorized **that specific destruction**, the daemon blocks it.

```
Agent "summarizer" (declared envelope: {read_docs, summarize, web_search})
  │
  ├─ tool call: read_file(report.md)          ── in-envelope, read-only ──► run
  │
  ├─ tool call: search_external_fs("*.key")   ── OUT of envelope ──► Pillar A
  │     drift signal: action category ∉ declared envelope
  │     → finding{intent_drift, sev=med} → Ruleset action = require-HITL
  │
  └─ tool call: delete_database("prod")        ── DESTRUCTIVE class ──► Pillar B
        check: explicit in-conversation authorization for deleting "prod"?  NO
        check: destructive ∈ declared envelope?                            NO
        → BLOCK (or require fresh human approval), regardless of static allow
        → finding{unauthorized_destructive_call} → immutable audit + cloud anomaly
```

### 12.2 Locked design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| G1 | **AI detects, the daemon enforces.** Classification may be AI-assisted (heuristics + local signatures + optional **local Ollama** classifier, like §4.5 Layer B), but the **enforcement action maps to the deterministic Ruleset Engine**. | A successful prompt-injection still can't disable the guardrail — the block lives below the model. Same trust model the rest of the platform relies on. |
| G2 | **Guardrails can only *add* friction, never remove a control.** Intent checks may escalate (warn → require-HITL → block); they can **never grant** a capability the static ruleset denies. | A wrong/compromised classifier degrades to **over-blocking** (annoying), never **under-blocking** (dangerous). Same safety property as §3's deterministic-floor (D4). |
| G3 | **On-device detection; cloud baselines only.** Detection runs on the daemon over local content; only **redacted findings** (category/severity/action/excerpt — never raw content) leave for the cloud's cross-run **drift anomaly detector**. | Preserves on-device-redaction; reuses the §4.5 injection-attempt anomaly infrastructure. |
| G4 | **Destructive tools require just-in-time, action-scoped authorization.** A destructive-class call is gated by *"did a human explicitly authorize **this** action in **this** run?"* — independent of, and on top of, the static allow/deny blocker. | This is the `delete_database` story: a blanket "tools allowed" never blesses an irreversible action. Authorization is **scoped to the target/args**, not the tool in general. |
| G5 | **The declared intent envelope is operator-confirmed, not model-self-declared.** Derived from the agent spec, but a **human edits/confirms** the allowed intent categories and per-tool blast-radius classes. | You don't let the model define its own boundaries. Keeps "intent" a concrete operator artifact, not a vibe. |
| G6 | **Fail-safe on monitor failure.** If the classifier is unavailable (Ollama down/timeout), **destructive-class gating falls back to require-HITL** and drift detection degrades to **warn + log** — losing the AI never *opens* a gate. | Availability of the monitor must not become a way to bypass it. |

### 12.3 The declared-intent envelope (where "intent" comes from)

A concrete, operator-owned artifact per agent (over an org default), **not** an inference the
model makes about itself:

- **Purpose statement** — a short natural-language description (often the system-prompt
  mission) used by the semantic classifier.
- **Allowed intent categories** — an explicit allow-list, e.g. `{read_docs, summarize,
  web_search}`; anything outside is drift. Categories are a **bounded taxonomy** (read,
  search, summarize, code-exec, file-write, external-upload, deletion, payment, …), not
  free-form.
- **Tool blast-radius class map** — every tool/MCP tool classified: **read-only** /
  **mutating** / **destructive** (irreversible external effect) / **exfiltrating** (sends data
  off-box). Defaults inferred from tool metadata, **human-confirmed** (G5).
- **Sensitivity** — per-agent drift sensitivity + the per-class destructive policy
  (block / require-HITL / warn).

### 12.4 Pillar A — Intent-Drift Detection

A daemon monitor scores each step against the envelope and the agent's own history:

| Signal | Example | Source |
|--------|---------|--------|
| **Category out-of-envelope** | declared `{summarize}`, agent calls `search_external_fs` (category `search`/`file-read` not allowed) | deterministic (category ∉ allow-list) — **fast path, inline** |
| **Goal divergence** | recent action trajectory drifts semantically from the purpose statement | semantic similarity (local classifier) — **off hot path** |
| **Trajectory anomaly** | sudden shift in this agent's tool-call distribution vs its historical baseline | **cloud** drift anomaly detector (G3) |

Findings carry `{category, severity, signal, redacted_excerpt}` and map to a **Ruleset
action** (warn / require-HITL / block) exactly like a §4.5 finding. **Default posture is
observational** (warn + log) so normal exploration isn't strangled; blocking is reserved for
**high-confidence + high-blast-radius** drift (operator-tunable). The deterministic category
check is **inline/blocking-capable**; expensive semantic scoring runs **alongside** the step,
not in the latency-critical path.

### 12.5 Pillar B — Context-Aware Tool Guardrails

When any tool is invoked, the daemon's guardrail (sitting just below the §4.6 blocker check)
inspects the **blast-radius class**:

- **read-only / mutating** → governed by the existing §4.6 ruleset as today.
- **destructive / exfiltrating** → **intent-conditioned just-in-time gate** (G4):
  1. **Action-scoped authorization?** Is there an **explicit, recent, in-conversation** human
     authorization matching **this target/args** (e.g. "yes, delete the `prod` database")? A
     prior approval of a *different* destructive call does **not** count — authorization is
     scoped to the specific action, and approving once never blesses all future calls.
  2. **In declared envelope?** Does the action's category fall inside the agent's allowed
     intent (§12.3)?
  3. If **either fails** → **block**, or surface a **HITL approval** showing the *proposed*
     action with **redacted args** ("agent wants to `delete_database(prod)` — approve?"). The
     human's approval is recorded as the action-scoped authorization for step 1.

This is the `delete_database` scenario: even if a static blocker would *allow* tool execution,
an **unauthorized, out-of-intent destruction is blocked anyway** — proactive, not reactive.

### 12.6 Trust model & layering (how it sits with §4.5 / §4.6)

This adds a **third gating axis**, orthogonal to what already exists — think of it as
**§4.5 "Layer C — behavioral/intent guard"** feeding the same finding→action pipeline:

| Layer | Question it answers | Already exists? |
|-------|--------------------|-----------------|
| §4.5 **Layer A** | Does this content contain secrets/PII to redact? | yes |
| §4.5 **Layer B** | Is this content a prompt-injection/jailbreak attempt? | yes |
| §4.6 **Ruleset** | Is this tool/path/host/cost statically allowed? | yes |
| **§12 Layer C** | Is this action **consistent with the agent's declared intent** and **explicitly authorized** for this conversation? | **new** |

All four are **enforced by the daemon** and emit findings into the **same immutable audit log
+ cloud anomaly pipeline**. Layer C never overrides the others' *denials* (G2); it only
contributes additional blocks/HITL. It is **defense-in-depth, not a replacement** for the
deterministic blockers — the static ruleset remains the floor.

### 12.7 Cloud role — cross-run baselining

The cloud reuses the §4.5 injection-anomaly infrastructure: it baselines **per-agent
behavior** (tool-call distribution, drift-finding rate), alerts on **drift spikes**, and can
**auto-pause** an agent whose behavior diverges sharply from its history — the same
mechanism that watches injection attempts, now watching intent drift. Cloud sees **redacted
findings only** (G3).

### 12.8 Data model

| Table | Change |
|-------|--------|
| **`agent_intent_profiles`** | **new** — declared purpose, allowed intent categories, per-tool blast-radius class map, sensitivity + destructive policy; per-agent over an org default (operator-set, G5) |
| `filter_findings` (the §4.5 findings/audit log) | **reuse** — new kinds: `intent_drift`, `unauthorized_destructive_call`; carries `{category, severity, signal, action, redacted_excerpt, run_id}` |
| `tool_calls` | += `blast_radius_class`, `intent_authorized` (bool), `drift_score` |
| `agent_behavior_baselines` | **new (cloud)** — per-agent tool-distribution + drift-rate rollups for the anomaly detector (reuse of §4.5 anomaly infra) |

No new transport primitive: findings stream up over the existing **telemetry channel**
(as §4.5 findings already do); auto-pause rides the **control channel**.

### 12.9 New surface (mostly config + reuse)

- **Config** (cloud → daemon via existing agent-config sync): the `agent_intent_profiles`
  entry (envelope + tool class map + sensitivity).
- **HITL**: destructive-call approvals reuse the **existing §4.x HITL approve/deny path**,
  carrying the **proposed action** (redacted) — no new approval mechanism.
- **No new agent-facing tools.** The agent doesn't call anything; the monitor is ambient.

### 12.10 Web UI

- **Intent profile editor** (per-agent, on the agent's Tools/Security tab, over an org
  default): purpose statement, allowed-category allow-list, the **tool blast-radius
  classifier** (read-only / mutating / destructive / exfiltrating), drift sensitivity, and the
  destructive-tool policy (block / require-HITL / warn).
- **Drift timeline** in **Logs (§4.10)** + **Alerts (§4.13)**: intent-drift findings,
  just-in-time authorization prompts, and **blocked destructive calls**, each with the
  redacted proposed action and the Ruleset action taken.
- **Approval surface**: a destructive-class HITL shows *"agent wants to `delete_database(prod)`
  — this is outside its declared intent and unauthorized in this run. Approve once?"*

### 12.11 False-positive & latency controls (the real risks of *this* feature)

| Concern | Control |
|---------|---------|
| Drift detection strangles legitimate exploration | **observational-by-default** (warn+log); blocking only for high-confidence + high-blast-radius drift; per-agent **sensitivity** tuning |
| Recurring false positives | operator can mark a flagged behavior **"expected"** → widens the declared envelope (a feedback loop, not a fixed wall) |
| Latency on every tool call | **fast deterministic category/class check inline**; expensive **semantic** scoring runs **off the hot path**, alongside the step |
| Operator over-trusts the monitor | documented as **defense-in-depth**, *not* a replacement for static blockers (G2); the deterministic ruleset remains the floor |

### 12.12 Risk notes

| Concern | Mitigation |
|---------|------------|
| Classifier wrong or injected | **G1/G2** — daemon enforces, can only *add* friction; degrades to over-blocking, never under-blocking |
| Monitor unavailable used to bypass it | **G6** fail-safe — destructive gating falls back to require-HITL; drift degrades to warn+log; the gate never opens |
| "Intent" is fuzzy / unfalsifiable | **G5** — envelope is an operator-set artifact with a bounded category taxonomy; destructive gating is **class-based deterministic**, not purely semantic |
| Raw conversation content leaking to cloud | **G3** — only redacted findings leave; baselining is on distributions, not content |

### 12.13 Open questions / future

- **Drift across a §11 handoff chain** — does the envelope travel with the baton, or does each
  agent keep its own? (Likely each agent enforces its own envelope; the chain-level view is a
  cloud rollup.)
- **Learned baselines vs. static envelopes** — auto-proposing an envelope from observed "known
  good" runs, with human confirmation (still G5).
- **Standard taxonomies** — a shared, versioned set of intent categories + blast-radius
  classes so policies are portable across agents/orgs.
- **Classifier calibration** — a local eval harness for drift-detection precision/recall before
  an org turns on blocking mode.

### 12.14 Promotion checklist — where this lands when graduated

- **[tui-daemon.md](tui-daemon.md)** — extend §4.5 with **Layer C (behavioral/intent guard)**
  + Pillar B's class-based just-in-time gate below the §4.6 blocker check; the on-device
  monitor (heuristics + optional local Ollama); `tool_calls` class/authorization fields; G6
  fail-safe.
- **[cloud-backend.md](cloud-backend.md)** — `agent_intent_profiles`, the new `filter_findings`
  kinds, `agent_behavior_baselines`, and the drift anomaly detector / auto-pause (reuse of the
  §4.5 anomaly pipeline).
- **[integration.md](integration.md)** — a walkthrough (drift flagged → HITL; destructive call
  blocked for lack of in-conversation authorization → approve-once); a responsibility-matrix
  row; findings ride the existing telemetry channel, auto-pause rides the control channel.
- **[web-ui.md](web-ui.md)** — the intent-profile editor (envelope + tool blast-radius
  classifier + sensitivity), the drift timeline in Logs §4.10 / Alerts §4.13, and the
  action-scoped destructive-approval surface.
- **`.claude/memory/project_overview.md`** — the intent-monitoring model + decisions G1–G6
  (AI detects/daemon enforces, friction-only, on-device + cloud baseline, action-scoped
  just-in-time authorization for destructive tools, operator-set envelope, fail-safe).

---

## 13. Feature 6 — Enterprise SSO sign-in (SAML / OIDC + SCIM)

> **ENTERPRISE — security-sensitive, not high-risk-experimental.** Unlike §§1–4 (which add a
> new principal) or §10 (which spends N×), this does **not** bend a platform invariant — it
> changes **how a human session is authenticated**, and leaves **authorization untouched**
> (the org/membership/role model from Members & RBAC stays the floor). It is **off by default**,
> **owner-only** to configure, and scoped per org. The whole design rests on one rule:
>
> > **SSO authenticates; it never authorizes.** The identity provider proves *who the human is*;
> > Synapse alone decides *what they may do* via `memberships.role` and RLS. An IdP claim can
> > never directly mint an `admin`/`owner` — role grants stay a human-confirmed action.

### 13.1 Why this exists & what it builds on

Today a human signs in with **Supabase Auth email/password**, gated by the Web UI's
**`AuthGate`** (`RequireSession` in [web-ui.md](web-ui.md)); the session's JWT identifies the
user and authorization is resolved from **`memberships`** via `user_org_ids()` / RLS
([cloud-backend §4](cloud-backend.md)). Enterprises require their workforce identity provider
(Okta, Entra ID/Azure AD, Google Workspace, Ping, JumpCloud…) to be the single source of
truth: one place to grant/revoke access, MFA enforced centrally, no per-tool passwords. This
feature adds **SAML 2.0 / OIDC SSO** and **SCIM 2.0** lifecycle on top of the existing auth,
reusing Supabase Auth's enterprise SSO rather than building a bespoke auth server.

It is the natural successor to the just-shipped **Members & RBAC + `org_invitations`** work:
manual email invites become **automatic, IdP-governed provisioning**, while the role model
and RLS they introduced stay exactly as-is.

### 13.2 Locked design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| S1 | **Delegate authentication to the org's IdP via Supabase Auth SSO** (SAML 2.0) **/ OIDC**; never build a bespoke auth server, never see the user's IdP password. | Reuses the platform's existing auth substrate; inherits MFA/conditional-access from the IdP; smallest new attack surface. |
| S2 | **Authn only — authorization is unchanged.** SSO mints the session; the JWT still identifies the user and RLS still derives org/role from `memberships`. SSO config never touches a policy. | Keeps the one trust boundary intact: a misconfigured/compromised IdP mapping can grant *login*, never *elevated authority*. Mirrors the §3 "deterministic floor" property for auth. |
| S3 | **JIT provisioning is bounded to the lowest role.** First SSO login auto-creates the `users` row + a `memberships` row at a **default role (viewer)** only; elevation stays an admin action (or an explicit, admin-confirmed group→role map, S6). | An IdP claim must never self-elevate. Closes the "attacker who controls a group claim becomes admin" hole. |
| S4 | **Domain-verified org routing.** An org claims one or more **verified email domains**; a sign-in email matching a claimed domain is routed to that org's SSO connection. Domain ownership must be **DNS-verified** before it routes. | Prevents org-hijack by email-domain spoofing; deterministic which IdP handles a given user. |
| S5 | **"Require SSO" is enforceable per domain, with break-glass.** Once an org enables enforcement, password sign-in for users on its claimed domains is **disabled** (no backdoor) — except a small, audited set of **break-glass owner accounts** exempt by design. | Enterprises need "everyone goes through the IdP" to be real, but a fully-locked org that loses its IdP must not be permanently bricked. |
| S6 | **Group→role mapping is explicit and admin-confirmed; SCIM deprovision is immediate.** IdP groups map to Synapse roles only through a mapping an **admin sets** (never raw claim trust); SCIM (or IdP removal) **revokes the membership immediately** and ends daemon-relayed sessions on next reconnect. | Joiner/mover/leaver lifecycle lives in the IdP (the enterprise requirement), but the *meaning* of a group is owner-defined, and offboarding is prompt and auditable. |

### 13.3 Sign-in flow

```
Human opens Synapse Web UI → AuthGate (no session)
  │  enters work email  ──►  domain lookup against verified org_domains
  │     no match  → normal Supabase email/password (unchanged)
  │     match     → org has an SSO connection → "Sign in with <Org IdP>"
  ▼
Supabase Auth SSO: redirect to the org's IdP (SAML 2.0 AuthnRequest / OIDC authorize)
  │     IdP authenticates (password + MFA + conditional access — all the enterprise's own)
  ▼
IdP POSTs SAML assertion / OIDC code back → Supabase Auth verifies signature, mints a session
  ▼
Cloud post-sign-in hook (JIT, S3):
  │  users row upsert (id = auth uid, email, display_name from assertion)
  │  membership exists for the routed org?
  │     YES → leave role as-is (SSO never changes an existing role)
  │     NO  → create membership at DEFAULT role = viewer   (+ apply admin-confirmed
  │           group→role map if configured, S6; never above the map's ceiling)
  ▼
AuthGate sees a session → app loads; RLS resolves org/role from memberships exactly as today
```

A returning user with a live membership simply lands in the app; the JIT step is a no-op
except refreshing `display_name`. **An expired/revoked IdP account cannot mint a session at
all** (the IdP refuses) — and SCIM/deprovision (S6) removes the membership so even a cached
token resolves to zero rows under RLS.

### 13.4 JIT provisioning & the invitation path (how they coexist)

- **SSO JIT replaces manual invites for governed domains.** Where `org_invitations`
  (the shipped invite-by-email) is a human pulling someone in one at a time, SSO JIT is the
  IdP pushing the whole eligible workforce — anyone who can authenticate against the org's IdP
  and matches a claimed domain is provisioned on first login.
- **Invitations still work for non-SSO / cross-domain guests** (e.g. an external contractor on
  a different email domain): an explicit `org_invitations` row, unchanged.
- **No double-provisioning:** JIT upserts on `(org_id, user_id)`; a pre-existing invite for the
  same email is marked `accepted` when the SSO user lands.

### 13.5 Group → role mapping (bounded, S6)

```jsonc
// org_sso_connections.role_mapping  (admin-confirmed; absent ⇒ everyone lands at viewer)
{
  "default_role": "viewer",                 // S3 floor for anyone not matched below
  "claim": "groups",                         // the IdP claim/attribute to read
  "rules": [
    { "group": "synapse-admins",    "role": "admin"    },
    { "group": "synapse-operators", "role": "operator" }
  ],
  "ceiling": "admin"                         // SSO can never auto-grant 'owner' (S3)
}
```

- The mapping is **edited and confirmed by an org admin** — raw IdP claims are never trusted to
  assign a role on their own (S6).
- **`owner` is never SSO-assignable** — ownership transfer stays a deliberate in-app action.
- On each login the role is **re-evaluated only upward to the mapped value if the org opts into
  "sync role from IdP"**; by default SSO **never downgrades or changes an existing role** (S2) —
  role changes flow through Members & RBAC, keeping one audit story for elevation.

### 13.6 SCIM 2.0 lifecycle (opt-in, S6)

SCIM is **not** native to Supabase Auth, so it is a **Synapse Cloud Backend endpoint**
(`/scim/v2/Users`, `/scim/v2/Groups`) authenticated by a **per-org SCIM bearer token**:

- **Provision/Update** → upsert `users` + `memberships` (role via the §13.5 map).
- **Deprovision** (IdP disables/removes a user) → **immediately revoke** the membership and
  flag any daemon-relayed sessions for that user to end on next reconnect (reuses the existing
  daemon revoke path, [cloud-backend §…](cloud-backend.md)).
- **Group sync** → keeps `synapse-admins`/`synapse-operators` membership in step with the IdP,
  still through the admin-confirmed map (never raw).

SCIM is **off by default** and independent of interactive SSO — an org can run SSO-only (JIT on
login) without SCIM, or add SCIM for full joiner/mover/leaver automation.

### 13.7 "Require SSO" enforcement & break-glass (S5)

- When enabled, **password sign-in is rejected for any email on the org's verified domains** —
  the AuthGate offers only "Sign in with <IdP>". This is the enterprise "no local passwords"
  requirement made real.
- **Break-glass:** a small, explicitly-flagged set of **owner** accounts (`break_glass = true`)
  remain password-capable (ideally with their own MFA), so an org whose IdP outage or
  misconfiguration would otherwise lock everyone out can still recover. Every break-glass login
  is **audited and alertable**.
- Enforcement is an **org setting**, owner-only, with a confirmation screen spelling out the
  lockout/break-glass implications.

### 13.8 Trust model & layering (how it sits with the existing auth)

| Layer | Question it answers | Changes here? |
|-------|--------------------|---------------|
| **AuthGate / Supabase Auth** | Is there a valid session, and who is the user? | **extended** — session can now be minted via SAML/OIDC, not just password |
| **JIT / SCIM provisioning** | Should this authenticated human have a membership, and at what *floor* role? | **new** — bounded to viewer + admin-confirmed map (S3/S6) |
| **`memberships` + RLS** (Members & RBAC) | What may this user do in this org? | **unchanged** — still the sole authorization source |

SSO/SCIM only ever **create or remove a membership and set its floor role**; they never write a
policy, never touch RLS, and never grant `owner`. Authorization remains exactly the model the
Members & RBAC work established.

### 13.9 Data model (cloud)

| Table | Change |
|-------|--------|
| **`org_sso_connections`** | **new** — per-org IdP config: `protocol` (`saml`/`oidc`), Supabase SSO provider id, metadata/issuer/ACS, `role_mapping` (§13.5), `enforce_sso` (bool), `created_by`, timestamps. **No IdP secrets in plaintext** — signing certs/metadata only; client secrets live in the secret store. |
| **`org_domains`** | **new** — `org_id`, `domain`, `verified_at`, DNS `verification_token`; routes a sign-in email to an org's SSO connection (S4). Unique on `domain`. |
| **`scim_tokens`** | **new** — per-org SCIM bearer token (**hashed**), `scopes`, `last_used_at`, `revoked_at` (S6). |
| `users` | += `auth_source` (`password`/`saml`/`oidc`/`scim`) for provenance/audit. |
| `memberships` | += `provisioned_via` (`manual`/`invitation`/`sso_jit`/`scim`), `idp_external_id`, `break_glass` (bool, S5). |
| `audit_events` | new kinds: `sso_login`, `sso_jit_provision`, `scim_provision`, `scim_deprovision`, `break_glass_login`, `sso_enforcement_changed`. |

All org-scoped tables are **RLS-scoped by `org_id`** like the rest of the schema; `scim_tokens`
and IdP secrets are **service-role-only** (never readable by `authenticated`).

### 13.10 New surface / endpoints

| Surface | Purpose |
|---------|---------|
| Supabase Auth SSO (SAML/OIDC) | the IdP redirect + assertion verification + session mint (reused, not built) |
| Cloud post-sign-in hook | JIT upsert of `users` + `memberships` at the floor role (§13.3) |
| `POST /scim/v2/Users`, `/scim/v2/Groups` (+ PATCH/DELETE) | SCIM lifecycle, per-org bearer token (§13.6) |
| `GET /sso/route?email=` | domain→connection lookup the AuthGate calls to decide password vs SSO (S4) |
| `org_domains` DNS verification | TXT-record challenge to prove domain ownership before routing |
| Daemon revoke (reused) | SCIM deprovision ends a user's daemon-relayed sessions on reconnect |

### 13.11 Web UI

- **AuthGate** gains an email-first step: enter work email → if the domain is SSO-governed,
  show **"Sign in with <Org IdP>"** (and, when `enforce_sso`, *hide* the password field);
  otherwise the existing password form. (`synapse_web/src/lib/auth.tsx`.)
- **Settings → Authentication** (new sub-tab, owner-only, next to **Members & RBAC** / **Teams**):
  - **SSO connection** — pick SAML or OIDC, paste IdP metadata / configure OIDC, test the
    connection, see the ACS/entity-id to hand back to the IdP admin.
  - **Domains** — add a domain, show the DNS TXT challenge, verify, list verified domains.
  - **Role mapping** — the admin-confirmed group→role table (§13.5), with the `owner` ceiling
    enforced in the UI.
  - **Require SSO** toggle with the break-glass explainer (S5).
  - **SCIM** — generate/rotate/revoke the SCIM bearer token; show the SCIM base URL.
- **Members & RBAC** rows gain a provenance chip (`SSO` / `SCIM` / `invited` / `manual`) and a
  **break-glass** badge, so an admin can see *how* each member got in.

### 13.12 Risk notes

| Concern | Mitigation |
|---------|------------|
| IdP/claim compromise grants elevated access | **S2/S3** — SSO authenticates only; JIT floor is `viewer`, `owner` never SSO-assignable, group→role is admin-confirmed (S6), not raw-claim-trusted |
| Email-domain spoofing hijacks an org | **S4** — domains must be **DNS-verified** before routing; `org_domains.domain` is globally unique |
| IdP outage / misconfig locks everyone out | **S5** break-glass owner accounts (audited) + an owner-only enforcement toggle with a clear warning |
| Offboarded user retains access | **S6** — SCIM/IdP removal revokes the membership immediately; even a cached JWT resolves to zero rows (RLS) and daemon sessions end on reconnect |
| SCIM token leakage | token **hashed at rest**, scoped, rotatable/revocable, service-role-only; all SCIM ops audited |
| SSO silently changes a role unexpectedly | default is **never change an existing role** (S2); "sync role from IdP" is explicit opt-in and capped by the mapping ceiling |
| SAML assertion replay / signature bypass | handled by **Supabase Auth's** SSO verification (reused, not hand-rolled); we never parse raw assertions ourselves |

### 13.13 Open questions / future

- **Multiple IdPs per org** (e.g. post-merger two directories) — connection precedence + domain
  partitioning.
- **SCIM-driven team membership** — map IdP groups straight onto the §-team hierarchy
  (Teams), not just roles, so org structure mirrors the directory.
- **Per-daemon / device-bound SSO step-up** — require a fresh IdP assertion before a
  high-blast-radius action (ties to §12's destructive gate).
- **Just-in-time *de*-provisioning latency** — webhook-based instant revoke vs SCIM polling.
- **SSO for the TUI device-login flow** — today device-code auth ([integration.md](integration.md))
  assumes an interactive browser session; routing it through the org IdP.

### 13.14 Promotion checklist — where this lands when graduated

- **[cloud-backend.md](cloud-backend.md)** — `org_sso_connections` / `org_domains` /
  `scim_tokens` + the `users`/`memberships`/`audit_events` deltas (§13.9); the post-sign-in JIT
  hook; the SCIM 2.0 endpoints + per-org token auth; domain DNS verification; `enforce_sso`
  gating + break-glass; service-role-only handling of IdP/SCIM secrets.
- **[web-ui.md](web-ui.md)** — the email-first **AuthGate** (password vs "Sign in with IdP",
  hidden password under enforcement); the owner-only **Settings → Authentication** sub-tab
  (connection + domains + role map + require-SSO + SCIM token); member provenance/break-glass
  chips in Members & RBAC.
- **[integration.md](integration.md)** — a walkthrough (admin configures SAML → verifies domain →
  user signs in via IdP → JIT membership at viewer → SCIM deprovision revokes); a
  responsibility-matrix row (IdP authenticates / Synapse authorizes); the `/scim/v2/*` +
  `/sso/route` surface and reuse of the daemon revoke path.
- **[tui-daemon.md](tui-daemon.md)** — only if SSO step-up or SSO device-login is adopted
  (§13.13); otherwise the daemon is unaffected (SSO changes session minting, not execution).
- **`.claude/memory/project_overview.md`** — the SSO model + decisions S1–S6 (delegate authn to
  the IdP via Supabase Auth, authn-only/authorization-unchanged, viewer-floor JIT,
  DNS-verified domain routing, require-SSO + break-glass, admin-confirmed group→role + immediate
  SCIM deprovision).

