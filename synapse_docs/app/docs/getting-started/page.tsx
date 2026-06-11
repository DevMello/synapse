export default function Page() {
  return <>


      <div className="doc-hero">
        <h1>Getting Started</h1>
        <p>Install the Synapse daemon, connect it to the cloud, and run your first agent — all in under five minutes. Your machine executes every agent; the cloud acts only as a secure broker.</p>
      </div>

      
      <div className="doc-section">
        <h2>Prerequisites</h2>
        <p>Before you begin, make sure you have the following:</p>
        <table>
          <thead>
            <tr><th>Requirement</th><th>Details</th></tr>
          </thead>
          <tbody>
            <tr><td><code>Python 3.11+</code></td><td>Check with <code>python --version</code>. Install from <a href="https://python.org" style={{ color: "var(--accent)" }}>python.org</a> if needed.</td></tr>
            <tr><td><code>pip</code></td><td>Bundled with Python 3.11+. Upgrade with <code>pip install --upgrade pip</code>.</td></tr>
            <tr><td>Synapse account</td><td>Sign up at the Web UI. No credit card required for the free tier.</td></tr>
            <tr><td>One open terminal</td><td>The daemon process stays running in the foreground or as a background service.</td></tr>
          </tbody>
        </table>
        <div className="callout info">
          <strong>Note</strong>
          Windows users should run commands in PowerShell 7+ or Windows Terminal. WSL2 also works — treat it as Linux throughout this guide.
        </div>
      </div>

      
      <div className="doc-section">
        <h2>Step 1 — Install synapse-worker</h2>
        <p>Install the daemon package from PyPI. A virtual environment is recommended but not required.</p>
        <div className="terminal" style={{ marginBottom: "20px" }}>
          <div className="term-bar">
            <div className="term-dots"><i></i><i></i><i></i></div>
            <span className="term-file">terminal</span>
          </div>
          <div className="term-body">
            <div><span className="term-prompt">$</span> pip install synapse-worker</div>
            <div className="term-comment"># Collecting synapse-worker</div>
            <div className="term-out info">Downloading synapse_worker-0.4.2-py3-none-any.whl (148 kB)</div>
            <div className="term-out info">Downloading textual-0.61.0-py3-none-any.whl (565 kB)</div>
            <div className="term-out info">Downloading httpx-0.27.0-py3-none-any.whl (75 kB)</div>
            <div className="term-out info">Downloading websockets-12.0-py3-none-any.whl (47 kB)</div>
            <div className="term-out info">Installing collected packages: httpx, websockets, textual, synapse-worker</div>
            <div className="term-out ok">Successfully installed synapse-worker-0.4.2</div>
            <div style={{ marginTop: "12px" }}><span className="term-prompt">$</span> synapse --version</div>
            <div className="term-out ok">synapse-worker 0.4.2</div>
          </div>
        </div>
        <div className="callout tip">
          <strong>Virtual environment</strong>
          Run <code>{"python -m venv .venv && source .venv/bin/activate"}</code> (Linux/macOS) or <code>python -m venv .venv; .venv\Scripts\Activate.ps1</code> (Windows) before installing to keep your global Python clean.
        </div>
      </div>

      
      <div className="doc-section">
        <h2>Step 2 — Log in</h2>
        <p>Synapse uses a device-code flow so your credentials never touch the daemon process. The CLI prints a short code; you approve the device in the Web UI.</p>
        <div className="terminal" style={{ marginBottom: "20px" }}>
          <div className="term-bar">
            <div className="term-dots"><i></i><i></i><i></i></div>
            <span className="term-file">terminal</span>
          </div>
          <div className="term-body">
            <div><span className="term-prompt">$</span> synapse login</div>
            <div className="term-out info">Opening device authorization flow...</div>
            <div style={{ margin: "10px 0", padding: "14px 18px", background: "rgba(255,255,255,0.04)", borderRadius: "10px", border: "1px solid rgba(255,255,255,0.07)" }}>
              <div style={{ color: "#e3dccf", fontSize: "12px", marginBottom: "8px" }}>Your device code:</div>
              <div style={{ fontSize: "26px", letterSpacing: "0.18em", color: "#ef6a2a", fontWeight: "600" }}>A3F7-BK92</div>
              <div style={{ color: "#6b6457", fontSize: "12px", marginTop: "8px" }}>Visit: <span style={{ color: "#5b8fd9" }}>https://app.synapse.sh/devices</span></div>
              <div style={{ color: "#6b6457", fontSize: "12px" }}>Code expires in 15 minutes.</div>
            </div>
            <div className="term-out info">Waiting for approval...</div>
            <div className="term-out info">Waiting for approval...</div>
            <div className="term-out ok">Authenticated as user@example.com</div>
            <div className="term-out ok">Credentials saved to ~/.synapse/credentials.json</div>
          </div>
        </div>
        <div className="steps">
          <div className="step">
            <div className="step-content">
              <div className="step-title">Open the Web UI</div>
              <div className="step-body">Navigate to <strong>app.synapse.sh</strong> in your browser and sign in to your account.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Go to Daemons</div>
              <div className="step-body">Click <strong>Daemons</strong> in the left sidebar, then click <strong>Approve device</strong> in the top-right corner.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Enter the code</div>
              <div className="step-body">Type the 8-character code shown in your terminal (e.g. <code>A3F7-BK92</code>) and click <strong>Confirm</strong>.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Confirm in terminal</div>
              <div className="step-body">The daemon prints <code>Authenticated as user@example.com</code> and writes credentials to <code>~/.synapse/credentials.json</code>.</div>
            </div>
          </div>
        </div>
      </div>

      
      <div className="doc-section">
        <h2>Step 3 — Initialize the daemon</h2>
        <p>Run <code>synapse init</code> to name this daemon instance and generate its configuration file at <code>~/.synapse/daemon.toml</code>.</p>
        <div className="terminal" style={{ marginBottom: "20px" }}>
          <div className="term-bar">
            <div className="term-dots"><i></i><i></i><i></i></div>
            <span className="term-file">terminal</span>
          </div>
          <div className="term-body">
            <div><span className="term-prompt">$</span> synapse init</div>
            <div style={{ marginTop: "8px", color: "#e3dccf" }}>Daemon name <span style={{ color: "#6b6457" }}>(leave blank for hostname "my-macbook-pro")</span>: <span style={{ color: "#ef6a2a" }}>dev-workstation</span></div>
            <div style={{ color: "#e3dccf", marginTop: "4px" }}>Working directory <span style={{ color: "#6b6457" }}>(default ~/.synapse/work)</span>: <span style={{ color: "#ef6a2a" }}></span></div>
            <div style={{ color: "#e3dccf", marginTop: "4px" }}>Max concurrent agents <span style={{ color: "#6b6457" }}>(default 4)</span>: <span style={{ color: "#ef6a2a" }}></span></div>
            <div style={{ marginTop: "12px" }} className="term-out ok">Created ~/.synapse/daemon.toml</div>
            <div className="term-out ok">Registered daemon "dev-workstation" with cloud (id: dae_7x9kp2mn)</div>
            <div className="term-out info">Run `synapse daemon run` to start.</div>
          </div>
        </div>
        <p>The generated <code>~/.synapse/daemon.toml</code> stores your daemon name, working directory, concurrency limit, and cloud endpoint. You can edit it by hand at any time — changes take effect on next startup.</p>
      </div>

      
      <div className="doc-section">
        <h2>Step 4 — Run the daemon</h2>
        <p>Start the daemon process. It opens a terminal UI (TUI) showing live agent activity and streams heartbeats to the cloud every 30 seconds.</p>
        <div className="terminal" style={{ marginBottom: "20px" }}>
          <div className="term-bar">
            <div className="term-dots"><i></i><i></i><i></i></div>
            <span className="term-file">terminal</span>
          </div>
          <div className="term-body">
            <div><span className="term-prompt">$</span> synapse daemon run</div>
            <div style={{ marginTop: "10px", borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: "10px", marginBottom: "10px" }}>
              <span style={{ color: "#ef6a2a", fontWeight: "600" }}>Synapse Daemon</span> <span style={{ color: "#6b6457" }}>v0.4.2</span>
            </div>
            <div className="term-out ok">Loaded config from ~/.synapse/daemon.toml</div>
            <div className="term-out ok">Authenticated as user@example.com</div>
            <div className="term-out ok">Connected to cloud wss://api.synapse.sh/ws</div>
            <div className="term-out ok">Heartbeat OK  <span style={{ color: "#6b6457" }}>(latency: 38 ms)</span></div>
            <div className="term-out info">Daemon "dev-workstation" is online  <span style={{ color: "#6b6457" }}>(id: dae_7x9kp2mn)</span></div>
            <div className="term-out info">Waiting for work...  <span style={{ color: "#6b6457" }}>0 agents running, 0 queued</span></div>
          </div>
        </div>
        <div className="callout warning">
          <strong>Keep this terminal open</strong>
          The daemon must be running for agents to execute. To run it as a background service, see <a href="/docs/daemon" style={{ color: "var(--accent)" }}>Daemon Management</a>.
        </div>
      </div>

      
      <div className="doc-section">
        <h2>Step 5 — Verify in the Web UI</h2>
        <p>Confirm the daemon appears online before creating your first agent.</p>
        <div className="steps">
          <div className="step">
            <div className="step-content">
              <div className="step-title">Open the Web UI</div>
              <div className="step-body">Go to <strong>app.synapse.sh</strong> and sign in if prompted.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Navigate to Daemons</div>
              <div className="step-body">Click <strong>Daemons</strong> in the left sidebar.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Confirm status</div>
              <div className="step-body">Your daemon (<code>dev-workstation</code>) appears in the list with a green <span className="status-chip passed" style={{ fontSize: "10px" }}>Online</span> badge. The "Last seen" column should read "just now".</div>
            </div>
          </div>
        </div>
        <div className="callout info">
          <strong>Not showing online?</strong>
          Make sure <code>synapse daemon run</code> is still running in your terminal. If the daemon registered but shows <span className="status-chip idle" style={{ fontSize: "10px" }}>Offline</span>, check that your firewall allows outbound WebSocket connections on port 443.
        </div>
      </div>

      
      <div className="doc-section">
        <h2>Step 6 — Create your first agent</h2>
        <p>Agents are defined in the Web UI and dispatched to your daemon on demand. The new-agent wizard takes about 30 seconds to complete.</p>
        <div className="steps">
          <div className="step">
            <div className="step-content">
              <div className="step-title">Open Agents</div>
              <div className="step-body">Click <strong>Agents</strong> in the left sidebar, then click <strong>New Agent</strong> in the top-right corner.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Name your agent</div>
              <div className="step-body">Enter a descriptive name such as <code>my-first-agent</code>. Names must be lowercase, alphanumeric, and may include hyphens.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Choose agent type</div>
              <div className="step-body">Select <strong>API Model</strong>. This type calls an LLM API directly — no custom code required.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Select a model</div>
              <div className="step-body">Choose <code>claude-sonnet-4-6</code> from the model dropdown. You can change this later from the agent detail page.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Write a system prompt and save</div>
              <div className="step-body">Enter a system prompt (e.g. <em>"You are a helpful assistant. Answer concisely."</em>), then click <strong>Create Agent</strong>. The agent is saved to the cloud and immediately available to all your daemons.</div>
            </div>
          </div>
        </div>
      </div>

      
      <div className="doc-section">
        <h2>Step 7 — Set your API key</h2>
        <p>API keys are stored as encrypted environment variables. The value is encrypted in your browser before it is sent to the cloud — Synapse never sees the plaintext.</p>
        <div className="steps">
          <div className="step">
            <div className="step-content">
              <div className="step-title">Open agent detail</div>
              <div className="step-body">Click your agent name in the Agents list to open its detail page.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Go to Environment tab</div>
              <div className="step-body">Click the <strong>Environment</strong> tab, then click <strong>Add Variable</strong>.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Enter the key name</div>
              <div className="step-body">Set <strong>Key</strong> to <code>ANTHROPIC_API_KEY</code>.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Enter the value and save</div>
              <div className="step-body">Paste your API key into the <strong>Value</strong> field. The input is masked. Click <strong>Save</strong> — the value is encrypted client-side with your account's public key before transmission.</div>
            </div>
          </div>
        </div>
        <div className="callout tip">
          <strong>Where to get an Anthropic API key</strong>
          Visit <a href="https://console.anthropic.com/settings/keys" style={{ color: "var(--accent)" }}>console.anthropic.com</a> to generate a key. Keys must have at minimum the <code>models:invoke</code> permission.
        </div>
      </div>

      
      <div className="doc-section">
        <h2>Step 8 — Run the agent</h2>
        <p>Trigger a manual run from the Web UI and watch logs stream in real time from your daemon.</p>
        <div className="steps">
          <div className="step">
            <div className="step-content">
              <div className="step-title">Click "Run now"</div>
              <div className="step-body">On the agent detail page, click <strong>Run now</strong>. Synapse dispatches the run to your online daemon within seconds.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Open the Runs tab</div>
              <div className="step-body">Click the <strong>Runs</strong> tab on the agent detail page. Your new run appears at the top with a <span className="status-chip running" style={{ fontSize: "10px" }}>Running</span> badge.</div>
            </div>
          </div>
          <div className="step">
            <div className="step-content">
              <div className="step-title">Stream live logs</div>
              <div className="step-body">Click the run row to open the log viewer. Logs stream line-by-line as the daemon executes the agent. When the run completes the badge changes to <span className="status-chip passed" style={{ fontSize: "10px" }}>Passed</span>.</div>
            </div>
          </div>
        </div>
        <div className="terminal" style={{ margin: "20px 0" }}>
          <div className="term-bar">
            <div className="term-dots"><i></i><i></i><i></i></div>
            <span className="term-file">Run log — my-first-agent / run_3pk8xq2r</span>
          </div>
          <div className="term-body">
            <div className="term-out info">Dispatching run_3pk8xq2r to daemon dev-workstation</div>
            <div className="term-out info">Daemon acknowledged dispatch</div>
            <div className="term-out info">Spawning agent process (model: claude-sonnet-4-6)</div>
            <div className="term-out info">Injecting 1 environment variable</div>
            <div className="term-out ok">Agent started</div>
            <div style={{ marginTop: "6px", color: "#e3dccf" }}><span className="term-comment">[agent]</span> Hello! I'm ready to help. What would you like to do today?</div>
            <div style={{ marginTop: "6px" }} className="term-out ok">Agent exited cleanly (exit 0, 1.34 s)</div>
            <div className="term-out ok">Run complete — status: passed</div>
          </div>
        </div>
        <div className="callout tip">
          <strong>Viewing logs from the daemon TUI</strong>
          The terminal running <code>synapse daemon run</code> also shows live output. Press <kbd style={{ fontFamily: "var(--font-mono)", fontSize: "12px", background: "rgba(0,0,0,0.06)", padding: "1px 5px", borderRadius: "3px" }}>L</kbd> to open the full-screen log pane.
        </div>
      </div>

      
      <div className="doc-section">
        <h2>What's next?</h2>
        <div className="callout tip">
          <strong>You're up and running</strong>
          Your daemon is connected, your first agent ran successfully, and logs streamed live to the Web UI. Here are a few good places to go next:
          <ul style={{ marginTop: "10px", paddingLeft: "18px" }}>
            <li><a href="/docs/concepts" style={{ color: "var(--accent)" }}>Core Concepts</a> — understand daemons, agents, runs, and the broker model in depth.</li>
            <li><a href="/docs/daemon" style={{ color: "var(--accent)" }}>Daemon Management</a> — run the daemon as a system service, configure auto-restart, and manage multiple daemons.</li>
            <li><a href="/docs/agents" style={{ color: "var(--accent)" }}>Agent Management</a> — add tools, configure retries, set concurrency limits, and chain agents.</li>
            <li><a href="/docs/hitl" style={{ color: "var(--accent)" }}>Human-in-the-Loop</a> — pause agent runs and route approval requests to Slack, email, or the Web UI.</li>
            <li><a href="/docs/security" style={{ color: "var(--accent)" }}>Security</a> — understand the end-to-end encryption model for secrets and how signing works.</li>
            <li><a href="/docs/scheduling" style={{ color: "var(--accent)" }}>{"Scheduling & Webhooks"}</a> — trigger agents on a cron schedule or via incoming HTTP webhooks.</li>
          </ul>
        </div>
      </div>

    
  </>
}
