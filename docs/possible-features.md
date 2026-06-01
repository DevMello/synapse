# Possible / Experimental Features

> **Status: EXPERIMENTAL — design only, not in the MVP.** Everything in this document is
> **off by default**, gated behind an org-level feature flag and an explicit consent
> screen, **excluded from `production`-tagged agents**, and enabled only by an org owner.
> These features deliberately bend assumptions the rest of the platform relies on, so each
> ships with its blast-radius controls *first*. Last updated 2026-05-31.

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
  agent → its daemon → outbound gRPC → cloud broker → target. The cloud still brokers.
- **Cloud never executes agents / holds raw secrets** — execution stays on the daemon;
  the cloud authorizes/audits/orchestrates only.
- **Daemon is outbound-only** — agents ride the existing daemon-initiated gRPC `Connect`
  stream; no inbound port is opened.

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

## 2. Feature 1 — Agent Orchestration (HIGH RISK)

*An agent can run other agents on its own daemon, and create/edit agents on its own daemon.*

### 2.1 Overview

An agent gains a built-in **`orchestrator`** capability whose tools translate into
**upstream control requests** rather than local execution. The daemon enforces a signed
grant locally, the cloud records the full lineage, and the dangerous verbs
(`create`/`edit`) default to human approval.

```
Agent "planner" (daemon macbook-01)
  │  calls tool: synapse.run_agent("researcher", input)
  ▼
Daemon orchestration broker (LOCAL)
  │  1. verify grant (signed, cached) covers verb=run, target=researcher, same daemon
  │  2. check depth < max_depth, fan_out < max_fan_out, tree_budget remaining
  │  3. compute effective perms = researcher.perms ∩ grant.scope   (no-escalation)
  │  4. append lineage row to SQLite WAL (root/parent/depth), decrement budget
  │  5. start the child run locally  ── OR ──  pause for HITL if verb ∈ {create, edit}
  ▼
  child run executes on the SAME daemon; telemetry streams to caller (tool result)
  ▼
async: audit event + lineage + telemetry → cloud (IngestTelemetry / Connect)
       cloud anomaly detector watches orchestration rate; can revoke / kill
```

### 2.2 The `orchestrator` capability & agent-facing tools

Provisioned through the normal **two-tier capability model**
([tui-daemon §4.11](tui-daemon.md)) but requires an **elevated grant** — an extra consent
step beyond a normal per-agent attach, because it confers authority over *other* agents.

| Tool | Effect | Default gating |
|------|--------|----------------|
| `synapse.list_agents()` | enumerate agents on this daemon the caller may target | none (scoped to grant) |
| `synapse.get_run(run_id)` | read status/telemetry of a run it started | none |
| `synapse.run_agent(id, input)` | trigger a run of an **already-approved** sibling agent | runs within budget |
| `synapse.create_agent(spec)` | define a new agent on this daemon | **HITL approval** |
| `synapse.edit_agent(id, patch)` | edit a sibling's prompt/config (NOT protected fields) | **HITL approval** |

Exposed to the agent the same way other capabilities are: via a built-in **`orchestrator`
MCP server** for CLI/tool agents, and programmatically for API agents.

### 2.3 Identity & the signed grant

- **Agent identity.** Each agent gets a machine identity (`agent_identities`) distinct from
  the daemon device token and the human user.
- **Grant token.** An **attenuated capability token** (macaroon / Biscuit-style — a base
  authority + cryptographically-chained caveats that can only *narrow* scope). Minted by the
  cloud when a human grants orchestration, cached on the daemon, verifiable **offline**.

```jsonc
// agent_orchestration_grants  (minted by cloud, cached + enforced on daemon)
{
  "grant_id": "grn_…",
  "agent_id": "agt_planner",
  "daemon_id": "dmn_macbook01",      // D1: same-daemon only
  "granted_by": "usr_…",             // the human; grant ⊆ this user's authority
  "verbs": ["run", "create", "edit"],
  "target_allow": ["agt_researcher", "agt_writer", "tag:safe"],
  "max_depth": 3,                    // recursion limit
  "max_fan_out": 5,                  // concurrent children per node
  "tree_budget_usd": 10.00,          // shared across the WHOLE orchestration tree
  "protected_fields": ["rulesets","blockers","env","capabilities","grants"],
  "expires_at": "2026-06-07T00:00:00Z",
  "sig": "ed25519:…"                 // cloud signature; daemon verifies, cannot forge
}
```

