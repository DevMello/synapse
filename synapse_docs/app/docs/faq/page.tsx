export default function Page() {
  return <>

    <div className="doc-hero">
      <div className="kicker">Support</div>
      <h1>Frequently Asked Questions</h1>
      <p>Common questions about Synapse's security model, architecture, setup, features, pricing, and troubleshooting — answered in full.</p>
    </div>

    
    <div className="doc-section">
      <h2>{"Security & Privacy"}</h2>
      <div className="faq-accordion">

        <details className="faq-item"><summary className="faq-question">
            Where does my API key live?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Your API keys (e.g. <code>OPENAI_API_KEY</code>, <code>ANTHROPIC_API_KEY</code>) are stored exclusively on the daemon machine. When you set them via <code>synapse env set</code> or the Web UI, the value is encrypted with your daemon's X25519 public key before it ever leaves your browser. The cloud stores only the ciphertext — it cannot decrypt or read the value. The key is decrypted by the daemon just before it is injected into an agent run.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Can the Synapse cloud read my agent's outputs?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>No. All run telemetry (tool calls, outputs, logs) passes through an on-device redaction pipeline before upload. Regex/entropy scanners strip secrets and PII (e.g. credit card numbers, SSNs, API keys), and optionally the Presidio NLP model provides deeper analysis. What the cloud stores is a redacted transcript — salted tokens like <code>{"<REDACTED:API_KEY:a91f>"}</code> replace sensitive values.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Does Synapse open any inbound ports on my machine?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>No. The daemon connects outbound-only over a single WebSocket uplink to the cloud. Your machine never listens for incoming connections. This is one of Synapse's three core invariants: the daemon always initiates the connection; the cloud never reaches in.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            What happens if I revoke a device?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>The cloud immediately invalidates that device's access and refresh tokens. The daemon will be disconnected on its next heartbeat (within 30 seconds). Any in-flight runs finish naturally, but no new runs can start and no new commands will be received. Revocation is instant and irreversible — the device must re-run <code>synapse login</code> to reconnect.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Who can see my agents' run logs?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Only members of your org with at least <code>viewer</code> role can see run logs in the Web UI. The raw (pre-redaction) logs never leave the daemon. RBAC is enforced by Postgres Row-Level Security — even Synapse employees cannot query another org's data.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            How are environment variable values protected at rest?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Env var values are stored in the cloud as X25519 sealed-box ciphertext (libsodium). The only key that can decrypt them is the daemon's private key, which lives in the OS keychain on your machine (macOS Keychain, Linux Secret Service, Windows Credential Manager). The cloud cannot decrypt them even with full database access.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            What is the org recovery key and when do I need it?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>The org recovery key is an ed25519 keypair generated when you create your org. The public key is stored in the cloud; the private key is yours to store securely. It is used to decrypt run checkpoints and memory snapshots if you ever need to restore an agent on a new daemon after total machine loss. You only need it in disaster recovery scenarios.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Does Synapse support MFA?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Yes. Web UI logins support TOTP (authenticator apps) and WebAuthn/passkeys (hardware security keys, Face ID, Touch ID). Org admins can enforce MFA for all members. Daemon auth uses the RFC 8628 Device Authorization Grant — the code approval in your already-authenticated browser session serves as the second factor.</p>
          </div></details>

      </div>
    </div>

    
    <div className="doc-section">
      <h2>{"Setup & Installation"}</h2>
      <div className="faq-accordion">

        <details className="faq-item"><summary className="faq-question">
            What are the system requirements for the daemon?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Python 3.11+, a supported OS (macOS 12+, Ubuntu 20.04+, Windows 10+), and outbound internet access on port 443 (HTTPS/WSS). The daemon uses less than 100MB RAM at idle and nearly zero CPU when no agents are running. An SSD is recommended for fast checkpoint write performance.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Can I run multiple daemons on different machines?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Yes. Each daemon authenticates independently with <code>synapse login</code> and appears as a separate device in Web UI → Daemons. You can assign agents to specific daemons (or allow any daemon in the org to run them). This is useful for running CPU-intensive agents on a beefy workstation while keeping a lightweight daemon on a server for scheduled tasks.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            How do I upgrade the daemon?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Run <code>pip install --upgrade synapse-worker</code> (or <code>uv pip install --upgrade synapse-worker</code>). If running as a system service, restart it after upgrading: <code>{"synapse daemon stop && synapse daemon run"}</code> (or <code>systemctl restart synapse</code> / <code>launchctl restart synapse.worker</code>). The cloud and daemon versions are forward/backward compatible within the same minor version.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Do I need Redis or a separate message broker?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>No. The cloud backend runs background jobs (heartbeat sweeps, telemetry rollups, anomaly detection) in-process via a lifespan scheduler. The only external dependency beyond Supabase is an internet connection. There is no Redis, Celery, RabbitMQ, or other broker required.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Can I self-host the Synapse cloud?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Yes. The cloud backend is open source in <code>synapse_cloud/</code>. You need a Supabase project (or self-hosted Postgres + GoTrue) and a server to run the FastAPI app. Set <code>SUPABASE_URL</code>, <code>SUPABASE_ANON_KEY</code>, <code>SUPABASE_SERVICE_ROLE_KEY</code>, and <code>DAEMON_JWT_SECRET</code> in your <code>.env</code>, then <code>uvicorn synapse_cloud.app:create_app --factory</code>. Point daemons to your cloud with <code>synapse login --cloud-url https://your-cloud.example.com</code>.</p>
          </div></details>

      </div>
    </div>

    
    <div className="doc-section">
      <h2>{"Architecture & Trust Model"}</h2>
      <div className="faq-accordion">

        <details className="faq-item"><summary className="faq-question">
            Why can't the browser talk directly to the daemon?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Direct browser-to-daemon communication would require opening an inbound port on your machine, which is Synapse's third invariant violation. It would also leak your machine's IP address and require TLS certificate management. The cloud broker provides a stable, authenticated relay that works even through NAT, firewalls, and dynamic IPs — without any port forwarding.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            What does the cloud actually store?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>The cloud stores: org/member/agent metadata (names, config, settings), redacted run transcripts (PII/secrets stripped), encrypted env var ciphertext (values unreadable), encrypted checkpoint blobs (E2E encrypted to org recovery key), event logs and audit trails, and aggregated analytics (token counts, cost estimates, run durations).</p>
            <p>It does NOT store: raw API keys, raw env var values, unredacted run outputs, or daemon private keys.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            What is the control plane / data plane split?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>The cloud is the control plane — it handles auth, routing, audit, analytics, and brokering commands between your browser and your daemons. Your machine is the data plane — it runs agents, holds secrets, performs redaction, and enforces rulesets. This split means the cloud can be fully compromised without exposing raw secrets or allowing arbitrary code execution on your machine.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            How does Synapse prevent a compromised cloud from harming my machine?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Cloud-to-daemon commands are signed with an ed25519 key (<code>GRANT_SIGNING_KEY</code>), and each command includes a nonce to prevent replay attacks. The daemon verifies every command's signature before executing it. Even if an attacker gained full control of the cloud, they could not forge commands without the signing key, which is configured only on the cloud host and never stored in the database.</p>
          </div></details>

      </div>
    </div>

    
    <div className="doc-section">
      <h2>{"Features & Capabilities"}</h2>
      <div className="faq-accordion">

        <details className="faq-item"><summary className="faq-question">
            What agent types does Synapse support?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Two types: (1) <strong>API model agents</strong> — agents that call an AI API (OpenAI, Anthropic, Google, etc.) directly; you provide the API key via encrypted env var; (2) <strong>CLI tool agents</strong> — agents that wrap CLI tools like Claude Code, Codex CLI, or Gemini CLI; the CLI is installed on the daemon machine and Synapse manages its invocation, I/O, and lifecycle. Both types go through the same redaction, ruleset, and HITL systems.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            How does Human-in-the-Loop (HITL) work on mobile?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>When an agent pauses at a HITL gate, Synapse sends a notification via your configured channels (Slack, Discord, or email). The Slack/Discord notification includes approve/reject buttons — you can action it directly from your phone without opening the Web UI. The Web UI Approvals queue also works on mobile browsers.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Can I import an existing Claude Code session into Synapse?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>You can create a CLI tool agent that wraps Claude Code and include a <code>--resume</code> flag pointing to a checkpoint file. Synapse's checkpoint system can also resume interrupted runs. For brand-new Synapse-managed sessions, the daemon handles all session state automatically.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            What happens if my machine goes offline mid-run?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>The daemon journals each run step to a local SQLite WAL. If the connection drops or the machine goes offline, the run is marked <code>interrupted</code> in the cloud. When the daemon reconnects, it can resume from the last checkpoint — no work is lost. If the machine is permanently lost, the checkpoint (encrypted with the org recovery key) can be restored to any authorized daemon.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            Is there a rate limit on how many agents I can run concurrently?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Concurrent run limits depend on your plan (Community / Pro / Enterprise). The daemon itself enforces a configurable <code>max_concurrent_runs</code> setting in <code>daemon.toml</code>. Beyond plan limits, the practical bottleneck is usually your machine's resources (CPU, RAM) and your AI provider's rate limits.</p>
          </div></details>

      </div>
    </div>

    
    <div className="doc-section">
      <h2>{"Pricing & Licensing"}</h2>
      <div className="faq-accordion">

        <details className="faq-item"><summary className="faq-question">
            Is Synapse open source?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Yes. The daemon (<code>synapse_worker/</code>), cloud backend (<code>synapse_cloud/</code>), and all docs are open source under the MIT license. You can self-host everything for free. The managed cloud (synapse.cloud) is a hosted service with free and paid tiers for teams who don't want to manage infrastructure.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            What's included in the free tier?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>The Community plan includes: 1 daemon, up to 5 agents, 100 runs/month, 30-day log retention, community support. The Pro plan adds unlimited daemons and agents, 1,000 runs/month, 90-day retention, HITL notifications, and email support. Enterprise adds SSO, audit export, SLA, and custom run limits.</p>
          </div></details>

      </div>
    </div>

    
    <div className="doc-section">
      <h2>Troubleshooting</h2>
      <div className="faq-accordion">

        <details className="faq-item"><summary className="faq-question">
            The daemon shows "disconnected" in the Web UI. What do I check?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>(1) Verify the daemon process is running: <code>synapse daemon status</code>. (2) Check outbound connectivity to the cloud URL on port 443. (3) Check daemon logs: <code>synapse daemon logs --since 5m</code>. (4) If the token is expired or revoked, re-run <code>synapse login</code>. (5) Ensure the cloud URL in <code>daemon.toml</code> matches the cloud you authenticated against.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            An agent run is stuck in "running" state but the process seems dead. How do I clear it?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>Go to Web UI → Runs → [the stuck run] → Force Stop. This marks the run as <code>failed</code> and unblocks any waiting processes. On the daemon side, <code>{"synapse agent logs <name> --run <run-id>"}</code> will show whether the process is truly dead. If the daemon restarted mid-run, the checkpoint system will have journaled the last state — a new run with <code>--resume</code> can pick up from there.</p>
          </div></details>

        <details className="faq-item"><summary className="faq-question">
            I'm getting "session limit exceeded" errors. What does that mean?
            <svg className="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </summary><div className="faq-answer">
            <p>This is a rate limit on concurrent API usage from the daemon's AI provider (e.g. OpenAI or Anthropic), not a Synapse limit. Solutions: (1) Reduce <code>max_concurrent_runs</code> in <code>daemon.toml</code>, (2) Add delays between scheduled runs using the overlap policy <code>coalesce</code>, (3) Upgrade your AI provider plan, (4) Set a cost/call cap in the agent's Ruleset to throttle expensive runs automatically.</p>
          </div></details>

      </div>
    </div>

  
  </>
}
