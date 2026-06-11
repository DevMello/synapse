import { CapabilityMock } from '@/components/capabilities/data'

export default function Page() {
  return <>

    <div className="doc-hero">
      <h1>Agent Management</h1>
      <p>Agents are the work units in Synapse. Each agent has a type, a prompt, environment variables, capabilities, and triggers — all configured in the Web UI and executed by the daemon.</p>
    </div>

    <CapabilityMock id="prompt-editor" />
    <CapabilityMock id="versions" />
    <CapabilityMock id="tools" />

    <div className="doc-section" id="agent-types">
      <h2>Agent Types</h2>
      <p>Synapse supports two agent types: <strong>API Model</strong> and <strong>CLI Tool</strong>. Both types run on-daemon and are managed identically — you configure them the same way, trigger them the same way, and monitor them in the same Runs tab. The difference is purely in how the agent executes its work.</p>

      <h3>API Model</h3>
      <p>An API Model agent calls a hosted LLM API directly — Claude, GPT-4, Gemini, or any compatible endpoint. You supply a system prompt and optional tool definitions; Synapse constructs and sends the request on each run, streams the response, and surfaces the output in the Web UI. This type is ideal for text-heavy tasks: code review, content drafting, data extraction, summarization, or any workflow that maps cleanly to a prompt-response loop.</p>

      <h3>CLI Tool</h3>
      <p>A CLI Tool agent wraps an agentic CLI — Claude Code, Codex CLI, Gemini CLI, or any binary that accepts a prompt over stdin and writes output to stdout. The daemon launches the binary as a subprocess, passes the prompt and environment variables, streams its stdout/stderr to the Runs log, and captures the exit code. This type is ideal for long-running coding tasks, multi-step file operations, or workflows that leverage an existing CLI's built-in tool-use.</p>

      <h3>Comparison</h3>
      <table>
        <thead>
          <tr>
            <th>Feature</th>
            <th>API Model</th>
            <th>CLI Tool</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Execution method</td>
            <td>HTTP request to LLM API</td>
            <td>Subprocess (stdin/stdout)</td>
          </tr>
          <tr>
            <td>Supported backends</td>
            <td>Claude, GPT-4, Gemini, any OpenAI-compatible endpoint</td>
            <td>Claude Code, Codex CLI, Gemini CLI, any binary</td>
          </tr>
          <tr>
            <td>System prompt</td>
            <td>Sent as the <code>system</code> field on every request</td>
            <td>Passed as a flag or prepended to stdin, per CLI convention</td>
          </tr>
          <tr>
            <td>Tool use</td>
            <td>Defined in agent config; Synapse handles the tool-call loop</td>
            <td>Handled natively by the CLI binary</td>
          </tr>
          <tr>
            <td>Token/cost tracking</td>
            <td>Read from API response headers</td>
            <td>Parsed from CLI output (best-effort)</td>
          </tr>
          <tr>
            <td>Streaming output</td>
            <td>Server-sent events from API</td>
            <td>Line-buffered stdout from subprocess</td>
          </tr>
          <tr>
            <td>{"Scheduling & webhooks"}</td>
            <td>Supported</td>
            <td>Supported</td>
          </tr>
          <tr>
            <td>Human-in-the-Loop</td>
            <td>Supported</td>
            <td>Supported</td>
          </tr>
          <tr>
            <td>Daemon-managed lifecycle</td>
            <td>Yes</td>
            <td>Yes</td>
          </tr>
        </tbody>
      </table>

      <div className="callout info">
        <strong>Same management surface, different execution model.</strong>
        Regardless of type, every agent appears in the same Agents list, uses the same prompt editor, shares the same version history, and produces runs you monitor in the same Runs tab.
      </div>
    </div>

    
    <div className="doc-section" id="creating-an-agent">
      <h2>Creating an Agent</h2>
      <p>The Web UI provides a five-step wizard for creating a new agent. All fields can be changed after creation — nothing is locked in.</p>

      <div className="steps">
        <div className="step">
          <div className="step-content">
            <div className="step-title">Click "New Agent" in the Agents list</div>
            <div className="step-body">Open the <strong>Agents</strong> section in the left nav of the Web UI. Click the <strong>New Agent</strong> button in the top-right corner of the list. A modal wizard opens.</div>
          </div>
        </div>
        <div className="step">
          <div className="step-content">
            <div className="step-title">Select the agent type</div>
            <div className="step-body">Choose <strong>API Model</strong> if you want to call an LLM API directly, or <strong>CLI Tool</strong> if you want to wrap a CLI binary such as Claude Code or Codex CLI. The remaining wizard steps adapt based on your choice.</div>
          </div>
        </div>
        <div className="step">
          <div className="step-content">
            <div className="step-title">Enter a name and select a model or binary</div>
            <div className="step-body">Give the agent a unique, descriptive name (e.g., <code>pr-reviewer</code> or <code>nightly-summarizer</code>). For API Model agents, select the model from the dropdown — Synapse knows the API parameters for each supported model. For CLI Tool agents, enter the path to the binary or pick a known CLI from the list.</div>
          </div>
        </div>
        <div className="step">
          <div className="step-content">
            <div className="step-title">Write the system prompt in the CodeMirror editor</div>
            <div className="step-body">The prompt editor (see <a href="#prompt-editor">Prompt Editor</a>) opens in the next step. Write the agent's standing instructions: its role, output format, constraints, and any tool-use guidance. You can save a draft at any time with <kbd>Ctrl+S</kbd> before proceeding.</div>
          </div>
        </div>
        <div className="step">
          <div className="step-content">
            <div className="step-title">Configure capabilities and click Save</div>
            <div className="step-body">On the final step, enable the capabilities this agent needs — file access, web search, code execution, or custom tool definitions. Review the summary and click <strong>Save Agent</strong>. The agent is created in a disabled state; enable it from the agent detail header when you are ready for it to accept scheduled and webhook triggers.</div>
          </div>
        </div>
      </div>

      <h3>CLI Alternative</h3>
      <p>You can also create an agent from the terminal without opening the Web UI:</p>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse agent create --name pr-reviewer --type api --model claude-sonnet-4-6</div>
          <div className="term-out ok">Agent "pr-reviewer" created (id: agt_01abc123)</div>
          <div className="term-out info">Next: set a system prompt with <span style={{ color: "#e3dccf" }}>synapse agent prompt set agt_01abc123</span></div>
        </div>
      </div>
      <p>After creation, set the system prompt, environment variables, and triggers using the respective <code>synapse agent prompt</code>, <code>synapse env set</code>, and <code>synapse trigger</code> subcommands, or switch to the Web UI at any point.</p>
    </div>

    
    <div className="doc-section" id="prompt-editor">
      <h2>The Prompt Editor</h2>
      <p>Synapse ships a full-featured CodeMirror editor for authoring and maintaining agent system prompts. The editor is embedded in the agent detail view under the <strong>Prompt</strong> tab.</p>

      <h3>Features</h3>
      <ul>
        <li><strong>Syntax highlighting</strong> — Markdown rendering with code fence highlighting. You can embed example tool calls or JSON schemas inside fenced blocks and they will be colored correctly.</li>
        <li><strong>Word count</strong> — A live word and approximate token count is shown in the editor status bar. This helps you stay within model context limits.</li>
        <li><strong>Draft saving with <kbd>Ctrl+S</kbd></strong> — Pressing <kbd>Ctrl+S</kbd> (or <kbd>Cmd+S</kbd> on macOS) saves the current text as a local draft without creating a new version. Drafts persist across browser sessions and are only visible to you.</li>
        <li><strong>Version history</strong> — Every time you click <strong>Save Prompt</strong> (the explicit save button, distinct from the draft shortcut), a new immutable version is created. Versions are listed in the <strong>Versions</strong> tab and can be tagged, compared, and rolled back.</li>
        <li><strong>Fullscreen mode</strong> — Click the expand icon in the editor toolbar to enter fullscreen. Useful for longer prompts that benefit from more vertical space.</li>
        <li><strong>{"Find & replace"}</strong> — Standard <kbd>Ctrl+H</kbd> opens the CodeMirror find-and-replace panel for bulk edits across a long prompt.</li>
      </ul>

      <div className="callout tip">
        <strong>Tip: use Markdown headings to structure long prompts.</strong>
        Sections like <code>## Role</code>, <code>## Output Format</code>, and <code>## Constraints</code> make prompts easier to read in the editor and easier to diff across versions.
      </div>

      <h3>Saving vs. Drafting</h3>
      <p>There are two distinct save actions in the editor:</p>
      <ul>
        <li><strong>Draft (<kbd>Ctrl+S</kbd>)</strong> — saves silently to browser storage. No version is created. Use this while you are still iterating.</li>
        <li><strong>Save Prompt (button)</strong> — writes to the daemon, creates a new version entry, and (if the agent is enabled) makes the new version the live prompt on the next run.</li>
      </ul>
    </div>

    
    <div className="doc-section" id="version-management">
      <h2>Version Management</h2>
      <p>Every time you click <strong>Save Prompt</strong>, Synapse stores the full prompt text as a new immutable version. Versions are accessible from the agent detail page under the <strong>Versions</strong> tab.</p>

      <h3>Viewing Versions</h3>
      <p>The Versions tab shows a reverse-chronological list of saved prompt versions. Each entry displays:</p>
      <ul>
        <li>Version number (auto-incrementing integer)</li>
        <li>Creation timestamp and author</li>
        <li>Any tags applied to the version</li>
        <li>A short excerpt of the prompt (first 120 characters)</li>
      </ul>

      <h3>Tagging a Version</h3>
      <p>Tags let you mark semantically significant versions so they are easy to find later. Built-in tag values are <code>production</code> and <code>known-good</code>; you can also enter custom tag strings.</p>
      <p>To tag a version: open the Versions tab, click the version row, and click <strong>Tag as production</strong> (or <strong>Add tag</strong> for a custom value). The <code>production</code> tag is special — it determines which version the daemon executes. If no version is tagged <code>production</code>, the most recent saved version is used as the default.</p>

      <div className="callout info">
        <strong>The production tag governs execution.</strong>
        When the daemon starts a run, it fetches the version currently tagged <code>production</code>. Retagging a different version takes effect on the next run — no restart required.
      </div>

      <h3>Comparing Two Versions</h3>
      <p>Select any two versions in the list (hold <kbd>Shift</kbd> or <kbd>Ctrl</kbd> and click) and then click <strong>Compare</strong>. A side-by-side diff view opens, with additions highlighted in green and removals in red. This is useful before promoting a version to production to verify exactly what changed.</p>

      <h3>Rolling Back</h3>
      <p>To roll back to an earlier version, open the Versions tab, click the target version, and click <strong>Set as production</strong>. The tag moves to that version immediately. No data is deleted — the newer versions remain in history and can be re-promoted at any time.</p>

      <div className="callout warning">
        <strong>Rollback does not delete newer versions.</strong>
        Rolling back moves the <code>production</code> tag; it does not remove or overwrite any stored version. Your full history is always preserved.
      </div>
    </div>

    
    <div className="doc-section" id="environment-variables">
      <h2>Environment Variables</h2>
      <p>Environment variables let you pass configuration and credentials to an agent at runtime without hard-coding values in the prompt. All variables are end-to-end encrypted: the cloud stores only ciphertext and the daemon decrypts values in memory immediately before launching a run.</p>

      <h3>Adding Variables in the Web UI</h3>
      <p>Navigate to the agent detail page and open the <strong>Environment</strong> tab. Click <strong>Add Variable</strong> and fill in three fields:</p>
      <ul>
        <li><strong>Key</strong> — the environment variable name, e.g., <code>ANTHROPIC_API_KEY</code>.</li>
        <li><strong>Value</strong> — the value to inject. If the <em>Secret</em> checkbox is checked, this value is encrypted in the browser before the request is sent (see below).</li>
        <li><strong>Secret</strong> — when checked, the browser encrypts the value with the daemon's X25519 public key before transmitting. The cloud stores the resulting ciphertext only. The plaintext value is never logged, never stored in the cloud, and is never visible after the initial save.</li>
      </ul>

      <div className="callout tip">
        <strong>Tip: you never need to rotate the secret for a key rotation.</strong>
        If you rotate an API key, simply update the variable value in the Web UI. The old ciphertext is replaced with a new one. There is no separate rotation workflow.
      </div>

      <h3>Encryption Details</h3>
      <p>When you mark a variable as a secret, the following happens entirely in your browser before the HTTP request is sent:</p>
      <ul>
        <li>The browser fetches the daemon's X25519 public key from the Synapse API.</li>
        <li>A one-time ephemeral X25519 keypair is generated in the browser.</li>
        <li>An ECDH shared secret is derived, then used as a key for AES-256-GCM encryption of the plaintext value.</li>
        <li>The ephemeral public key, the IV, and the ciphertext are base64-encoded and stored as the variable's value.</li>
      </ul>
      <p>The daemon holds the corresponding private key. When a run starts, the daemon decrypts each secret variable in memory and injects it into the run environment. The decrypted value is never written to disk or sent over the network.</p>

      <h3>CLI Alternative</h3>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse env set agt_01abc123 ANTHROPIC_API_KEY --secret</div>
          <div className="term-out info">Enter value (input hidden):</div>
          <div className="term-out ok">Secret variable ANTHROPIC_API_KEY set for agent agt_01abc123</div>
        </div>
      </div>
      <p>The <code>--secret</code> flag causes the CLI to read the value from a hidden prompt (never from a positional argument) and encrypt it locally before sending it to the API, matching the browser behaviour exactly.</p>

      <h3>Non-Secret Variables</h3>
      <p>Variables without the secret flag are stored in plaintext and are visible in the Web UI and CLI. Use non-secret variables for non-sensitive configuration such as <code>LOG_LEVEL</code>, <code>TARGET_REPO</code>, or feature flags.</p>
    </div>

    
    <div className="doc-section" id="triggers">
      <h2>Triggers</h2>
      <p>A trigger is what causes an agent run to start. Synapse supports three trigger types: <strong>Manual</strong>, <strong>Scheduled</strong>, and <strong>Webhook</strong>. Configure triggers in the agent detail page under the <strong>Triggers</strong> tab.</p>

      <h3>Manual</h3>
      <p>The simplest trigger — a human clicks <strong>Run now</strong> in the Web UI or runs <code>synapse agent run AGENT_ID</code> from the CLI. Manual triggers are always available regardless of whether the agent is enabled or disabled. Use manual triggers for on-demand tasks, for testing a new prompt version, or for workflows that must not run automatically.</p>

      <h3>Scheduled</h3>
      <p>Scheduled triggers fire automatically on a time-based cadence. You can specify either a cron expression or a plain-English interval:</p>
      <ul>
        <li><strong>Cron expression</strong> — e.g., <code>0 9 * * 1-5</code> (weekdays at 09:00 UTC).</li>
        <li><strong>Interval</strong> — e.g., <code>every 30 minutes</code>, <code>every 6 hours</code>, <code>daily</code>.</li>
      </ul>
      <p>Scheduled triggers only fire while the agent is <strong>enabled</strong>. If the agent is disabled, scheduled runs are silently skipped (not queued). For full details on cron syntax, timezone handling, and missed-run behaviour, see the <a href="/docs/scheduling">{"Scheduling & Webhooks"}</a> documentation.</p>

      <h3>Webhook</h3>
      <p>A webhook trigger gives each agent a unique, secret HTTP endpoint. Posting to that endpoint starts a run immediately. The request body is available to the agent as the <code>SYNAPSE_WEBHOOK_PAYLOAD</code> environment variable (JSON string).</p>
      <p>The webhook URL has the form:</p>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">webhook url</span>
        </div>
        <div className="term-body">
          <div style={{ color: "#e3dccf" }}>{"https://<your-daemon-host>/webhooks/agt_01abc123/<secret-token>"}</div>
          <div className="term-out info">POST with any JSON body to trigger a run</div>
        </div>
      </div>
      <p>Webhook tokens are rotatable from the Triggers tab. Like scheduled triggers, webhook triggers only fire while the agent is enabled.</p>

      <div className="callout info">
        <strong>Multiple triggers can coexist.</strong>
        An agent can have a scheduled trigger, a webhook trigger, and still be run manually at any time. All three operate independently.
      </div>
    </div>

    
    <div className="doc-section" id="running-agents">
      <h2>Running Agents</h2>
      <p>A "run" is a single execution of an agent. Each run has its own log, status, duration, and cost estimate. Runs are immutable records — they accumulate over time and are never modified after the run completes.</p>

      <h3>Running from the Web UI</h3>
      <p>Open the agent detail page and click <strong>Run now</strong> in the header. Synapse creates a new run record, assigns it a status of <span className="status-chip running">running</span>, and opens the <strong>Runs</strong> tab with a live log stream. Output lines appear in real time as the daemon produces them. When the run finishes, the status chip updates to <span className="status-chip passed">passed</span> (exit 0) or <span className="status-chip blocked">blocked</span> (non-zero exit or error).</p>

      <h3>Running from the CLI</h3>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse agent run agt_01abc123 --wait</div>
          <div className="term-out info">Run started: run_9xkz4p (agent: pr-reviewer)</div>
          <div style={{ color: "#e3dccf" }}>Streaming output...</div>
          <div className="term-out ok">Run completed in 14.3s — 1,842 tokens — est. $0.0028</div>
        </div>
      </div>
      <p>Without <code>--wait</code>, the CLI returns the run ID immediately and the run proceeds in the background. Use <code>synapse run logs RUN_ID --follow</code> to tail the log of a background run.</p>

      <h3>Run Metadata</h3>
      <p>Every run record contains the following metadata, visible in the Web UI and returned by the API:</p>
      <table>
        <thead>
          <tr><th>Field</th><th>Description</th></tr>
        </thead>
        <tbody>
          <tr><td>Status</td><td><span className="status-chip running">running</span> <span className="status-chip passed">passed</span> <span className="status-chip blocked">blocked</span> <span className="status-chip idle">idle</span></td></tr>
          <tr><td>Duration</td><td>Wall-clock time from run start to completion, in seconds</td></tr>
          <tr><td>Token count</td><td>Input + output tokens consumed (API Model); best-effort parse for CLI Tool</td></tr>
          <tr><td>Cost estimate</td><td>Calculated from token count and the model's published pricing</td></tr>
          <tr><td>Trigger type</td><td>One of: manual, scheduled, webhook</td></tr>
          <tr><td>Prompt version</td><td>The version number of the prompt used for this run</td></tr>
        </tbody>
      </table>
    </div>

    
    <div className="doc-section" id="enabling-disabling">
      <h2>Enabling and Disabling</h2>
      <p>Every agent has an enabled/disabled toggle in the agent detail header. The state is visible at a glance in the Agents list as a small <span className="status-chip passed">enabled</span> or <span className="status-chip idle">disabled</span> chip next to the agent name.</p>

      <h3>What Disabling Does</h3>
      <ul>
        <li>Scheduled triggers do <strong>not</strong> fire. Missed schedules are not queued or replayed.</li>
        <li>Webhook triggers return <code>HTTP 423 Locked</code> — the caller knows the agent is intentionally paused.</li>
        <li>Manual runs (<strong>Run now</strong> in the Web UI or <code>synapse agent run</code> in the CLI) still work normally. Disabling does not prevent human-initiated runs.</li>
      </ul>

      <h3>When to Disable</h3>
      <p>Use the disable toggle to pause an agent without deleting its configuration, run history, prompt versions, or environment variables. Common use cases:</p>
      <ul>
        <li>Temporarily halting a scheduled agent while you audit its prompt.</li>
        <li>Pausing an agent that is consuming budget during an incident.</li>
        <li>Keeping a deprecated agent for reference without allowing it to run.</li>
      </ul>

      <div className="callout tip">
        <strong>Disabling is non-destructive.</strong>
        All configuration, prompt history, environment variables, run history, and analytics are fully preserved. Re-enabling the agent restores all triggers immediately.
      </div>

      <h3>CLI</h3>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse agent disable agt_01abc123</div>
          <div className="term-out ok">Agent "pr-reviewer" disabled</div>
          <div><span className="term-prompt">$</span> synapse agent enable agt_01abc123</div>
          <div className="term-out ok">Agent "pr-reviewer" enabled</div>
        </div>
      </div>
    </div>

    
    <div className="doc-section" id="monitoring-analytics">
      <h2>Monitoring and Analytics</h2>
      <p>Synapse gives you two views for understanding an agent's behaviour over time: the <strong>Runs</strong> tab for operational log-level detail, and the <strong>Analytics</strong> tab for aggregate metrics and budget tracking.</p>

      <h3>Runs Tab</h3>
      <p>The Runs tab lists all historical runs for the agent in reverse chronological order. Each row shows:</p>
      <ul>
        <li>Status chip: <span className="status-chip passed">passed</span>, <span className="status-chip blocked">blocked</span>, <span className="status-chip running">running</span>, or <span className="status-chip idle">idle</span> (queued but not yet started)</li>
        <li>Run ID and trigger type (manual / scheduled / webhook)</li>
        <li>Start time and wall-clock duration</li>
        <li>Token count and cost estimate</li>
        <li>Prompt version used</li>
      </ul>
      <p>Click any run row to open the full log viewer. Logs are searchable and support filtering by log level. For runs that are still in progress, the log streams live — no manual refresh needed.</p>

      <h3>Analytics Tab</h3>
      <p>The Analytics tab aggregates run data into the following metrics:</p>
      <ul>
        <li><strong>Daily runs chart</strong> — a bar chart showing runs per day over the selected time window (default: last 30 days). Bars are colour-coded by status (passed / blocked).</li>
        <li><strong>Average cost per run</strong> — the mean cost across all completed runs in the selected window, shown in USD.</li>
        <li><strong>Success rate</strong> — percentage of runs that completed with status <code>passed</code>.</li>
        <li><strong>P50 / P95 duration</strong> — latency percentiles to help you spot outlier runs and set realistic timeouts.</li>
        <li><strong>Token breakdown</strong> — stacked bar showing input vs. output tokens per run, useful for diagnosing prompt bloat.</li>
      </ul>

      <h3>Budget Alerts</h3>
      <p>You can set a spending alert on any agent to receive a notification when the agent's estimated cost exceeds a threshold within a rolling 24-hour window. To configure an alert:</p>
      <ol>
        <li>Open the agent detail page and click the <strong>Analytics</strong> tab.</li>
        <li>Click <strong>Set budget alert</strong>.</li>
        <li>Enter a daily budget threshold (e.g., <code>$5.00</code>).</li>
        <li>Choose notification channels: <strong>email</strong>, <strong>Slack</strong>, or both.</li>
        <li>Click <strong>Save Alert</strong>.</li>
      </ol>
      <p>When the 24-hour rolling cost for the agent exceeds the threshold, Synapse sends a notification immediately. It does not stop the agent — use the <a href="#enabling-disabling">disable toggle</a> if you want to halt execution. A second notification is sent when the rolling cost drops back below the threshold.</p>

      <div className="callout warning">
        <strong>Cost estimates are not exact billing figures.</strong>
        Estimates are calculated from published model pricing at the time of the run. Actual charges from your LLM provider may differ due to pricing changes, discounts, or rounding. Always verify against your provider's billing dashboard.
      </div>

      <h3>Exporting Run Data</h3>
      <p>Click <strong>Export CSV</strong> in the Analytics tab to download a CSV of all run records for the selected time window. The export includes run ID, start time, duration, status, token count, and cost estimate — suitable for import into a spreadsheet or BI tool.</p>
    </div>

  
  </>
}