### 2.4 Local enforcement + async audit (D3)

The daemon's **orchestration broker** authorizes every tool call **locally** against the
cached grant — no cloud round-trip on the hot path:

1. **Verify** the grant signature + expiry; confirm `verb`, `target`, and same-daemon.
2. **Budget/limits**: `depth < max_depth`, `fan_out < max_fan_out`, `tree_budget` remaining;
   reject + surface to caller otherwise.
3. **No-escalation** (§2.5).
4. **Lineage**: append `(root_run_id, parent_run_id, depth, initiator=agent,
   initiator_agent_id)` to the **SQLite WAL** (same journal as checkpointing
   [§4.12](tui-daemon.md)); decrement the shared budget atomically.
5. **Execute** the child run locally, **or** pause for HITL if the verb is `create`/`edit`.
6. **Async** stream the audit event + lineage + child telemetry to the cloud.

**Why local, not a cloud round-trip:** it preserves **offline durability** (agent-to-agent
keeps working through a network blip — a round-trip would fail every orchestration on a
dropped link), lowers latency, and matches the existing principle that *rulesets are
enforced by the daemon, not the model*. The cloud still receives the complete audit lineage,
runs the anomaly detector on it, and retains the authority to **revoke the grant** (effective
on next reconnect) and trip the **kill switch**.

### 2.5 No-escalation (confused-deputy prevention)

The single most important safety rule:

> An orchestrated run's **effective permissions = intersection** of the *target agent's*
> permissions **and** the *grant's* scope. `edit_agent` may **never** add a permission the
> editing agent does not itself hold, and may **never** touch `protected_fields`.

This closes the laundering hole — an agent cannot route a forbidden action (e.g. a denied
shell command, an unallowed network host) through a more-privileged sibling, and cannot
edit a sibling to remove its blockers and then run it.

```python
def authorize_orchestration(call, grant, target_agent):
    assert verify_sig(grant) and not expired(grant)
    assert call.verb in grant.verbs
    assert target_agent.daemon_id == grant.daemon_id            # D1
    assert matches(call.target, grant.target_allow)
    assert call.depth < grant.max_depth
    assert live_fanout(call.parent_run_id) < grant.max_fan_out
    assert tree_budget_remaining(call.root_run_id) > 0
    if call.verb == "edit":
        assert call.patch.keys().isdisjoint(grant.protected_fields)
        assert call.patch.perms ⊆ caller_effective_perms()      # no-escalation
    if call.verb in ("create", "edit"):
        return REQUIRE_HITL
    return ALLOW   # run within budget
```

### 2.6 Anti-runaway controls

| Failure mode | Control |
|--------------|---------|
| Infinite recursion (A→B→A…) | `max_depth` + **cycle detection** over the lineage graph |
| Fork bomb / thousands of children | `max_fan_out` per node |
| Cost explosion | **one budget shared across the entire tree**, decremented atomically; trip → halt |
| Injection amplification (1 hijacked agent → whole local fleet) | `create`/`edit` behind HITL; `run` limited to grant `target_allow` + budget |
| Runaway in flight | **"halt orchestration tree"** kill switch cancels root + all descendants; anomaly detector auto-trips on orchestration-rate spikes |

### 2.7 New messages

- **Upstream (daemon → cloud)**, on the `Connect` stream — used for audit/lineage only,
  since enforcement is local: `agent.orchestrate { verb, caller_agent_id, target,
  payload_hash, root_run_id, parent_run_id, depth, idempotency_key }`.
- **Downstream (cloud → daemon)** reuses existing commands where the cloud must intervene:
  `grant.revoke { grant_id }`, `orchestration.halt { root_run_id }`.
- HITL for `create`/`edit` reuses the existing `hitl.request` / `hitl.resolve` path.

### 2.8 Data model (cloud)

