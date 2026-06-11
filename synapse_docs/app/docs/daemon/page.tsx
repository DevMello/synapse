import DaemonAnalytics from '@/components/DaemonAnalytics'
import { CapabilityMock } from '@/components/capabilities/data'

export default function Page() {
  return <>

    <div className="doc-hero">
      <h1>Daemon Management</h1>
      <p>The TUI Worker Daemon is the on-device process that executes agents, holds secrets, enforces guardrails, and maintains a persistent outbound connection to the cloud.</p>
    </div>

    <CapabilityMock id="daemons" />

    <div className="doc-section" id="installation">
      <h2>Installation</h2>
      <p>The daemon ships as a standalone Python package. Python 3.11 or newer is required. Install it from PyPI with a single command:</p>

      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> pip install synapse-worker</div>
          <div className="term-out info">Collecting synapse-worker</div>
          <div className="term-out info">  Downloading synapse_worker-1.4.2-py3-none-any.whl (382 kB)</div>
          <div className="term-out info">Installing collected packages: synapse-worker</div>
          <div className="term-out ok">Successfully installed synapse-worker-1.4.2</div>
          <div style={{ marginTop: "8px" }}><span className="term-prompt">$</span> synapse --version</div>
          <div className="term-out ok">synapse-worker 1.4.2</div>
        </div>
      </div>

      <div className="callout tip">
        <strong>Tip — faster installs with uv</strong>
        <a href="https://github.com/astral-sh/uv" target="_blank" rel="noopener noreferrer"><code>uv</code></a> resolves and installs packages significantly faster than pip.
        Run <code>uv pip install synapse-worker</code> or, if you manage a project environment, <code>uv add synapse-worker</code>.
      </div>

      <h3>Platform support</h3>
      <table>
        <thead>
          <tr><th>Platform</th><th>Supported</th><th>Notes</th></tr>
        </thead>
        <tbody>
          <tr><td>{"macOS (Apple Silicon & Intel)"}</td><td><span className="status-chip passed">supported</span></td><td>Recommended for local development. Launchd service integration available.</td></tr>
          <tr><td>Linux (x86-64, arm64)</td><td><span className="status-chip passed">supported</span></td><td>Full systemd unit support. Works in containers and on servers.</td></tr>
          <tr><td>Windows 10 / 11 (x86-64)</td><td><span className="status-chip passed">supported</span></td><td>Windows Service integration via <code>synapse daemon install</code>.</td></tr>
        </tbody>
      </table>
    </div>

    
    <div className="doc-section" id="authentication">
      <h2>Authentication — <code>synapse login</code></h2>
      <p>The daemon authenticates to the Synapse cloud using the OAuth 2.0 Device Authorization Grant (RFC 8628). No browser session is required on the device — only an outbound HTTPS connection.</p>

      <div className="terminal" style={{ marginBottom: "24px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse login</div>
          <div className="term-out info">Opening device authorization flow…</div>
          <div style={{ marginTop: "6px", color: "#e3dccf" }}>  Your device code: <strong style={{ color: "#ef6a2a", letterSpacing: "0.12em" }}>KRTX-9M2P</strong></div>
          <div style={{ color: "#e3dccf" }}>  Approve at:       <span style={{ color: "#5b8fd9" }}>https://app.synapse.run/devices</span></div>
          <div style={{ color: "#6b6457", marginTop: "4px" }}>  Waiting for approval… (expires in 15 min)</div>
          <div style={{ marginTop: "10px" }} className="term-out ok">Authenticated as user@example.com</div>
          <div className="term-out info">Token stored in ~/.synapse/credentials.toml</div>
        </div>
      </div>

      <div className="steps">
        <div className="step">
          <div className="step-content">
            <div className="step-title">Run <code>synapse login</code></div>
            <div className="step-body">Execute the command in any terminal on the machine you want to register. The CLI contacts the Synapse authorization server and receives a short-lived device code.</div>
          </div>
        </div>
        <div className="step">
          <div className="step-content">
            <div className="step-title">Note the 8-character code</div>
            <div className="step-body">The terminal displays a code in the format <code>XXXX-XXXX</code> (e.g. <code>KRTX-9M2P</code>). This code is valid for 15 minutes.</div>
          </div>
        </div>
        <div className="step">
          <div className="step-content">
            <div className="step-title">Visit the approval URL in any browser</div>
            <div className="step-body">Navigate to <code>https://app.synapse.run/devices</code> from any device where you are already logged in to the Synapse Web UI.</div>
          </div>
        </div>
        <div className="step">
          <div className="step-content">
            <div className="step-title">Enter the code in Web UI → Daemons → Approve Device</div>
            <div className="step-body">Paste or type the 8-character code, confirm the machine name and permissions, then click <strong>Approve</strong>. The cloud issues a long-lived refresh token scoped to that device.</div>
          </div>
        </div>
        <div className="step">
          <div className="step-content">
            <div className="step-title">Terminal confirms authentication</div>
            <div className="step-body">Within seconds the terminal prints <em>Authenticated as user@example.com</em> and stores the credential in <code>~/.synapse/credentials.toml</code>. The machine is now registered in your organization's daemon roster.</div>
          </div>
        </div>
      </div>

      <div className="callout warning">
        <strong>Token security</strong>
        <code>~/.synapse/credentials.toml</code> contains a long-lived refresh token. Protect it with appropriate filesystem permissions (<code>chmod 600</code>). If the file is compromised, revoke the device immediately via <strong>Web UI → Daemons → Revoke Access</strong>.
      </div>
    </div>

    
    <div className="doc-section" id="initialization">
      <h2>Initialization — <code>synapse init</code></h2>
      <p>After authentication, run <code>synapse init</code> to configure the daemon for this machine. The wizard creates a <code>daemon.toml</code> file in <code>~/.synapse/</code>.</p>

      <div className="terminal" style={{ marginBottom: "24px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse init</div>
          <div className="term-out info">Synapse daemon setup wizard</div>
          <div style={{ marginTop: "8px", color: "#e3dccf" }}>  Daemon name <span className="term-comment">(default: macbook-pro-pranav)</span>: <span style={{ color: "#ef6a2a" }}>dev-laptop</span></div>
          <div style={{ color: "#e3dccf" }}>  Cloud URL <span className="term-comment">(default: https://api.synapse.run)</span>: </div>
          <div style={{ color: "#e3dccf" }}>  Log level <span className="term-comment">[debug/info/warn/error]</span> <span className="term-comment">(default: info)</span>: </div>
          <div style={{ color: "#e3dccf" }}>  Max concurrent runs <span className="term-comment">(default: 4)</span>: <span style={{ color: "#ef6a2a" }}>8</span></div>
          <div style={{ marginTop: "8px" }} className="term-out ok">Created ~/.synapse/daemon.toml</div>
          <div className="term-out info">Run `synapse daemon run` to start the daemon.</div>
        </div>
      </div>

      <h3><code>~/.synapse/daemon.toml</code> reference</h3>
      <table>
        <thead>
          <tr><th>Key</th><th>Type</th><th>Default</th><th>Description</th></tr>
        </thead>
        <tbody>
          <tr>
            <td><code>name</code></td>
            <td>string</td>
            <td>hostname</td>
            <td>Human-readable label shown in the Web UI Daemons list.</td>
          </tr>
          <tr>
            <td><code>cloud_url</code></td>
            <td>string</td>
            <td><code>https://api.synapse.run</code></td>
            <td>Base URL of the Synapse cloud API. Change for self-hosted deployments.</td>
          </tr>
          <tr>
            <td><code>log_level</code></td>
            <td>string</td>
            <td><code>info</code></td>
            <td>Verbosity level. Use <code>debug</code> for troubleshooting, <code>warn</code> for production.</td>
          </tr>
          <tr>
            <td><code>max_concurrent_runs</code></td>
            <td>integer</td>
            <td><code>4</code></td>
            <td>Maximum number of agent runs executing simultaneously on this daemon.</td>
          </tr>
          <tr>
            <td><code>heartbeat_interval_s</code></td>
            <td>integer</td>
            <td><code>30</code></td>
            <td>Seconds between keep-alive pings sent to the cloud. Reduce on unreliable networks.</td>
          </tr>
        </tbody>
      </table>

      <p>Edit <code>~/.synapse/daemon.toml</code> directly at any time. Changes take effect on the next daemon start or restart.</p>
    </div>

    
    <div className="doc-section" id="running">
      <h2>Running the Daemon</h2>
      <p>Three modes are available depending on your workflow: foreground, interactive TUI, and system service.</p>

      <h3>Foreground mode</h3>
      <p>The simplest way to run the daemon — useful during development and testing. Press <kbd>Ctrl+C</kbd> to stop.</p>

      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse daemon run</div>
          <div className="term-out ok">Synapse daemon v1.4.2 starting</div>
          <div className="term-out info">Connected to https://api.synapse.run</div>
          <div className="term-out ok">Registered as "dev-laptop" in org "Acme Corp"</div>
          <div className="term-out info">Heartbeat every 30s · max 8 concurrent runs</div>
          <div className="term-out ok">Daemon ready — waiting for work</div>
          <div style={{ color: "#6b6457", marginTop: "6px" }}>  Press Ctrl+C to stop.</div>
        </div>
      </div>

      <h3>TUI dashboard — <code>synapse tui</code></h3>
      <p>The interactive terminal dashboard gives a real-time view of all activity without leaving the terminal. Launch it instead of (or alongside) <code>synapse daemon run</code>:</p>

      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse tui</div>
          <div className="term-out ok">Starting TUI dashboard…</div>
        </div>
      </div>

      <p>The TUI is split into four panes:</p>
      <ul>
        <li><strong>Agents</strong> — lists all agents registered to this daemon with their current status (idle, running, errored).</li>
        <li><strong>Live</strong> — streams real-time log output from the active run, updated line by line.</li>
        <li><strong>Approvals</strong> — surfaces pending human-in-the-loop approval requests; use arrow keys and Enter to approve or reject without leaving the terminal.</li>
        <li><strong>Settings</strong> — shows the active <code>daemon.toml</code> values and lets you toggle log verbosity on the fly.</li>
      </ul>

      <h3>System service — <code>synapse daemon install</code></h3>
      <p>For unattended or production machines, install the daemon as an OS-managed service so it starts automatically at boot and restarts on failure.</p>

      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse daemon install</div>
          <div className="term-out info">Detected platform: macOS (launchd)</div>
          <div className="term-out ok">Wrote ~/Library/LaunchAgents/run.synapse.daemon.plist</div>
          <div className="term-out ok">Service loaded and started</div>
          <div style={{ marginTop: "8px", color: "#6b6457" }}>  <span className="term-comment"># Linux (systemd)</span></div>
          <div style={{ color: "#e3dccf" }}>  Wrote /etc/systemd/system/synapse-daemon.service</div>
          <div style={{ color: "#e3dccf" }}>  systemctl enable --now synapse-daemon</div>
          <div style={{ marginTop: "8px", color: "#6b6457" }}>  <span className="term-comment"># Windows</span></div>
          <div style={{ color: "#e3dccf" }}>  Registered "Synapse Daemon" as a Windows Service (sc.exe)</div>
        </div>
      </div>

      <table>
        <thead>
          <tr><th>Platform</th><th>Service manager</th><th>Auto-start</th><th>Restart on crash</th></tr>
        </thead>
        <tbody>
          <tr><td>macOS</td><td>launchd (<code>.plist</code>)</td><td>At login</td><td>Yes (<code>KeepAlive true</code>)</td></tr>
          <tr><td>Linux</td><td>systemd (<code>.service</code>)</td><td>At boot</td><td>Yes (<code>Restart=on-failure</code>)</td></tr>
          <tr><td>Windows</td><td>Windows Services (<code>sc.exe</code>)</td><td>At boot</td><td>Yes (failure actions configured)</td></tr>
        </tbody>
      </table>

      <p>To remove the service, run:</p>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse daemon uninstall</div>
          <div className="term-out ok">Service stopped and removed</div>
        </div>
      </div>
    </div>

    
    <div className="doc-section" id="monitoring">
      <h2>Monitoring</h2>

      <h3>Status snapshot — <code>synapse daemon status</code></h3>
      <p>Prints a point-in-time summary of the local daemon.</p>

      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse daemon status</div>
          <div style={{ marginTop: "6px", color: "#e3dccf" }}>  Version          <span style={{ color: "#4ec46a" }}>1.4.2</span></div>
          <div style={{ color: "#e3dccf" }}>  Uptime           <span style={{ color: "#4ec46a" }}>3d 7h 22m</span></div>
          <div style={{ color: "#e3dccf" }}>  Connected org    <span style={{ color: "#4ec46a" }}>Acme Corp</span></div>
          <div style={{ color: "#e3dccf" }}>  Last heartbeat   <span style={{ color: "#4ec46a" }}>4s ago</span></div>
          <div style={{ color: "#e3dccf" }}>  Agents running   <span style={{ color: "#ef6a2a" }}>2 / 8</span></div>
          <div style={{ color: "#e3dccf" }}>  Pending approvals <span style={{ color: "#e0a93b" }}>1</span></div>
        </div>
      </div>

      <h3>Live log stream — <code>synapse daemon logs</code></h3>
      <p>Tail structured daemon logs directly in the terminal. Use <code>--follow</code> to stream in real time:</p>

      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse daemon logs --tail 50 --follow</div>
          <div className="term-out info">2026-06-10T09:14:02Z  INFO  heartbeat sent  latency=18ms</div>
          <div className="term-out ok">2026-06-10T09:14:12Z  INFO  run started  agent=gh-triage  run_id=r_8d3f</div>
          <div className="term-out info">2026-06-10T09:14:45Z  INFO  approval requested  step="label issue"</div>
          <div className="term-out warn">2026-06-10T09:15:03Z  WARN  run paused — awaiting human approval  run_id=r_8d3f</div>
          <div className="term-out ok">2026-06-10T09:15:31Z  INFO  approval granted by user@example.com</div>
          <div className="term-out ok">2026-06-10T09:15:31Z  INFO  run resumed  run_id=r_8d3f</div>
        </div>
      </div>

      <h3>Web UI — Daemons dashboard</h3>
      <p>Navigate to <strong>Web UI → Daemons</strong> for a centralized view of every daemon registered to your organization:</p>
      <ul>
        <li>Online / offline <span className="status-chip passed">online</span> <span className="status-chip idle">offline</span> status chips updated in real time.</li>
        <li><strong>Last seen</strong> timestamp derived from the most recent heartbeat.</li>
        <li>Machine info: OS, Python version, daemon version, hostname.</li>
        <li>Per-daemon active run count and concurrency limit.</li>
      </ul>
    </div>


    <div className="doc-section" id="analytics">
      <h2>Analytics</h2>
      <p>The daemon detail page in the Web UI includes an <strong>Analytics</strong> tab that aggregates every run executed on this machine — across all of its agents — into a single dashboard. Use the agent filter to scope every metric and breakdown to one agent, or leave it on <strong>All agents</strong> for the daemon-wide totals.</p>

      <DaemonAnalytics />

      <p>The same metrics surfaced per-agent (see <a href="/docs/agents#monitoring-analytics">Agent Monitoring &amp; Analytics</a>) roll up here at the daemon level:</p>
      <ul>
        <li><strong>Total tokens</strong> — combined input + output tokens consumed by every run on the daemon, with the input/output split.</li>
        <li><strong>Spend</strong> — estimated cost over the window, plus the average cost per run.</li>
        <li><strong>Average latency</strong> — run-weighted wall-clock latency across all selected runs.</li>
        <li><strong>Tool calls</strong> — total tool invocations, alongside the run success rate.</li>
        <li><strong>Cost by model</strong> — spend, runs, tokens, and tool calls grouped by the model that produced them — so a single CLI Tool agent that switches between models is broken out per model.</li>
      </ul>

      <div className="callout info">
        <strong>Filter by agent in the breakdown.</strong>
        Selecting an agent in the dropdown recomputes the stat cards, the cost-by-model chart, the token split, and the per-row table to that agent only. This makes it easy to see which agent is responsible for the bulk of a daemon's spend or latency before drilling into its individual <a href="/docs/agents#running-agents">runs</a>.
      </div>

      <div className="callout warning">
        <strong>Cost estimates are not exact billing figures.</strong>
        Daemon-level totals are the sum of per-run estimates calculated from published model pricing at run time. Always reconcile against your LLM provider's billing dashboard.
      </div>
    </div>


    <div className="doc-section" id="capabilities">
      <h2>Capabilities</h2>
      <p>Capabilities are optional integrations (GitHub, Slack, Jira, filesystem tools, etc.) that extend what agents can do. They are installed at the daemon level and then granted to individual agents.</p>

      <h3>Listing installed capabilities</h3>
      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse capability list</div>
          <div style={{ marginTop: "6px", color: "#e3dccf" }}>  NAME        VERSION   STATUS</div>
          <div style={{ color: "#e3dccf" }}>  ─────────── ───────── ──────────</div>
          <div className="term-out ok">  filesystem  1.2.0     installed</div>
          <div className="term-out ok">  github      2.0.1     installed</div>
          <div style={{ color: "#8a8378" }}>  slack       —         not installed</div>
          <div style={{ color: "#8a8378" }}>  jira        —         not installed</div>
        </div>
      </div>

      <h3>Installing a capability</h3>
      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse capability install github</div>
          <div className="term-out info">Downloading github capability v2.0.1…</div>
          <div className="term-out ok">Installed github capability v2.0.1</div>
          <div className="term-out info">Restart the daemon to activate: synapse daemon restart</div>
        </div>
      </div>

      <div className="callout info">
        <strong>Per-agent capability grants</strong>
        Installing a capability on the daemon does not automatically expose it to every agent. You must explicitly grant each capability to agents individually via <strong>Web UI → Agents → [agent name] → Capabilities</strong> tab, or using <code>{"synapse agent capability grant <agent> github"}</code>.
      </div>
    </div>

    
    <div className="doc-section" id="multiple-daemons">
      <h2>Multiple Daemons</h2>
      <p>Each machine runs a single daemon process. Multiple machines — each with its own daemon — can all belong to the same organization simultaneously.</p>

      <h3>Viewing all daemons</h3>
      <p>Navigate to <strong>Web UI → Daemons</strong> to see every connected and recently-disconnected daemon in your org. Each entry shows its name, status chip, last heartbeat, OS, and active run count.</p>

      <h3>Assigning agents to daemons</h3>
      <p>When creating or editing an agent, the <strong>Execution</strong> tab lets you choose:</p>
      <ul>
        <li><strong>Any available</strong> — the cloud schedules the run on whichever daemon is online and has capacity. Best for high-availability setups.</li>
        <li><strong>Specific daemon</strong> — pins the agent to one named machine. Use this when an agent needs access to local files, a VPN, or hardware that only exists on that machine.</li>
      </ul>

      <h3>Recommended topology</h3>
      <table>
        <thead>
          <tr><th>Daemon name</th><th>Purpose</th><th>Notes</th></tr>
        </thead>
        <tbody>
          <tr><td><code>dev-laptop</code></td><td>Local development</td><td>High log verbosity, unrestricted capabilities, used by individual engineers.</td></tr>
          <tr><td><code>ci-runner-01</code></td><td>Staging / CI</td><td>Runs against staging APIs; separate credentials from production.</td></tr>
          <tr><td><code>prod-server-01</code></td><td>Production</td><td>Locked down; only approved agents with scoped capabilities.</td></tr>
        </tbody>
      </table>

      <div className="callout tip">
        <strong>Tip</strong>
        Name daemons clearly and consistently. The name is visible in every run log entry, making it easy to trace where a run executed.
      </div>
    </div>

    
    <div className="doc-section" id="revocation">
      <h2>Revoking a Device</h2>
      <p>If a machine is decommissioned, lost, or compromised, revoke its daemon token immediately to prevent further access.</p>

      <h3>Revoke via Web UI</h3>
      <ol>
        <li>Go to <strong>Web UI → Daemons</strong>.</li>
        <li>Click the daemon you want to revoke.</li>
        <li>Click <strong>Revoke Access</strong> in the daemon detail panel.</li>
        <li>Confirm the action. The refresh token is invalidated on the server within seconds. Any in-flight runs are allowed to finish; new runs will be rejected.</li>
      </ol>

      <div className="callout warning">
        <strong>Immediate effect</strong>
        Revocation is not deferred. Once confirmed, the daemon loses connectivity and any agents pinned to it will fail to schedule until re-authenticated.
      </div>

      <h3>Re-authenticating after revocation</h3>
      <p>To reconnect the same machine under a new token, run <code>synapse login</code> again and complete the device authorization flow:</p>
      <div className="terminal">
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse login</div>
          <div className="term-out info">Previous token revoked — starting fresh device authorization…</div>
          <div style={{ color: "#e3dccf" }}>  Your device code: <strong style={{ color: "#ef6a2a", letterSpacing: "0.12em" }}>PLXW-4Z7Q</strong></div>
          <div style={{ color: "#e3dccf" }}>  Approve at:       <span style={{ color: "#5b8fd9" }}>https://app.synapse.run/devices</span></div>
        </div>
      </div>
    </div>

    
    <div className="doc-section" id="upgrading">
      <h2>Upgrading</h2>
      <p>Keep the daemon up to date to receive bug fixes, new capabilities, and security patches.</p>

      <h3>Simple upgrade (foreground / TUI mode)</h3>
      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> pip install --upgrade synapse-worker</div>
          <div className="term-out info">Downloading synapse_worker-1.5.0-py3-none-any.whl</div>
          <div className="term-out ok">Successfully installed synapse-worker-1.5.0</div>
        </div>
      </div>

      <h3>Upgrading a system service (zero-manual steps)</h3>
      <p>When running as a managed service, stop the service, upgrade the package, and restart:</p>
      <div className="terminal" style={{ marginBottom: "20px" }}>
        <div className="term-bar">
          <div className="term-dots"><i></i><i></i><i></i></div>
          <span className="term-file">Terminal</span>
        </div>
        <div className="term-body">
          <div><span className="term-prompt">$</span> synapse daemon stop <span className="term-comment">{"&& pip install --upgrade synapse-worker && synapse daemon start"}</span></div>
          <div className="term-out ok">Daemon stopped</div>
          <div className="term-out info">Downloading synapse_worker-1.5.0-py3-none-any.whl</div>
          <div className="term-out ok">Successfully installed synapse-worker-1.5.0</div>
          <div className="term-out ok">Daemon started (v1.5.0)</div>
        </div>
      </div>

      <div className="callout tip">
        <strong>Tip — pin to a minor version in production</strong>
        Use <code>pip install "synapse-worker~=1.5"</code> to allow patch upgrades while preventing breaking minor-version changes from landing automatically.
      </div>

      <div className="callout info">
        <strong>Downtime during upgrade</strong>
        The daemon is offline for only as long as the pip install takes (typically a few seconds). Runs queued in the cloud during that window are dispatched immediately once the daemon reconnects.
      </div>
    </div>

  
  </>
}
