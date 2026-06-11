export default function Page() {
  return <>

    <div className="doc-hero">
      <div className="kicker">Examples</div>
      <h1>Use Cases</h1>
      <p>Real-world walkthroughs showing how teams use Synapse to automate high-stakes workflows with confidence.</p>
    </div>


    <section className="doc-section" id="deployment-automation">
      <div className="uc-label">Use Case 01</div>
      <h2>Server-Side Deployment & Maintenance Automation</h2>
      <p>
        The core power of Synapse is that agents can live anywhere. Deploy a daemon on your production servers,
        and agents can automate critical maintenance: monitoring for CVE disclosures and automatically patching
        dependencies, analyzing request logs in real-time to detect anomalies or performance regressions, pulling
        hardware signals from connected IoT devices and alerting when thresholds are breached. Unlike generic
        automation platforms, Synapse agents execute entirely on the server where the data lives — no raw logs,
        credentials, or sensor data ever transit through the cloud. Configure approval gates to pause before
        destructive actions (apply patches, scale infrastructure), but routine monitoring and diagnostics run
        hands-off.
      </p>

      <h3>Walkthrough</h3>
      <div className="steps">
        <div className="step">
          <div className="step-body">
            <h4>Deploy daemon to production server</h4>
            <p>SSH into your prod box and run <code>pip install synapse-worker && synapse daemon run</code>. The daemon connects outbound-only (no inbound ports). You can deploy multiple daemons across your fleet.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Create maintenance agents with server-side scheduling</h4>
            <p>Define agents that run on a cron schedule or webhook trigger. The <code>cve-patrol</code> agent runs nightly, fetches CVE databases, compares against installed packages, and drafts a patch plan. The <code>log-monitor</code> agent tails request logs in real-time and detects anomalies.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Store secrets on the server only</h4>
            <p>Use <code>synapse env set cve-patrol NPM_TOKEN</code> to store secrets locally, encrypted with your daemon's device key. Secrets never leave the machine.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>CVE agent detects vulnerability and proposes patch</h4>
            <p>The <code>cve-patrol</code> agent wakes at 2 AM, fetches the NVD feed, matches against installed packages, and if a critical CVE is found, drafts a patch plan with testing steps.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>HITL gate pauses before patch deployment</h4>
            <p>The Ruleset Engine fires <code>require-approval</code> on package updates and infrastructure changes. The agent pauses and routes an approval request to your team via Slack or the Web UI.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>On-call engineer reviews and approves</h4>
            <p>The team sees the CVE, the patch plan, the affected services, and projected impact. They can approve, modify, or reject from their phone via Slack.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Agent applies patch to staging, runs tests</h4>
            <p>On approval, the agent applies patches to staging, runs the full test suite, monitors for regressions, and only promotes to production if all checks pass.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Log monitor detects anomaly in real-time</h4>
            <p>In parallel, the <code>log-monitor</code> agent tails access logs. If error rate spikes above 5% or p99 latency exceeds 2s, it sends an immediate alert and drafts a diagnosis (possible causes, rollback steps).</p>
          </div>
        </div>
      </div>

      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">synapse daemon logs --follow (on production server)</span>
        </div>
        <div className="term-body">
          <div className="term-prompt">$ synapse daemon logs --follow</div>
          <div className="term-out ok">Synapse daemon v1.4.2 — connected to cloud</div>
          <div className="term-out"> </div>
          <div className="term-comment"># CVE patrol runs nightly at 2 AM</div>
          <div className="term-out info">[02:00:01] cron     cve-patrol starting (schedule: daily 2 AM)</div>
          <div className="term-out info">[02:00:02] agent    cve-patrol  Checking installed packages...</div>
          <div className="term-out ok">[02:00:05] agent    cve-patrol  Installed: 342 packages</div>
          <div className="term-out info">[02:00:05] agent    cve-patrol  Fetching NVD feed (on-device)...</div>
          <div className="term-out warn">[02:00:18] agent    cve-patrol  CRITICAL: CVE-2025-1234 in express@4.17.1</div>
          <div className="term-out warn">              Severity: 8.6  Remote Code Execution  Published 2 hours ago</div>
          <div className="term-out info">[02:00:19] agent    cve-patrol  Drafting patch plan...</div>
          <div className="term-out ok">[02:00:21] agent    cve-patrol  Plan: upgrade express 4.17.1 → 4.18.2</div>
          <div className="term-out"> </div>
          <div className="term-comment"># HITL gate pauses for approval</div>
          <div className="term-out warn">[02:00:22] hitl     PAUSED — "Apply CVE-2025-1234 patch (express upgrade)"</div>
          <div className="term-out info">[02:00:22] alert    🚨 P0 alert sent to #oncall via Slack</div>
          <div className="term-out info">[02:00:22] hitl     Approval request routed</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Meanwhile, log-monitor runs continuously</div>
          <div className="term-out info">[14:32:11] agent    log-monitor  Monitoring /var/log/app.log for anomalies...</div>
          <div className="term-out info">[14:32:11] agent    log-monitor  Baseline: error_rate=0.2%  p99_latency=340ms</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Anomaly detected in production logs</div>
          <div className="term-out warn">[14:45:33] agent    log-monitor  ⚠ ANOMALY: error_rate=6.2% (30x baseline) p99=4100ms</div>
          <div className="term-out info">[14:45:33] agent    log-monitor  Analyzing last 100 errors...</div>
          <div className="term-out ok">[14:45:36] agent    log-monitor  Root cause hypothesis: memory_exhaustion in worker pool</div>
          <div className="term-out warn">[14:45:37] alert    Anomaly alert posted to #incidents (diagnosis attached)</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Engineer approved CVE patch (30 min later)</div>
          <div className="term-out ok">[02:30:15] hitl     APPROVED by sarah@acme.com</div>
          <div className="term-out info">[02:30:15] agent    cve-patrol  Applying patch to staging...</div>
          <div className="term-out ok">[02:32:44] agent    cve-patrol  Patch applied  npm test passed ✓</div>
          <div className="term-out info">[02:32:45] agent    cve-patrol  Promoting to production...</div>
          <div className="term-out ok">[02:33:22] agent    cve-patrol  Production patched. CVE-2025-1234 mitigated.</div>
          <div className="term-out ok">[02:33:23] alert    ✓ Patch applied. CVE resolved. Summary posted to #oncall.</div>
        </div>
      </div>

      <div className="callout tip">
        <span className="callout-icon">🚀</span>
        <p><strong>Key differentiator: agents live on your infrastructure.</strong> Unlike dispatch-style platforms
        that execute in a managed cloud, Synapse daemons live on your servers, containers, or edge devices. Your
        monitoring data, logs, and hardware signals never leave the machine. Agents can interact with anything
        on the system — not just software APIs, but local hardware sensors, IoT devices, file systems, databases.
        This is the fundamental difference: <em>run agents where your data lives.</em></p>
      </div>
    </section>

    <section className="doc-section" id="incident-response">
      <div className="uc-label">Use Case 02</div>
      <h2>Incident Response Automation</h2>
      <p>
        Production incidents demand fast, coordinated action — but also careful judgment before anything is changed.
        The <code>incident-commander</code> agent acknowledges PagerDuty alerts, pulls CloudWatch logs and metrics,
        drafts a diagnosis, and coordinates the response over Slack, all without touching production infrastructure
        until an on-call engineer explicitly approves the action. The Ruleset Engine hard-blocks irreversible
        commands like instance termination.
      </p>

      <h3>Walkthrough</h3>
      <div className="steps">
        <div className="step">
          <div className="step-body">
            <h4>Install the incident-commander template</h4>
            <p>Install from the Marketplace. The template bundles PagerDuty, Slack, and AWS CloudWatch plugin configurations.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Configure the PagerDuty webhook</h4>
            <p>In PagerDuty, add a webhook extension pointing to the agent's inbound URL. Trigger on <em>incident.triggered</em> events.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Store credentials (all E2E encrypted)</h4>
            <p>Set PagerDuty token, Slack bot token, and AWS credentials via <code>synapse env set incident-commander ...</code>. All values are encrypted with your device key before being stored.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Alert fires — agent gathers diagnostics</h4>
            <p>When an alert triggers, the agent acknowledges the PagerDuty incident, queries CloudWatch for the last 30 minutes of logs and metrics for the affected service, and identifies anomalies.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Diagnosis posted to Slack</h4>
            <p>The agent drafts a diagnosis thread in the incident Slack channel: affected service, error rate spike time, top error patterns, and a recommended remediation action.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>HITL gate fires for any remediation action</h4>
            <p>Before executing any remediation (restart, scale-up, rollback), the daemon pauses and routes to the approvals queue. The Ruleset Engine independently hard-blocks any <code>kubectl delete</code>, <code>aws ec2 terminate-instances</code>, or similar irreversible commands — they cannot be approved.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>On-call engineer approves via Slack</h4>
            <p>The Synapse Slack bot posts an approval card with the full action plan. The engineer taps Approve (or Reject with a note) from their phone — no Web UI required.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Agent executes and posts resolution</h4>
            <p>After approval, the daemon resumes, executes the remediation, monitors recovery metrics, and posts a resolution summary to the Slack thread and PagerDuty timeline.</p>
          </div>
        </div>
      </div>

      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">synapse daemon logs --follow</span>
        </div>
        <div className="term-body">
          <div className="term-prompt">$ synapse daemon logs --follow</div>
          <div className="term-out ok">Synapse daemon v1.4.2 — connected</div>
          <div className="term-out"> </div>
          <div className="term-comment"># PagerDuty webhook received</div>
          <div className="term-out warn">{"[02:31:17] event    PD-ALERT incident #INC-8841 triggered: \"API p95 latency > 2000ms\""}</div>
          <div className="term-out info">[02:31:17] agent    incident-commander spawned (run-id: rc_9f3a)</div>
          <div className="term-out ok">[02:31:18] tool     pagerduty.acknowledge  incident=INC-8841</div>
          <div className="term-out info">[02:31:18] tool     cloudwatch.getLogs  service=api-gateway window=30m</div>
          <div className="term-out ok">[02:31:21] tool     cloudwatch.getLogs  events=14392 errors=1847 (12.9%)</div>
          <div className="term-out info">[02:31:21] tool     cloudwatch.getMetrics  p95_latency=2340ms p99=4100ms</div>
          <div className="term-out info">[02:31:22] agent    Diagnosing root cause...</div>
          <div className="term-out ok">[02:31:24] agent    Root cause: connection pool exhaustion on db-replica-2</div>
          <div className="term-out ok">[02:31:24] tool     slack.postMessage  channel=#incidents  thread created</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Remediation requires approval</div>
          <div className="term-out warn">[02:31:25] hitl     PAUSED — "Restart db-replica-2 connection pool"</div>
          <div className="term-out info">[02:31:25] tool     slack.postApprovalCard  to=@oncall-eng  action="restart db-replica-2"</div>
          <div className="term-out info">[02:31:25] ruleset  checking: "aws rds reboot-db-instance"  → ALLOWED (pending approval)</div>
          <div className="term-out"> </div>
          <div className="term-comment"># On-call engineer approved via Slack (2 min later)</div>
          <div className="term-out ok">[02:33:41] hitl     APPROVED by alex@acme.com (via Slack)</div>
          <div className="term-out ok">[02:33:42] tool     aws.rds.rebootInstance  db=replica-2</div>
          <div className="term-out info">[02:33:52] agent    Monitoring recovery... p95=1820ms (improving)</div>
          <div className="term-out ok">[02:34:30] agent    Recovery confirmed. p95=340ms. Incident resolved.</div>
          <div className="term-out ok">[02:34:31] tool     pagerduty.resolve  incident=INC-8841</div>
        </div>
      </div>

      <div className="callout warning">
        <span className="callout-icon">⚠</span>
        <p><strong>Key feature: Ruleset Engine hard-blocks.</strong> Rules with <code>severity: block</code> fire
        before the HITL check — <code>kubectl delete</code>, <code>aws ec2 terminate-instances</code>, and any
        other irreversible commands are rejected outright. No approval flow can override a block-severity rule.
        This gives teams a hard safety net beneath the approval layer.</p>
      </div>
    </section>


    <section className="doc-section" id="data-pipeline">
      <div className="uc-label">Use Case 03</div>
      <h2>Data Pipeline Operations</h2>
      <p>
        Database performance degrades silently over time as query patterns evolve. The <code>pipeline-ops</code>
        agent runs nightly maintenance automatically: it analyzes slow query logs, proposes index changes with
        cost estimates, waits for a DBA to approve, applies the migration to staging first, validates the
        improvement, and only then promotes to production. The <code>postgres</code> plugin runs on-device,
        so credentials never leave the daemon.
      </p>

      <h3>Walkthrough</h3>
      <div className="steps">
        <div className="step">
          <div className="step-body">
            <h4>Create the pipeline-ops agent with postgres plugin</h4>
            <p>Run <code>synapse agent create pipeline-ops --plugin postgres</code>. Configure staging and production connection strings via <code>synapse env set pipeline-ops DB_STAGING_URL</code> and <code>DB_PROD_URL</code>.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Set the cron schedule</h4>
            <p>Configure <code>schedule: "0 2 * * *"</code> in the agent definition to run nightly at 2 AM UTC. Set <code>overlapPolicy: coalesce</code> to skip if a previous run is still in progress.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Agent runs EXPLAIN ANALYZE on slow queries</h4>
            <p>The agent queries the slow query log table, selects the top 10 queries by total execution time, and runs <code>EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)</code> on each using the on-device postgres plugin.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Index proposals appear in Web UI diff view</h4>
            <p>The agent generates <code>CREATE INDEX CONCURRENTLY</code> statements with projected cost reduction, estimated table lock impact, and index size. These appear as a diff for review in the Web UI.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>require-approval rule fires for production schema changes</h4>
            <p>The Ruleset Engine fires a <code>require-approval</code> rule matching any <code>CREATE INDEX</code> targeting the production schema. The agent cannot proceed without sign-off.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>DBA reviews the index plan</h4>
            <p>In the Approvals queue, the DBA sees the full plan: affected query, query time before/after (estimated), index size, and lock duration. They can approve, reject, or modify individual indexes.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Agent applies migration to staging first</h4>
            <p>On approval, the agent runs the approved <code>CREATE INDEX CONCURRENTLY</code> statements on staging, benchmarks the affected queries, and confirms the expected improvement was achieved.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Agent promotes to production</h4>
            <p>After staging validation passes, the agent applies the same migration to production and posts a summary report — query times, index sizes, duration — as an artifact in the Web UI run history.</p>
          </div>
        </div>
      </div>

      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">synapse agent run pipeline-ops --wait</span>
        </div>
        <div className="term-body">
          <div className="term-prompt">$ synapse agent run pipeline-ops --wait</div>
          <div className="term-out info">Starting pipeline-ops (run-id: rc_7c2b)...</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Slow query analysis</div>
          <div className="term-out info">[02:00:01] db       Connected to staging (on-device plugin)</div>
          <div className="term-out info">[02:00:02] agent    Analyzing slow query log — top 10 queries by total time</div>
          <div className="term-out ok">[02:00:08] agent    Query 1: orders.by_customer  avg=1842ms  calls/day=42000</div>
          <div className="term-out ok">[02:00:08] agent    Query 2: inventory.stock_check  avg=940ms  calls/day=180000</div>
          <div className="term-out ok">[02:00:09] agent    Query 3: analytics.daily_summary  avg=8200ms  calls/day=120</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Index proposals</div>
          <div className="term-out info">[02:00:12] agent    Proposal 1: CREATE INDEX CONCURRENTLY idx_orders_customer_id_created_at</div>
          <div className="term-out info">              Est. improvement: 1842ms → 12ms  |  Est. size: 840 MB  |  Lock: none (concurrent)</div>
          <div className="term-out info">[02:00:12] agent    Proposal 2: CREATE INDEX CONCURRENTLY idx_inventory_sku_warehouse</div>
          <div className="term-out info">              Est. improvement: 940ms → 8ms   |  Est. size: 210 MB  |  Lock: none (concurrent)</div>
          <div className="term-out"> </div>
          <div className="term-comment"># HITL gate — production schema changes require DBA approval</div>
          <div className="term-out warn">[02:00:13] hitl     PAUSED — 2 index proposals pending DBA approval</div>
          <div className="term-out info">[02:00:13] hitl     Approval request sent to: dba-team@acme.com</div>
          <div className="term-out"> </div>
          <div className="term-comment"># DBA approved both proposals (8 hours later, during business hours)</div>
          <div className="term-out ok">[10:14:55] hitl     APPROVED by mike@acme.com — both proposals accepted</div>
          <div className="term-out info">[10:14:55] db       Applying migration to staging...</div>
          <div className="term-out ok">[10:17:22] db       idx_orders_customer_id_created_at created (staging)  2m27s</div>
          <div className="term-out ok">[10:19:44] db       idx_inventory_sku_warehouse created (staging)  2m22s</div>
          <div className="term-out info">[10:19:44] agent    Benchmarking on staging...</div>
          <div className="term-out ok">{"[10:20:01] agent    orders.by_customer: 1842ms → 11ms  ✓ (target: <50ms)"}</div>
          <div className="term-out ok">{"[10:20:01] agent    inventory.stock_check: 940ms → 7ms  ✓ (target: <50ms)"}</div>
          <div className="term-out info">[10:20:01] db       Promoting to production...</div>
          <div className="term-out ok">[10:22:38] db       Production migration complete. Run finished in 8h22m37s.</div>
        </div>
      </div>

      <div className="callout tip">
        <span className="callout-icon">🗄</span>
        <p><strong>Key feature: on-device postgres plugin + staged promotion.</strong> The <code>postgres</code>
        plugin runs entirely inside the daemon — your database credentials and query results never transit through
        the cloud broker. The Ruleset Engine enforces the staging-before-prod sequencing: no <code>CREATE INDEX</code>
        on the production schema can execute without an approval, and the approval flow itself captures the
        staging validation results so approvers see real benchmark data.</p>
      </div>
    </section>


    <section className="doc-section" id="support-triage">
      <div className="uc-label">Use Case 04</div>
      <h2>Support Ticket Triage</h2>
      <p>
        Support teams are overwhelmed by ticket volume. The <code>support-triage</code> agent classifies
        every incoming ticket by severity and category, searches the agent's memory for how similar issues
        were resolved, drafts a context-aware response, and routes it to the right team — all before a human
        reads it. No reply is ever sent without human review and approval, giving support reps fast first
        drafts without sacrificing quality control.
      </p>

      <h3>Walkthrough</h3>
      <div className="steps">
        <div className="step">
          <div className="step-body">
            <h4>Install support-triage and configure Zendesk</h4>
            <p>Install the template from Marketplace. Set your Zendesk subdomain and API token: <code>synapse env set support-triage ZENDESK_TOKEN</code>. Configure the Zendesk webhook to fire on <em>ticket.created</em>.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>New ticket arrives — agent classifies it</h4>
            <p>The agent receives the ticket via webhook, analyzes the subject and body, and assigns severity (P1/P2/P3) and category (billing, technical, feature-request, other) with confidence scores.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Agent searches memory for similar resolutions</h4>
            <p>The memory system performs a semantic search over past resolved tickets. Matching resolutions — including the exact steps taken and time-to-resolution — are injected into the agent's context.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Agent drafts a response</h4>
            <p>Using the classification, past resolutions, and any relevant knowledge base articles, the agent drafts a first response. For technical tickets, it includes diagnostic steps. For billing issues, it cites the relevant policy.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>P1 tickets trigger an immediate page</h4>
            <p>For P1 (critical) tickets, the agent immediately posts an alert to the #support-urgent Slack channel and pages the on-call support engineer via PagerDuty before the approval step.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>All draft responses queue for human approval</h4>
            <p>Every draft — regardless of severity — goes to the Approvals queue. Support reps see the ticket, the draft, the memory citations, and the classification. No message is sent automatically.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Support rep reviews, edits, and approves</h4>
            <p>The rep can approve the draft as-is, edit it inline (the Web UI shows a diff of their changes vs. the agent's draft), or reject with feedback. Edits are fed back into memory as corrections.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Agent sends reply and updates memory</h4>
            <p>On approval, the agent posts the reply via the Zendesk API. The resolved ticket — including the final response and any rep edits — is stored in agent memory for future reference.</p>
          </div>
        </div>
      </div>

      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">synapse agent logs support-triage --follow</span>
        </div>
        <div className="term-body">
          <div className="term-prompt">$ synapse agent logs support-triage --follow</div>
          <div className="term-out ok">Agent support-triage is running</div>
          <div className="term-out"> </div>
          <div className="term-comment"># New ticket received via Zendesk webhook</div>
          <div className="term-out info">[14:02:11] webhook  ticket #84291 received: "Cannot export invoice PDF - error 500"</div>
          <div className="term-out info">[14:02:11] agent    Classifying ticket...</div>
          <div className="term-out ok">[14:02:12] agent    severity=P2  category=technical  confidence=0.94</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Memory search for similar past tickets</div>
          <div className="term-out info">[14:02:12] memory   Searching: "invoice pdf export error 500"</div>
          <div className="term-out ok">{"[14:02:13] memory   Match 1 (score=0.91): ticket #71834 — \"PDF export fails for invoices > 50 line items\""}</div>
          <div className="term-out info">              Resolution: cleared orphaned export job from queue — resolved in 12 min</div>
          <div className="term-out ok">[14:02:13] memory   Match 2 (score=0.87): ticket #68102 — "Bulk export 500 error on Pro plan"</div>
          <div className="term-out info">              Resolution: temporary storage quota exceeded, auto-cleared — resolved in 4 min</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Draft response generated with memory context</div>
          <div className="term-out info">[14:02:14] agent    Drafting response using 2 memory citations...</div>
          <div className="term-out ok">[14:02:15] agent    Draft ready (312 words, 3 diagnostic steps, 2 memory citations)</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Approval queue</div>
          <div className="term-out warn">[14:02:15] hitl     QUEUED — awaiting support rep approval</div>
          <div className="term-out info">[14:02:15] hitl     Assigned to: support-queue (next available rep)</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Rep approved with minor edit (7 min later)</div>
          <div className="term-out ok">[14:09:44] hitl     APPROVED by jessica@acme.com (1 edit: personalized greeting)</div>
          <div className="term-out ok">[14:09:45] tool     zendesk.postReply  ticket=84291  public=true</div>
          <div className="term-out ok">[14:09:45] memory   Resolution stored for future reference</div>
        </div>
      </div>

      <div className="callout tip">
        <span className="callout-icon">🧠</span>
        <p><strong>Key feature: persistent memory with semantic search.</strong> The memory system gives
        <code>support-triage</code> institutional knowledge that grows with every resolved ticket. When a new
        ticket arrives, the agent retrieves the most semantically similar past resolutions and cites them
        explicitly in its draft — support reps can see exactly which past cases informed the response. Every
        rep edit is also stored, continuously improving response quality over time.</p>
      </div>
    </section>


    <section className="doc-section" id="multi-agent-research">
      <div className="uc-label">Use Case 05</div>
      <h2>Multi-Agent Research Pipeline</h2>
      <p>
        Complex research tasks benefit from parallelism and specialization, but uncontrolled agent spawning
        risks ballooning costs. The <code>research-director</code> agent orchestrates a team of specialist
        sub-agents — literature search, data analysis, and report writing — under a strict spend budget.
        The daemon enforces the budget as a hard ceiling: once the tree hits <code>treeBudgetUsd</code>,
        no further sub-agent spawning is permitted, regardless of what the orchestrator requests.
      </p>

      <h3>Walkthrough</h3>
      <div className="steps">
        <div className="step">
          <div className="step-body">
            <h4>Create research-director with orchestration grant</h4>
            <p>Define the orchestration grant in the agent config: <code>targets: ["literature-*", "data-analyst", "report-writer"]</code>, <code>maxDepth: 1</code>, <code>maxFanOut: 3</code>, <code>treeBudgetUsd: 25.00</code>. Without an explicit grant, spawning is rejected.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>User triggers the agent with a research topic</h4>
            <p>Run <code>synapse agent run research-director --input "market sizing: enterprise AI observability tools 2025"</code>. The director agent begins planning the research strategy.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Director spawns literature-search and data-analyst in parallel</h4>
            <p>The director issues two concurrent spawn calls. Both sub-agents start immediately. <code>literature-search</code> queries academic databases and news sources; <code>data-analyst</code> queries market data APIs.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Sub-agents run independently and return results</h4>
            <p>Each sub-agent completes its task and returns structured results to the parent. The daemon tracks individual costs for each run and accumulates them against the tree budget.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Director synthesizes and spawns report-writer</h4>
            <p>After both sub-agents complete, the director synthesizes their outputs and spawns <code>report-writer</code> with the combined context. The budget check confirms sufficient headroom before spawning.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Report-writer produces the final report</h4>
            <p><code>report-writer</code> produces a formatted markdown report with executive summary, market sizing estimates, competitive landscape, and source citations.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Report stored as artifact in Web UI</h4>
            <p>The final report is stored in agent memory and published as a downloadable artifact in the Web UI run detail page, alongside the full agent tree view.</p>
          </div>
        </div>
        <div className="step">
          <div className="step-body">
            <h4>Web UI tree view shows full lineage and costs</h4>
            <p>The Web UI renders an interactive tree of all 4 runs (director + 3 sub-agents) with individual token counts, costs, and durations. Total cost is confirmed under the $25.00 ceiling.</p>
          </div>
        </div>
      </div>

      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">synapse agent run research-director --wait</span>
        </div>
        <div className="term-body">
          <div className="term-prompt">$ synapse agent run research-director --input "market sizing: enterprise AI observability tools 2025" --wait</div>
          <div className="term-out info">Starting research-director (run-id: rc_5e1a)  budget=$25.00</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Director plans research strategy</div>
          <div className="term-out info">[09:00:01] agent    research-director  Planning research strategy...</div>
          <div className="term-out ok">[09:00:03] agent    research-director  Strategy: parallel lit-search + data-analyst, then report-writer</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Spawning sub-agents in parallel</div>
          <div className="term-out ok">[09:00:03] spawn    literature-search-1  run-id=rc_5e1b  parent=rc_5e1a  budget-remaining=$25.00</div>
          <div className="term-out ok">[09:00:03] spawn    data-analyst-1       run-id=rc_5e1c  parent=rc_5e1a  budget-remaining=$25.00</div>
          <div className="term-out info">[09:00:03] agent    literature-search-1  Querying: ArXiv, G2, TechCrunch, Gartner...</div>
          <div className="term-out info">[09:00:03] agent    data-analyst-1       Querying: Crunchbase, PitchBook, SEC filings...</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Sub-agents complete</div>
          <div className="term-out ok">[09:02:14] agent    literature-search-1  Complete  cost=$4.12  sources=47</div>
          <div className="term-out ok">[09:03:31] agent    data-analyst-1       Complete  cost=$6.84  data-points=312</div>
          <div className="term-out info">[09:03:31] budget   Tree spend so far: $10.96  remaining: $14.04</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Director synthesizes and spawns report-writer</div>
          <div className="term-out info">[09:03:35] agent    research-director  Synthesizing results...</div>
          <div className="term-out ok">[09:03:40] spawn    report-writer-1      run-id=rc_5e1d  parent=rc_5e1a  budget-remaining=$14.04</div>
          <div className="term-out info">[09:03:40] agent    report-writer-1      Writing report (context: 28k tokens)...</div>
          <div className="term-out ok">[09:06:12] agent    report-writer-1      Complete  cost=$8.71  pages=14</div>
          <div className="term-out"> </div>
          <div className="term-comment"># Final summary</div>
          <div className="term-out ok">[09:06:13] agent    research-director  Complete  cost=$2.18</div>
          <div className="term-out ok">[09:06:13] budget   Total tree cost: $22.05 / $25.00  (11.8% headroom)</div>
          <div className="term-out ok">[09:06:13] memory   Report stored: "AI Observability Market 2025 — 14pp"</div>
          <div className="term-out ok">[09:06:13] artifact Published to Web UI run rc_5e1a</div>
          <div className="term-out info">View tree: https://app.synapse.dev/runs/rc_5e1a/tree</div>
        </div>
      </div>

      <div className="callout tip">
        <span className="callout-icon">🌳</span>
        <p><strong>Key feature: <code>treeBudgetUsd</code> hard ceiling.</strong> The daemon tracks cumulative
        spend across the entire agent tree in real time. When a spawn call would push the tree over
        <code>treeBudgetUsd</code>, the daemon rejects it — the orchestrator cannot override this.
        The Web UI tree view provides full lineage visibility: every sub-agent run, its individual cost,
        token count, duration, and relationship to the parent, rendered as an interactive graph.</p>
      </div>
    </section>

  
  </>
}