- **`agent_identities`** — `agent_id`, `org_id`, public key/identity material, created/rotated.
- **`agent_orchestration_grants`** — the grant in §2.3 (also cached on the daemon).
- **`runs`** gains: `initiator` (`human|schedule|webhook|agent`), `initiator_agent_id`,
  `root_run_id`, `parent_run_id`, `depth`.
- **`audit_events`** — one per orchestrate/create/edit, with the full lineage chain
  (which agent, on behalf of which user, did what to which target).

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
- **Upstream**: variants stream over the existing `IngestTelemetry` RPC tagged with
  `run_group_id` / `variant_model`; group status rides the `Connect` stream.
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

## 11. Feature 4 — Native Handoff Protocol (MEDIUM RISK)

> **A constrained sibling of §2, not a duplicate.** §2 (Agent Orchestration) is *supervised
> fan-out* — a parent spawns and **stays alive over** children, with a shared tree budget,
> and can `create`/`edit` agents. This is the **sequential baton-pass**: Agent A finishes its
> slice and **passes work forward** to Agent B along a **human-pre-approved chain**. It
> **cannot** create/edit agents, **cannot** fan out, and **cannot** target an agent outside
> the approved topology — so it is **materially lower-risk than §2** and ships behind its own
> flag. It builds **Planner → Critic → Executor**-style workflows that render as one unified
> trace in the Web UI. Status: experimental, off by default, daemon-local only (v1).

### 11.1 Overview

An agent gains a built-in **`handoff`** capability with a single dangerous verb: **pass the
current task to another agent in a pre-approved chain**. The unit of work keeps moving along
an allow-listed topology (`planner → critic → executor`), every hop shares **one
`root_run_id`** (the unified Trace ID), and the whole chain is a single expandable lineage in
the Web UI. The daemon enforces a signed **chain grant** locally and streams audit upstream —
exactly the §2.4 local-enforce + async-audit model, just for a narrower verb.

```
Agent "planner" (daemon macbook-01, root_run_id = R)
  │  calls tool: synapse.handoff("critic", context_payload)            ── TAIL handoff
  ▼
Daemon handoff broker (LOCAL)
  │  1. verify chain grant covers edge planner→critic, same daemon
  │  2. check hop < max_hops, chain_budget_usd remaining
  │  3. redact context_payload via §4.5 Layer A  (nothing raw leaves A)
  │  4. append lineage row to SQLite WAL (root=R, parent=planner-run, hop+1)
  │  5. planner run COMPLETES; critic run STARTS on the SAME daemon, carrying R
  ▼
"critic" runs, may hand off onward: synapse.handoff("executor", …)   (hop 2, root still R)
  ▼
async: handoff audit event + lineage → cloud (Connect); telemetry → IngestTelemetry
       Web UI renders R as one trace: planner ▸ critic ▸ executor
```

### 11.2 Locked design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| H1 | **Handoff is a strict subset of orchestration.** Sequential baton-pass only — **no `create`/`edit`, no fan-out** (one successor at a time). | This is what makes it medium- not high-risk: an agent can only *route work it already holds* to a *pre-vetted* successor; it gains no authority to mint or reshape agents. |
| H2 | **Daemon-local only (v1).** The whole chain runs on the originating daemon. | Inherits §1.2 **D1** — no lateral movement; lineage/budget/loop-control stay on one host. Cross-daemon handoff deferred (§11.13). |
| H3 | **Targets are a human-pre-approved topology (the chain grant).** An agent may hand off **only along an edge that exists in the grant graph** — it cannot pick an arbitrary successor at runtime. | A handoff agent can't be tricked (prompt-injected) into routing work to an unintended high-trust agent: the edge must already exist in a human-signed graph. |
| H4 | **Context payload is bounded + redacted.** The A→B payload is size-capped, structured, and passed through §4.5 **Layer A** before it leaves A. | The payload is the one new data path; redacting it on-device keeps the on-device-redaction invariant intact and caps blast radius if A is compromised. |
| H5 | **The unified Trace ID is the existing `root_run_id`.** No new tracing primitive. | §2 already extends `runs` with `root_run_id`/`parent_run_id`/`depth`; a chain is just a linear lineage under one root. Reuse buys the trace view for free. |
| H6 | **Authz = local-enforce + async audit** (inherits §1.2 **D3**); enforcement is the **daemon**, not the model. | A successful injection still can't hand off along an edge the grant doesn't contain; the cloud keeps revoke + the kill switch. Works through a network blip. |

