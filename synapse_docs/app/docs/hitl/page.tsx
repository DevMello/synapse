import { CapabilityMock } from '@/components/capabilities/data'

export default function Page() {
  return <>



      <div className="doc-hero">
        <div className="kicker">Unit 6</div>
        <h1>Human-in-the-Loop</h1>
        <p>Give humans the final word before an agent takes an irreversible action. Approval gates let you run powerful autonomous agents with confidence, knowing that anything destructive waits for your sign-off.</p>
      </div>

      <CapabilityMock id="approvals" />

      <section className="doc-section" id="overview">
        <h2>What is Human-in-the-Loop?</h2>
        <p>Human-in-the-Loop (HITL) is a control mechanism that inserts a mandatory human decision point into an agent's execution path. When the daemon encounters an operation that matches a configured rule, it pauses the agent, emits a pause event to the cloud, and waits for an authorized human to approve or reject the action before proceeding.</p>
        <p>AI agents are increasingly capable of making wide-ranging changes: deleting files, pushing code, sending emails, calling external APIs, or modifying infrastructure. Many of these actions are <strong>irreversible</strong>. A misfire at scale can cause real damage before a human notices the logs.</p>
        <p>HITL addresses this by enforcing a trust boundary at the point of execution. The agent cannot proceed past a gate unilaterally — it must receive an explicit human signal. This is not about distrust of AI in general; it is about applying the same principle that governs critical human workflows: four-eyes checks, change-approval boards, and deployment sign-offs.</p>
        <ul>
          <li><strong>Irreversibility guard</strong> — any command that cannot be undone (deletes, drops, purges) can be gated.</li>
          <li><strong>Scope containment</strong> — stop an agent from operating outside its intended domain without a human reviewing the drift.</li>
          <li><strong>Audit continuity</strong> — every gate crossed leaves a permanent, attributed record in the audit trail.</li>
          <li><strong>Graceful abort</strong> — rejecting a gate cleanly terminates the run; the agent does not retry or find workarounds.</li>
        </ul>
      </section>

      
      <section className="doc-section" id="approval-gates">
        <h2>How Approval Gates Work</h2>
        <p>The lifecycle of an approval gate spans the daemon, the cloud broker, and the Web UI (or TUI). No component acts alone — the three-tier architecture keeps secrets on your machine and decisions recorded in the cloud.</p>

        <div className="steps">
          <div className="step">
            <div className="step-body">
              <h4>Daemon detects a gated operation</h4>
              <p>The agent requests an action (e.g., running a shell command). The daemon evaluates it against the loaded ruleset. If a rule matches, execution pauses immediately — the subprocess is not spawned.</p>
            </div>
          </div>
          <div className="step">
            <div className="step-body">
              <h4>Pause event emitted to cloud</h4>
              <p>The daemon sends a structured <code>hitl.pause</code> event over its persistent outbound WebSocket to the cloud broker. The event contains the agent ID, run ID, matched rule, the full command, and any context the agent provided.</p>
            </div>
          </div>
          <div className="step">
            <div className="step-body">
              <h4>Cloud routes to approvals queue</h4>
              <p>The broker writes the pause event to the approvals queue and fans out notifications to all configured channels (Slack, Discord, email). The queue entry is visible immediately in Web UI → Approvals and in the TUI approvals panel.</p>
            </div>
          </div>
          <div className="step">
            <div className="step-body">
              <h4>Authorized user approves or rejects</h4>
              <p>A user with <code>admin</code> or <code>operator</code> role reviews the pending item. They can approve (the run continues) or reject (the run aborts). An optional comment can be attached to either decision.</p>
            </div>
          </div>
          <div className="step">
            <div className="step-body">
              <h4>Cloud relays the decision</h4>
              <p>The broker pushes a <code>hitl.decision</code> event back to the daemon over the same outbound connection. The decision includes who acted, when, and the comment if any.</p>
            </div>
          </div>
          <div className="step">
            <div className="step-body">
              <h4>Daemon resumes or aborts</h4>
              <p>On approval, the daemon spawns the previously-held subprocess and the agent continues. On rejection, the daemon sends an abort signal to the agent runtime and marks the run as <code>rejected</code>. Either outcome is written to the immutable audit log.</p>
            </div>
          </div>
        </div>

        <div className="terminal">
          <div className="term-bar">
            <div className="term-dots"><i></i><i></i><i></i></div>
            <span className="term-file">synapse daemon — HITL pause/resume</span>
          </div>
          <div className="term-body">
            <div className="term-out info">agent:cleanup-bot  run:r_7k2m  step 4 of 9  →  exec "rm -rf /var/log/old"</div>
            <div className="term-out warn">HITL gate triggered  rule:no-destructive-deletes  severity:block</div>
            <div className="term-out info">pause event sent to cloud  queue_id:q_9fn3</div>
            <div className="term-out">waiting for human decision … (timeout: none — severity block)</div>
            <br />
            <div className="term-out ok">decision received  actor:alice@acme.com  action:approved</div>
            <div className="term-out ok">comment: "old logs confirmed stale, safe to delete"</div>
            <div className="term-out info">resuming agent execution</div>
            <div className="term-out ok">step 4 complete  exec exited 0</div>
          </div>
        </div>
      </section>

      
      <section className="doc-section" id="severity-levels">
        <h2>Severity Levels</h2>
        <p>Each HITL rule carries a severity that controls how the daemon behaves when the rule fires. Choose the right severity to balance safety with throughput.</p>

        <table>
          <thead>
            <tr>
              <th>Severity</th>
              <th>Daemon behavior</th>
              <th>Timeout</th>
              <th>Use when</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><span className="chip block">block</span></td>
              <td>Always stops. Execution does not continue until an explicit approval is received. No automatic timeout — the run waits indefinitely.</td>
              <td>None (waits forever)</td>
              <td>Irreversible operations: <code>DROP TABLE</code>, mass deletes, production deploys, secret rotation.</td>
            </tr>
            <tr>
              <td><span className="chip warn">require-approval</span></td>
              <td>Pauses and waits for a decision. If the configured timeout expires without a decision, the action is automatically <strong>rejected</strong> and the run aborts.</td>
              <td>Configurable (default: 30 min)</td>
              <td>Risky but time-bounded operations where an unattended overnight run should fail safe rather than wait forever.</td>
            </tr>
            <tr>
              <td><span className="chip approve">warn</span></td>
              <td>Logs a structured warning event to the cloud audit log and continues execution unless a human has pre-configured an override that escalates it. Does not pause the agent.</td>
              <td>N/A — non-blocking</td>
              <td>Visibility without friction: flag unusual patterns for post-hoc review while keeping the agent running.</td>
            </tr>
          </tbody>
        </table>

        <div className="callout warning">
          <span className="callout-icon">⚠</span>
          <p><strong>Timeout = reject, not approve.</strong> For <code>require-approval</code> rules, a timeout is a safety-side failure. The run aborts cleanly rather than silently proceeding. If you need indefinite wait, use <code>block</code> instead.</p>
        </div>
      </section>

      
      <section className="doc-section" id="configuration">
        <h2>Configuring HITL Rules</h2>
        <p>Rules live in your daemon config file (<code>~/.config/synapse/daemon.toml</code> on Linux/macOS, <code>%APPDATA%\synapse\daemon.toml</code> on Windows). Each rule specifies what to match and what to do when it matches.</p>

        <pre><code># daemon.toml — HITL ruleset configuration

[hitl]
enabled = true

# Default timeout for require-approval rules (seconds)
default_timeout = 1800   # 30 minutes

[[hitl.ruleset.rules]]
name        = "no-recursive-deletes"
description = "Block any rm -rf invocation regardless of path"
pattern     = "rm -rf"
match       = "command-contains"   # options: command-contains | command-regex | tool-name
action      = "require-approval"
severity    = "block"
notify      = ["slack", "email"]

[[hitl.ruleset.rules]]
name        = "no-database-drops"
description = "Block DROP TABLE / DROP DATABASE in any SQL tool call"
pattern     = "(?i)drop\\s+(table|database|schema)"
match       = "command-regex"
action      = "require-approval"
severity    = "block"
notify      = ["slack"]

[[hitl.ruleset.rules]]
name        = "warn-on-curl-post"
description = "Log a warning when the agent makes outbound POST requests"
pattern     = "curl.*-X POST"
match       = "command-regex"
action      = "warn"
severity    = "warn"
notify      = []

[[hitl.ruleset.rules]]
name        = "production-deploy"
description = "Require approval before any deployment to production"
tool_name   = "deploy"
match       = "tool-name"
action      = "require-approval"
severity    = "require-approval"
timeout     = 3600   # override: 1 hour for deploy gates
notify      = ["slack", "discord", "email"]</code></pre>

        <h3>Pattern matching modes</h3>
        <ul>
          <li><code>command-contains</code> — simple substring match against the full command string. Fast and easy to read.</li>
          <li><code>command-regex</code> — full ECMAScript-compatible regular expression. Use for complex patterns or case-insensitive matching.</li>
          <li><code>tool-name</code> — matches the name of the MCP tool or built-in tool being called, independent of its arguments. Useful for gating all invocations of a specific tool regardless of parameters.</li>
        </ul>

        <div className="callout info">
          <span className="callout-icon">i</span>
          <p>Rules are evaluated in order. The first matching rule wins. Place more specific rules above more general ones to avoid unintended early matches.</p>
        </div>
      </section>

      
      <section className="doc-section" id="web-ui">
        <h2>Approvals Queue in Web UI</h2>
        <p>Open <strong>Web UI → Approvals</strong> to see every pending gate across all agents and daemons registered to your organization. The queue updates in real time via a push subscription — no manual refresh needed.</p>

        <h3>Pending item layout</h3>
        <p>Each card in the approvals queue displays:</p>
        <ul>
          <li><strong>{"Agent name & run ID"}</strong> — links to the full run detail page.</li>
          <li><strong>Matched rule</strong> — the name from your ruleset config and its severity chip.</li>
          <li><strong>Full command or tool call</strong> — exactly what the agent is asking to do, untruncated.</li>
          <li><strong>Context</strong> — the agent's stated reason for the action, taken from its scratchpad at pause time.</li>
          <li><strong>Timestamp</strong> — when the gate fired; for <code>require-approval</code> rules, a countdown timer shows how long until automatic rejection.</li>
          <li><strong>Daemon</strong> — which local machine the agent is running on.</li>
        </ul>

        <h3>Acting on a pending item</h3>
        <p>Click any card to expand it. The detail view shows the full agent context window at pause time. Two action buttons are present:</p>
        <ul>
          <li><strong>Approve</strong> (green) — the daemon receives a <code>hitl.decision: approved</code> event and resumes execution.</li>
          <li><strong>Reject</strong> (red) — the daemon receives a <code>hitl.decision: rejected</code> event, the agent run is aborted, and the rejection reason is logged.</li>
        </ul>
        <p>A <strong>comment field</strong> sits above both buttons. Comments are optional but strongly recommended — they become part of the permanent audit record and help future reviewers understand why a decision was made.</p>

        <div className="callout tip">
          <span className="callout-icon">✓</span>
          <p>You can bulk-approve or bulk-reject multiple items of the same rule type by selecting them with the checkbox column header. Bulk actions attach the same comment to all selected items.</p>
        </div>
      </section>

      
      <section className="doc-section" id="notifications">
        <h2>Notification Channels</h2>
        <p>When a gate fires, Synapse can notify your team immediately so approvals do not sit unattended. Notifications are sent at the moment the <code>hitl.pause</code> event reaches the cloud — typically within one second of the daemon pausing.</p>

        <div className="callout warning">
          <span className="callout-icon">⚠</span>
          <p><strong>Notifications fire on pause, not on timeout.</strong> Your team is alerted the instant the gate triggers, giving the maximum window to review before a <code>require-approval</code> timeout expires.</p>
        </div>

        <h3>Supported channels</h3>
        <table>
          <thead>
            <tr>
              <th>Channel</th>
              <th>What you receive</th>
              <th>Config location</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Slack</strong></td>
              <td>Rich message block: agent, rule, truncated command, approve/reject deep-link buttons (opens Web UI pre-loaded on that item).</td>
              <td>Web UI → Settings → Notifications → Slack</td>
            </tr>
            <tr>
              <td><strong>Discord</strong></td>
              <td>Embed with colour-coded severity, agent name, rule, command preview. No interactive buttons — link opens Web UI.</td>
              <td>Web UI → Settings → Notifications → Discord</td>
            </tr>
            <tr>
              <td><strong>Email</strong></td>
              <td>Plain-text and HTML email to one or more addresses. Subject: <code>{"[Synapse HITL] <agent> waiting for approval"}</code>. Body includes full command and direct link.</td>
              <td>Web UI → Settings → Notifications → Email</td>
            </tr>
          </tbody>
        </table>

        <h3>Configuring in Web UI</h3>
        <p>Navigate to <strong>Settings → Notifications</strong>. Each channel has an <em>Add integration</em> button:</p>
        <ol>
          <li>For <strong>Slack</strong>: click <em>Connect Slack workspace</em>, complete the OAuth flow, then choose the target channel. You can add multiple channels (e.g., <code>#ops-alerts</code> and <code>#on-call</code>).</li>
          <li>For <strong>Discord</strong>: paste a webhook URL from your Discord server's channel settings (<em>Edit Channel → Integrations → Webhooks</em>).</li>
          <li>For <strong>Email</strong>: enter one or more comma-separated addresses. Synapse sends from <code>hitl-alerts@synapse.run</code>; add this to your allowlist if your mail provider filters unknown senders.</li>
        </ol>
        <p>Each integration can be scoped to fire on specific severity levels only — e.g., send a Slack message for <code>warn</code> events but page the email list only for <code>block</code> events.</p>
      </section>

      
      <section className="doc-section" id="rbac">
        <h2>RBAC-Checked Decisions</h2>
        <p>Not every member of your organization should be able to approve an agent action. Synapse enforces role-based access control on every decision attempt at the API layer — the Web UI simply reflects what the server will allow.</p>

        <table>
          <thead>
            <tr>
              <th>Role</th>
              <th>View queue</th>
              <th>Approve / Reject</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>owner</code></td>
              <td>Yes</td>
              <td>Yes</td>
              <td>Inherits all admin permissions. Cannot be removed from the organization.</td>
            </tr>
            <tr>
              <td><code>admin</code></td>
              <td>Yes</td>
              <td>Yes</td>
              <td>Full control over agents, rules, and decisions.</td>
            </tr>
            <tr>
              <td><code>operator</code></td>
              <td>Yes</td>
              <td>Yes</td>
              <td>Can act on pending gates but cannot modify ruleset configuration or manage users.</td>
            </tr>
            <tr>
              <td><code>viewer</code></td>
              <td>Yes</td>
              <td>No</td>
              <td>Read-only access. Approve and Reject buttons are visible but disabled; API returns <code>403 Forbidden</code> if called directly.</td>
            </tr>
          </tbody>
        </table>

        <div className="callout warning">
          <span className="callout-icon">⚠</span>
          <p><strong>RBAC is enforced server-side.</strong> Disabling the approve button in the Web UI is a convenience; the actual gate is the API authorization check. Scripted requests with a <code>viewer</code> token will be rejected with <code>403</code> regardless of how the request is constructed.</p>
        </div>

        <p>Roles are managed in <strong>Web UI → Settings → Members</strong>. You can assign roles per-organization; a user can be an <code>operator</code> in one org and a <code>viewer</code> in another.</p>
      </section>

      
      <section className="doc-section" id="tui">
        <h2>TUI Approvals Panel</h2>
        <p>If you prefer staying in the terminal, the Synapse TUI includes a dedicated approvals panel that mirrors the Web UI queue in real time. Press <code>Tab</code> from any panel to cycle to <em>Approvals</em>, or jump directly with <code>Ctrl+A</code>.</p>

        <h3>Keyboard shortcuts</h3>
        <table>
          <thead>
            <tr>
              <th>Key</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>↑</code> / <code>↓</code></td>
              <td>Navigate the pending queue. The highlighted item's full command and context are shown in the detail pane on the right.</td>
            </tr>
            <tr>
              <td><code>a</code></td>
              <td>Approve the selected item. You will be prompted to enter an optional comment before the decision is submitted.</td>
            </tr>
            <tr>
              <td><code>r</code></td>
              <td>Reject the selected item. Same comment prompt. The run aborts on the daemon immediately.</td>
            </tr>
            <tr>
              <td><code>Enter</code></td>
              <td>Expand the selected item to show the full agent scratchpad and matched rule detail.</td>
            </tr>
            <tr>
              <td><code>Esc</code></td>
              <td>Collapse an expanded item / cancel a pending comment prompt.</td>
            </tr>
            <tr>
              <td><code>?</code></td>
              <td>Open the keyboard shortcut help overlay.</td>
            </tr>
          </tbody>
        </table>

        <div className="terminal">
          <div className="term-bar">
            <div className="term-dots"><i></i><i></i><i></i></div>
            <span className="term-file">synapse tui — Approvals panel</span>
          </div>
          <div className="term-body">
            <div className="term-out" style={{ color: "#6b6457" }}>┌─ Approvals (3 pending) ──────────────────────────────┐</div>
            <div className="term-out" style={{ color: "#6b6457" }}>│                                                      │</div>
            <div className="term-out" style={{ background: "rgba(239,106,42,0.18)", color: "#e3dccf" }}>│ ► [BLOCK]  cleanup-bot / r_7k2m   rm -rf /var/log   │</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>│   [BLOCK]  backup-agent / r_8a1x  DROP TABLE events  │</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>│   [REQ]    deploy-bot / r_9zp2    deploy --env prod  │</div>
            <div className="term-out" style={{ color: "#6b6457" }}>│                                                      │</div>
            <div className="term-out" style={{ color: "#6b6457" }}>└──────────────────────────────────────────────────────┘</div>
            <br />
            <div className="term-out" style={{ color: "#6b6457" }}>┌─ Detail ─────────────────────────────────────────────┐</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>│  agent:   cleanup-bot                                │</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>│  run:     r_7k2m                                     │</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>│  rule:    no-recursive-deletes  (block)              │</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>│  cmd:     rm -rf /var/log/old                        │</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>│  context: "clearing logs older than 90 days"         │</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>│  paused:  14s ago                                    │</div>
            <div className="term-out" style={{ color: "#6b6457" }}>│                                                      │</div>
            <div className="term-out" style={{ color: "#6b6457" }}>│  [a] approve   [r] reject   [Enter] expand   [?] help│</div>
            <div className="term-out" style={{ color: "#6b6457" }}>└──────────────────────────────────────────────────────┘</div>
          </div>
        </div>

        <p>The TUI panel uses the same WebSocket connection as the daemon — there is no separate authentication step. Your local <code>synapse auth</code> session determines which org's queue you see.</p>
      </section>

      
      <section className="doc-section" id="audit-trail">
        <h2>Audit Trail</h2>
        <p>Every HITL decision — approval or rejection — is written to an immutable, append-only audit log stored in the cloud. The log cannot be edited or deleted after the fact, even by organization owners.</p>

        <h3>What each audit entry contains</h3>
        <ul>
          <li><strong>Decision ID</strong> — a globally unique identifier for this specific gate crossing.</li>
          <li><strong>{"Run & agent"}</strong> — the full run ID and agent name, with a link to the run's detail page.</li>
          <li><strong>Rule matched</strong> — rule name, severity, and the exact pattern that fired.</li>
          <li><strong>Full command</strong> — the complete, untruncated command or tool call the agent submitted.</li>
          <li><strong>Agent context</strong> — the agent's scratchpad and stated intent at pause time, captured verbatim.</li>
          <li><strong>Decision</strong> — <code>approved</code> or <code>rejected</code>.</li>
          <li><strong>Actor</strong> — the email address and user ID of the person who acted, or <code>system/timeout</code> for automatic rejections.</li>
          <li><strong>Timestamp</strong> — ISO-8601 UTC timestamp of the decision, not the pause.</li>
          <li><strong>Comment</strong> — the reviewer's comment, if provided.</li>
        </ul>

        <h3>Accessing the audit trail</h3>
        <p>The audit log is accessible in two places:</p>
        <ol>
          <li><strong>Web UI → Runs → [select a run] → Audit tab</strong> — shows all HITL events for that specific run in chronological order.</li>
          <li><strong>Web UI → Approvals → History</strong> — the organization-wide audit log, filterable by date range, agent, rule, actor, and decision outcome.</li>
        </ol>

        <div className="callout tip">
          <span className="callout-icon">✓</span>
          <p><strong>Audit log entries are immutable.</strong> Once written, a decision record cannot be modified or deleted via any API or UI action. This property is enforced at the database layer with append-only permissions on the audit table. Use the History export (CSV or JSON) for compliance reporting.</p>
        </div>

        <div className="terminal">
          <div className="term-bar">
            <div className="term-dots"><i></i><i></i><i></i></div>
            <span className="term-file">synapse audit log — run r_7k2m</span>
          </div>
          <div className="term-body">
            <div className="term-out" style={{ color: "#5b8fd9" }}>decision_id:  dec_3hq8r2</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>run:          r_7k2m  (cleanup-bot)</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>rule:         no-recursive-deletes  [block]</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>command:      rm -rf /var/log/old</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>context:      "clearing logs older than 90 days per maintenance schedule"</div>
            <div className="term-out ok">decision:     approved</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>actor:        alice@acme.com  (uid:u_k9mn)</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>timestamp:    2025-11-14T03:47:22Z</div>
            <div className="term-out" style={{ color: "#b8b0a4" }}>comment:      "old logs confirmed stale, safe to delete"</div>
            <br />
            <div className="term-out" style={{ color: "#6b6457" }}># This record is immutable. Append-only audit log.</div>
          </div>
        </div>
      </section>

    
  </>
}
