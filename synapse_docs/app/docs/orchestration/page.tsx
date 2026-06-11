export default function Page() {
  return <>

    <div className="doc-hero">
      <div className="kicker">Advanced</div>
      <h1>Agent Orchestration</h1>
      <p>Let one agent direct many. Synapse's orchestration system lets a trusted orchestrator spawn child agents for parallel or sequential sub-tasks — with full spend controls, depth limits, and an auditable run tree enforced by the daemon, not the model.</p>
    </div>

    
    <section className="doc-section" id="overview">
      <h2>What is agent orchestration?</h2>
      <p>Agent orchestration is the pattern where one agent — called the <strong>orchestrator</strong> — breaks a larger task into sub-tasks and spawns dedicated child agents to handle each one. The orchestrator coordinates results and decides the next step; the children do the focused work.</p>
      <p>Synapse tracks the full run tree from root to leaf, enforces spend budgets across the entire tree, and prevents any agent from spawning children unless an admin has explicitly granted that right via a <strong>spawn grant</strong>.</p>
      <h3>Common use cases</h3>
      <ul>
        <li><strong>Release pipeline:</strong> a <code>release-captain</code> agent spawns <code>qa-agent</code> and <code>deploy-agent</code> in parallel, waits for both to succeed, then spawns <code>notify-agent</code>.</li>
        <li><strong>Incident response:</strong> an <code>incident-commander</code> agent spawns a <code>diagnosis-agent</code> to collect logs and metrics, then spawns a <code>remediation-agent</code> based on the findings.</li>
        <li><strong>Code review pipeline:</strong> a <code>pr-reviewer</code> agent spawns a <code>lint-agent</code>, a <code>test-agent</code>, and a <code>security-scan-agent</code> concurrently, then summarises all three results.</li>
      </ul>
      <div className="callout info">
        <span className="callout-icon">ℹ</span>
        <p>Orchestration is opt-in. An agent without a spawn grant cannot spawn children under any circumstances — even if the model attempts to do so via a crafted prompt.</p>
      </div>
    </section>

    
    <section className="doc-section" id="spawn-grants">
      <h2>Spawn grants</h2>
      <p>Before an agent can spawn children, an admin must <em>mint a grant</em> for that agent. The grant is stored cloud-side, relayed to the daemon on the next heartbeat, and checked locally on every spawn request. Grants are never stored inside the agent's prompt or accessible to the model.</p>
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Type</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>verbs</code></td>
            <td><code>[]string</code></td>
            <td>Allowed operations: <code>run</code>, <code>create</code>, <code>edit</code></td>
          </tr>
          <tr>
            <td><code>targetAllow</code></td>
            <td><code>[]string</code></td>
            <td>Agent name patterns the parent may spawn (e.g. <code>["qa-*", "deploy-prod"]</code>)</td>
          </tr>
          <tr>
            <td><code>maxDepth</code></td>
            <td><code>int</code></td>
            <td>Maximum nesting depth (1 = only direct children)</td>
          </tr>
          <tr>
            <td><code>maxFanOut</code></td>
            <td><code>int</code></td>
            <td>Max simultaneous child runs at any depth</td>
          </tr>
          <tr>
            <td><code>treeBudgetUsd</code></td>
            <td><code>float</code></td>
            <td>Cost ceiling for the entire spawn tree in USD</td>
          </tr>
          <tr>
            <td><code>expiresAt</code></td>
            <td><code>timestamp</code></td>
            <td>Grant expiry (<code>null</code> = never expires)</td>
          </tr>
        </tbody>
      </table>
      <div className="callout warning">
        <span className="callout-icon">⚠</span>
        <p><code>targetAllow</code> patterns are glob-matched server-side. A pattern like <code>deploy-*</code> matches <code>deploy-staging</code> and <code>deploy-prod</code> but not <code>predeploy-check</code>. Be as specific as your use case allows.</p>
      </div>
    </section>

    
    <section className="doc-section" id="run-lineage">
      <h2>Run lineage</h2>
      <p>Every run in Synapse carries three lineage fields that are set at creation and are immutable:</p>
      <ul>
        <li><code>rootRunId</code> — the top-level run that started the tree; equal to the run's own ID for root runs.</li>
        <li><code>parentRunId</code> — the direct parent run; <code>null</code> for root runs.</li>
        <li><code>depth</code> — 0 for the root run, incremented by 1 for each level of nesting.</li>
      </ul>
      <p>These fields are used by the daemon to enforce <code>maxDepth</code> and <code>maxFanOut</code> limits, and by the Web UI to render the tree view.</p>
      <pre><code>run-abc (depth=0, root)
├── run-def (depth=1, parentRunId=run-abc)
│   └── run-ghi (depth=2, parentRunId=run-def)
└── run-jkl (depth=1, parentRunId=run-abc)</code></pre>
      <div className="callout tip">
        <span className="callout-icon">✓</span>
        <p>All runs in a tree share the same <code>rootRunId</code>. You can query the entire tree at once using: <code>synapse runs list --root run-abc</code></p>
      </div>
    </section>

    
    <section className="doc-section" id="minting-grants">
      <h2>Minting a grant</h2>
      <p>Grants can be minted from the Web UI or the CLI. Only organization admins can mint grants.</p>
      <h3>Web UI</h3>
      <div className="steps">
        <div className="step">
          <div className="step-body">
            <h4>Open the Orchestration tab</h4>
            <p>Navigate to Web UI → Agents → [orchestrator agent] → Orchestration tab.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Create a new grant</h4>
            <p>Click <strong>New Grant</strong> and fill in the fields: <code>verbs</code>, <code>targetAllow</code>, <code>maxDepth</code>, <code>maxFanOut</code>, <code>treeBudgetUsd</code>, and optionally <code>expiresAt</code>.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Confirm and relay</h4>
            <p>Click <strong>Confirm</strong>. The grant is stored cloud-side and relayed to the daemon on its next heartbeat (typically within 30 seconds).</p>
          </div>
        </div>
      </div>
      <h3>CLI</h3>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse agent grant create pr-reviewer \</div>
          <div>  --target "qa-*" \</div>
          <div>  --max-depth 2 \</div>
          <div>  --budget 5.00</div>
          <div className="term-out ok">Grant grt_01hx9abc created for pr-reviewer</div>
          <div className="term-out info">Targeting: qa-* | maxDepth: 2 | maxFanOut: (unlimited) | budget: $5.00</div>
          <div className="term-out info">Grant will be relayed to daemon on next heartbeat</div>
        </div>
      </div>
      <p>You can also set <code>--verbs</code> (default: <code>run</code>), <code>--max-fan-out</code>, and <code>--expires-at</code> (RFC 3339 timestamp).</p>
    </section>

    
    <section className="doc-section" id="runtime">
      <h2>How spawning works at runtime</h2>
      <p>When an orchestrator agent wants to spawn a child, it calls the Synapse spawn API — either via the MCP <code>spawn_agent</code> tool or directly through the SDK. The request flows as follows:</p>
      <ol>
        <li>The orchestrator sends a spawn request to the local daemon, including the target agent name, initial input, and any configuration overrides.</li>
        <li>The daemon looks up the orchestrator's active spawn grants and validates the request against every constraint: <code>verbs</code>, <code>targetAllow</code> glob patterns, current <code>depth</code>, current <code>fanOut</code> count, and remaining <code>treeBudgetUsd</code>.</li>
        <li>If validation passes, the daemon starts the child run, records its <code>parentRunId</code> and <code>rootRunId</code>, and returns the new run ID to the orchestrator.</li>
        <li>As the child run accrues cost, the daemon decrements the tree's remaining budget atomically. Once the budget is exhausted, all subsequent spawn attempts for that tree are refused — even if the grant's own <code>treeBudgetUsd</code> has not been reached by any single run.</li>
      </ol>
      <div className="callout info">
        <span className="callout-icon">ℹ</span>
        <p>Budget enforcement is atomic and enforced by the daemon in-process. There is no race window where two simultaneous spawns could both see budget remaining and collectively overspend.</p>
      </div>
    </section>

    
    <section className="doc-section" id="revoking-grants">
      <h2>Revoking grants</h2>
      <p>Grants can be revoked at any time. Revocation takes effect on the daemon's next heartbeat sync.</p>
      <h3>Web UI</h3>
      <p>Navigate to Web UI → Agents → [agent] → Orchestration tab → [grant row] → <strong>Revoke</strong>. Confirm the dialog. The grant status changes to <em>Revoked</em> immediately in the UI.</p>
      <h3>CLI</h3>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse agent grant revoke grt_01hx9abc</div>
          <div className="term-out ok">Grant grt_01hx9abc revoked</div>
          <div className="term-out warn">In-flight runs will complete; no new spawns will be permitted</div>
        </div>
      </div>
      <div className="callout tip">
        <span className="callout-icon">✓</span>
        <p>In-flight runs that were spawned before revocation are allowed to complete. Revocation only blocks <em>new</em> spawns. If you need to halt in-flight runs immediately, cancel them individually with <code>{"synapse run cancel <run-id>"}</code>.</p>
      </div>
    </section>

    
    <section className="doc-section" id="tree-view">
      <h2>Viewing orchestration trees</h2>
      <p>The Web UI provides a dedicated Tree view for any root run that has spawned children.</p>
      <ul>
        <li>Navigate to Web UI → Runs → [root run] → <strong>Tree</strong> tab.</li>
        <li>The tree is rendered as a collapsible hierarchy. Each node shows the run ID, agent name, status badge, depth, and accrued cost.</li>
        <li>Click any run node to jump directly to that run's detail page.</li>
        <li>The root node displays the <strong>total tree cost</strong> — the sum of all descendant runs — in addition to its own run cost.</li>
        <li>Running and pending children are shown with live status updates; the tree auto-refreshes every 5 seconds while any child is active.</li>
      </ul>
      <p>From the CLI, you can list all runs in a tree with:</p>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse runs list --root run-abc --tree</div>
          <div className="term-out">run-abc   release-captain   succeeded   depth=0   $3.14 (tree: $8.72)</div>
          <div className="term-out">  run-def  qa-agent          succeeded   depth=1   $2.30</div>
          <div className="term-out">  run-jkl  deploy-staging    succeeded   depth=1   $1.58</div>
          <div className="term-out">  run-mno  deploy-prod       succeeded   depth=1   $1.70</div>
        </div>
      </div>
    </section>

    
    <section className="doc-section" id="security">
      <h2>Security model</h2>
      <p>Synapse's orchestration security is designed so that a compromised or prompt-injected model cannot escalate its own privileges or spawn agents it was never authorized to spawn.</p>
      <ul>
        <li><strong>Grants are enforced by the daemon, not the model.</strong> Even if a prompt injection tricks the model into calling the spawn API with an unauthorized target, the daemon will reject the request before any child run starts.</li>
        <li><strong>Grants are not visible to the model.</strong> The agent's system prompt does not contain grant details. The model has no way to read, modify, or forge grant data.</li>
        <li><strong><code>targetAllow</code> is glob-matched server-side.</strong> Pattern matching happens in the daemon. The model cannot influence the matching logic.</li>
        <li><strong>Depth limits prevent runaway recursion.</strong> A child agent that itself has a grant cannot spawn deeper than the root grant's <code>maxDepth</code> allows relative to the tree root.</li>
        <li><strong>Fan-out limits prevent resource exhaustion.</strong> <code>maxFanOut</code> is counted across all active runs in the tree at any depth — not just direct children.</li>
        <li><strong><code>treeBudgetUsd</code> is a hard ceiling.</strong> The daemon refuses new spawn requests once the accumulated tree cost reaches the budget, regardless of which agent in the tree makes the request.</li>
      </ul>
      <div className="callout warning">
        <span className="callout-icon">⚠</span>
        <p>If an agent's grant uses a broad <code>targetAllow</code> pattern (e.g. <code>*</code>), a prompt injection could spawn any registered agent. Use the most restrictive patterns your workflow allows, and set a tight <code>treeBudgetUsd</code> as a safety net.</p>
      </div>
    </section>

    
    <section className="doc-section" id="example-release-pipeline">
      <h2>Example: release pipeline</h2>
      <p>This end-to-end example walks through how a <code>release-captain</code> agent orchestrates a multi-stage deployment using spawn grants.</p>
      <h3>Setup</h3>
      <p>An admin has minted the following grant for <code>release-captain</code>:</p>
      <pre><code>{"{\n  \"agent\": \"release-captain\",\n  \"verbs\": [\"run\"],\n  \"targetAllow\": [\"qa-agent\", \"deploy-*\"],\n  \"maxDepth\": 1,\n  \"maxFanOut\": 3,\n  \"treeBudgetUsd\": 10.00,\n  \"expiresAt\": null\n}"}</code></pre>
      <p>This allows <code>release-captain</code> to spawn <code>qa-agent</code> and any <code>deploy-*</code> agent, but only as direct children (depth 1), with at most 3 running simultaneously, and a hard spend cap of $10.00 for the entire tree.</p>
      <h3>Runtime walk-through</h3>
      <ol>
        <li><strong>QA gate:</strong> <code>release-captain</code> spawns <code>qa-agent</code> with the PR diff as input. It waits for the run to complete and checks the result. If QA fails, the pipeline stops.</li>
        <li><strong>Staging deploy:</strong> On QA success, <code>release-captain</code> spawns <code>deploy-staging</code>. It waits for the deploy to succeed before proceeding.</li>
        <li><strong>Production deploy (HITL gate):</strong> Before spawning <code>deploy-prod</code>, <code>release-captain</code> emits a Human-in-the-Loop checkpoint. An operator reviews the staging results and approves. Only then does <code>release-captain</code> spawn <code>deploy-prod</code>.</li>
      </ol>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">synapse · release-captain run-abc</span>
        </div>
        <div className="term-body">
          <div className="term-comment"># release-captain starts</div>
          <div className="term-out info">run-abc  release-captain  started  depth=0</div>
          <div> </div>
          <div className="term-comment"># spawn qa-agent</div>
          <div><span className="term-prompt">spawn</span>{" qa-agent --input '{\"pr\": 482, \"ref\": \"main\"}'"}</div>
          <div className="term-out ok">run-def  qa-agent  started  depth=1  parentRunId=run-abc</div>
          <div className="term-out ok">run-def  qa-agent  succeeded  cost=$2.30  all checks passed</div>
          <div> </div>
          <div className="term-comment"># spawn deploy-staging</div>
          <div><span className="term-prompt">spawn</span>{" deploy-staging --input '{\"ref\": \"main\", \"env\": \"staging\"}'"}</div>
          <div className="term-out ok">run-jkl  deploy-staging  started  depth=1  parentRunId=run-abc</div>
          <div className="term-out ok">run-jkl  deploy-staging  succeeded  cost=$1.58  deployed to staging</div>
          <div> </div>
          <div className="term-comment"># HITL gate — waiting for operator approval</div>
          <div className="term-out warn">hitl  Awaiting approval: "Deploy PR #482 to production?"</div>
          <div className="term-out ok">hitl  Approved by dana@example.com at 14:03:22Z</div>
          <div> </div>
          <div className="term-comment"># spawn deploy-prod</div>
          <div><span className="term-prompt">spawn</span>{" deploy-prod --input '{\"ref\": \"main\", \"env\": \"production\"}'"}</div>
          <div className="term-out ok">run-mno  deploy-prod  started  depth=1  parentRunId=run-abc</div>
          <div className="term-out ok">run-mno  deploy-prod  succeeded  cost=$1.70  deployed to production</div>
          <div> </div>
          <div className="term-out ok">run-abc  release-captain  succeeded  tree-cost=$5.58 / $10.00 budget</div>
        </div>
      </div>
      <p>The entire pipeline used $5.58 of the $10.00 budget. The tree is recorded in full under <code>run-abc</code> and is auditable in the Web UI Tree view.</p>
    </section>

  
  </>
}