### 11.3 Handoff vs. orchestration — when to use which

| | **§11 Handoff** | **§2 Orchestration** |
|---|----------------|----------------------|
| Shape | **Linear chain** A▸B▸C (baton) | **Supervised tree** (parent over children) |
| Parent lifetime | **Tail handoff:** A *terminates*, B takes over | Parent **stays alive**, supervises, collects results |
| Concurrency | One successor at a time (no fan-out) | `max_fan_out` concurrent children |
| Verbs | `handoff` only | `run` + `create` + `edit` |
| Grant | **Chain grant** (an allow-listed edge graph) | **Attenuated orchestration grant** (verbs + targets + depth + budget) |
| Risk | **MEDIUM** | **HIGH** |
| Canonical use | Planner → Critic → Executor pipelines | An agent that dynamically composes/builds other agents |

**Two handoff modes:**

- **Tail handoff (default).** A completes and terminates; B continues the **same root run**.
  Pure baton-pass — the linear-pipeline case.
- **Return handoff (optional, still no fan-out).** A **pauses**, B runs to completion, B's
  (redacted) result returns to A, A resumes. Enables a **Critic loop** (Planner ▸ Critic ▸
  back to Planner) without ever running two successors at once. Still one-at-a-time, still no
  create/edit — so it stays below the orchestration line.

### 11.4 The `handoff` capability & the chain grant

Provisioned through the normal **two-tier capability model**
([tui-daemon §4.11](tui-daemon.md)) but, like §2.2, requires an **elevated grant** — here a
**chain grant** that names the permitted edges. Far simpler than the orchestration grant: no
`create`/`edit` verbs, no fan-out, just a signed **directed graph of allowed handoffs**.

| Tool | Effect | Default gating |
|------|--------|----------------|
| `synapse.handoff(to, context)` | pass the current task to a successor named in the chain grant (tail mode) | within `max_hops` + `chain_budget` |
| `synapse.handoff_return(to, context)` | pause self, run successor, resume with its result (return mode) | as above; one-at-a-time |
| `synapse.list_chain()` | enumerate the successors this agent may hand off to | none (scoped to grant) |

```jsonc
// agent_chain_grants  (minted by cloud, cached + enforced on daemon — verifiable offline)
{
  "grant_id": "chn_…",
  "daemon_id": "dmn_macbook01",          // H2: same-daemon only
  "granted_by": "usr_…",                 // grant ⊆ this human's authority
  "edges": [                             // H3: the ONLY handoffs allowed
    { "from": "agt_planner",  "to": "agt_critic"   },
    { "from": "agt_critic",   "to": "agt_planner"  },   // return-loop edge
    { "from": "agt_critic",   "to": "agt_executor" }
  ],
  "max_hops": 8,                         // total handoffs along the chain (loop guard)
  "chain_budget_usd": 5.00,              // shared across the WHOLE chain
  "max_payload_bytes": 32768,            // H4: bounded context transfer
  "modes": ["tail", "return"],
  "expires_at": "2026-06-07T00:00:00Z",
  "sig": "ed25519:…"                     // cloud signature; daemon verifies, cannot forge
}
```

### 11.5 The context payload (the one new data path)

A handoff carries a **structured, bounded handoff envelope** from A to B:

- **Fields:** `task` (the forward instruction), `artifacts` (refs/inline up to
  `max_payload_bytes`), `summary` (A's result so far), `hop`, `root_run_id`.
- **Redaction (H4):** the envelope is screened by **§4.5 Layer A** on A's daemon *before* it
  is handed to B — same salted-token treatment as any other egress. Raw secrets never ride a
  handoff; if B needs a credential it resolves its **own** env-var vault entry (§4.10), never
  inherits A's.
- **No permission inheritance.** B runs under **B's own** ruleset/blockers/capabilities — a
  handoff transfers *work*, not *authority*. (Contrast §2's intersection rule: there's nothing
  to intersect here because A confers no permissions on B.)

### 11.6 Unified trace & lineage (reuse, H5)

The chain reuses §2's lineage columns on `runs`: every hop writes
`root_run_id` (constant across the chain), `parent_run_id` (the predecessor run),
`depth`/`hop`, and `initiator = agent` / `initiator_agent_id`. The cloud already aggregates
by `root_run_id`, so:

- **One Trace ID** spans planner ▸ critic ▸ executor; the Web UI renders the chain as a single
  expandable run (the §2 "lineage view" gains a linear-chain layout).
- **Cost/telemetry** roll up to the root automatically — `chain_budget_usd` is enforced
  against the root's accumulated cost on the daemon.
- **Audit:** each hop is one `audit_events` row (`kind = handoff`) with `from`/`to`/`hop`/
  `root_run_id` and the **payload hash** (not the payload).

### 11.7 Local enforcement flow

On `synapse.handoff(to, ctx)` the daemon's **handoff broker** runs **locally** (no cloud
round-trip), mirroring §2.4:

1. **Verify** the chain grant is signed, unexpired, and contains the edge `caller → to` on
   **this** daemon (H3).
2. **Loop/budget gate:** `hop < max_hops` and root-run cost `< chain_budget_usd` (H1/H2).
3. **Redact** `ctx` via §4.5 Layer A; reject if it exceeds `max_payload_bytes` (H4).
4. **Journal** the lineage row to the SQLite WAL (root/parent/hop) — so a crash mid-handoff
   resumes correctly (§4.12 durability).
5. **Tail:** mark the caller run complete and **start `to`** carrying `root_run_id` + the
   redacted envelope. **Return:** checkpoint+pause the caller, start `to`, and on its
   completion resume the caller with `to`'s redacted result.
6. **Async** stream the handoff audit event + lineage + child telemetry to the cloud.

### 11.8 Safety controls

| Risk | Control |
|------|---------|
| Infinite ping-pong (A▸B▸A▸B…) | **`max_hops`** ceiling on total handoffs (cycles are *allowed* for Critic loops but **bounded**) |
| Runaway cost along the chain | shared **`chain_budget_usd`** enforced against the root run's accumulated cost; per-run `max_cost_usd` still applies to each hop |
| Injection re-routes work to a high-trust agent | **H3** — handoff only along edges in the human-signed graph; an off-graph target is simply not callable |
| Sensitive data leaking A→B | **H4** Layer-A redaction of the envelope + `max_payload_bytes` cap; no credential inheritance |
| Runaway chain in flight | the §2 **`orchestration.halt { root_run_id }`** kill switch cancels the root + all downstream hops (shared lineage); anomaly detector trips on handoff-rate spikes |
| `production` agents pulled into a chain | production-tagged agents **cannot** be chain edges (source or target) by default (inherits §4 production-exclusion) |

### 11.9 Data model (cloud)

| Table | Change |
|-------|--------|
| **`agent_chain_grants`** | **new** — the signed edge-graph grant in §11.4 (also cached on the daemon) |
| `runs` | **reuses** §2's `root_run_id` / `parent_run_id` / `depth` / `initiator` / `initiator_agent_id`; += `hop`, `handoff_mode` (`tail`/`return`) |
| `audit_events` | new kind: **`handoff`** (`from`, `to`, `hop`, `root_run_id`, `payload_hash`) |
| `agent_identities` | **reuses** §2's agent machine identity (no new table) |

No new telemetry tables — each hop is an ordinary `run`, so `tool_calls`, cost, and
checkpoint tables are unchanged (the same cheapness as §10).

### 11.10 New messages

- **Upstream** (daemon → cloud, `Connect` stream, audit-only since enforcement is local):
  `agent.handoff { from_agent_id, to_agent_id, root_run_id, parent_run_id, hop, mode,
  payload_hash, idempotency_key }`.
- **Downstream** (cloud → daemon): `grant.revoke { grant_id }` **(reused)** invalidates a
  chain grant; `orchestration.halt { root_run_id }` **(reused)** cancels a chain. *No new
  downstream verbs* — handoff intentionally rides §2's revoke + kill switch.

### 11.11 Web UI

- **Chain builder** — a human composes the allowed **edge graph** (drag agents, draw
  `from → to` edges), sets `max_hops` / `chain_budget` / `max_payload_bytes`, and signs it as
  a chain grant via the elevated-grant consent flow (shared with §2).
- **Unified trace view** — a chained run renders as **one expandable trace** under its
  `root_run_id`: a linear (or looped) **planner ▸ critic ▸ executor** ribbon, each hop
  expandable to its own telemetry, with the **redacted handoff envelope** + payload hash shown
  on each edge.
- **Live status** — the active hop is highlighted; **halt chain** (kill switch) and **revoke
  grant** are one click.

### 11.12 Risk notes (medium)

| Concern | Mitigation |
|---------|------------|
| An agent routes work somewhere unintended | **H3** pre-approved edge graph — off-graph handoff is uncallable; enforced by the daemon, not the model (**H6**) |
| Chain never terminates | **`max_hops`** + shared **`chain_budget_usd`** hard-stops |
| Context payload leaks secrets to the next agent | **H4** Layer-A redaction + size cap; no credential inheritance (§11.5) |
| Confusion with §2's authority model | handoff transfers **work, not permissions**; B runs under B's own ruleset; **no `create`/`edit`, no fan-out** (H1) |
| Crash mid-handoff loses the baton | lineage row is WAL-journaled **before** the successor starts (§11.7 step 4 / §4.12) |

### 11.13 Open questions / future

- **Cross-daemon handoff** — routing a chain across hosts (researcher on one box ▸ summarizer
  on another); reintroduces lateral-movement risk, deferred behind its own flag (as §2's
  cross-daemon is, §8).
- **Dynamic-but-bounded targets** — letting an agent choose among `tag:safe` successors rather
  than explicit edges; needs a tighter injection story before relaxing H3.
- **Handoff SLAs / timeouts** — auto-fail a hop that stalls, with a fallback edge.
- **Merge/join semantics** — a chain stays linear in v1; fan-in (multiple predecessors into
  one successor) is orchestration territory (§2), not handoff.

### 11.14 Promotion checklist — where this lands when graduated

- **[tui-daemon.md](tui-daemon.md)** — Agent Runtime gains the **handoff broker** + the
  `handoff` capability/MCP tools; add `agent.handoff` to the §4.2 command router; note the
  WAL lineage row + Layer-A envelope redaction (§4.5).
- **[cloud-backend.md](cloud-backend.md)** — §4 data model: `agent_chain_grants` + the `runs`
  `hop`/`handoff_mode` columns + the `handoff` audit kind; reuse of `root_run_id` aggregation;
  chain-grant mint/revoke; daemon-local + production-exclusion gating.
- **[integration.md](integration.md)** — a walkthrough (build chain grant → planner hands off
  to critic → critic returns → executor); a responsibility-matrix row; the `agent.handoff`
  upstream entry + reuse of `grant.revoke` / `orchestration.halt` downstream.
- **[web-ui.md](web-ui.md)** — the chain builder (edge graph + limits + consent) and the
  unified-trace chain view (per-hop expand + redacted envelope).
- **`.claude/memory/project_overview.md`** — the handoff model + decisions H1–H6 (subset of
  orchestration, daemon-local, pre-approved edge graph, bounded+redacted payload, reuse
  `root_run_id` as the unified trace, local-enforce).

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

No new transport primitive: findings stream up over the existing **`IngestTelemetry`** RPC
(as §4.5 findings already do); auto-pause rides the **`Connect`** stream.

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
  row; findings ride existing `IngestTelemetry`, auto-pause rides `Connect`.
- **[web-ui.md](web-ui.md)** — the intent-profile editor (envelope + tool blast-radius
  classifier + sensitivity), the drift timeline in Logs §4.10 / Alerts §4.13, and the
  action-scoped destructive-approval surface.
- **`.claude/memory/project_overview.md`** — the intent-monitoring model + decisions G1–G6
  (AI detects/daemon enforces, friction-only, on-device + cloud baseline, action-scoped
  just-in-time authorization for destructive tools, operator-set envelope, fail-safe).
