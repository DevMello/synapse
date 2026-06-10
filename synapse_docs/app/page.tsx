import Link from 'next/link'
import FaqAccordion from '@/components/FaqAccordion'

export default function Home() {
  const faqItems = [
    {
      question: 'Where does my API key live?',
      answer: (
        <p>
          On your machine only. When you set a secret in the Web UI, your browser encrypts it with
          the daemon&apos;s X25519 public key before the HTTPS request is made. The cloud stores
          ciphertext only — it never sees the plaintext value.
        </p>
      ),
    },
    {
      question: 'Does Synapse open any inbound ports on my machine?',
      answer: (
        <p>
          No. The daemon connects outbound-only to the cloud&apos;s WebSocket hub. Your machine
          never listens for incoming connections — this is one of the three core invariants.
        </p>
      ),
    },
    {
      question: "Can the cloud read my agent's outputs?",
      answer: (
        <p>
          Only redacted versions. Before any log line leaves the daemon, the on-device redaction
          engine strips API keys, passwords, emails, and other PII. The cloud receives scrubbed text
          only.
        </p>
      ),
    },
    {
      question: 'What happens if the cloud goes down?',
      answer: (
        <p>
          Agents currently running continue executing — the daemon is self-contained for execution.
          New commands from the Web UI won&apos;t reach the daemon until the connection is restored.
          HITL gates remain paused until reconnect.
        </p>
      ),
    },
    {
      question: 'What agent types does Synapse support?',
      answer: (
        <p>
          Two types: API model agents (call an LLM API with a prompt and tools — Claude, GPT-4,
          Gemini) and CLI tool agents (wrap a CLI AI tool like Claude Code, Codex CLI, or Gemini
          CLI as a subprocess). Both are managed identically.
        </p>
      ),
    },
    {
      question: 'Is Synapse open source?',
      answer: (
        <p>
          Yes — MIT license. The worker daemon and cloud backend are fully open source at
          github.com/DevMello/synapse. Self-host the backend, or use the managed cloud option for
          teams who don&apos;t want to run infrastructure.
        </p>
      ),
    },
  ]

  return (
    <>
      {/* Hero */}
      <section className="hero fx-grid-dark fx-hatch">
        <div className="fx-aurora" aria-hidden="true"></div>
        <div className="hatch tl" aria-hidden="true"></div>
        <div className="hatch tr" aria-hidden="true"></div>
        <div className="hatch bl" aria-hidden="true"></div>
        <div className="hatch br" aria-hidden="true"></div>
        <div className="hero-inner">
          <div className="eyebrow">
            <span className="eyebrow-pulse" aria-hidden="true"></span>
            Open source · Now in public beta
          </div>
          <h1>
            Agent management with a <em className="serif-accent">hard trust boundary.</em>
          </h1>
          <p>
            Deploy AI agents on your own machines. Execution, secrets, and PII redaction never
            leave the host. The cloud is only a broker and historian.
          </p>
          <div className="hero-actions">
            <Link href="/docs/getting-started" className="btn btn-primary">
              Get Started →
            </Link>
            <a
              href="https://github.com/DevMello/synapse"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-ghost-dark"
            >
              View on GitHub
            </a>
          </div>
          {/* Terminal */}
          <div
            className="terminal"
            style={{ marginTop: '48px', textAlign: 'left', maxWidth: '560px', marginLeft: 'auto', marginRight: 'auto' }}
          >
            <div className="term-bar">
              <div className="term-dots">
                <i></i>
                <i></i>
                <i></i>
              </div>
              <span className="term-file">synapse</span>
            </div>
            <div className="term-body">
              <div className="term-prompt">$ synapse login</div>
              <div className="term-out info">
                Visit https://app.synapse.sh/devices and enter code:
              </div>
              <div style={{ color: '#e3dccf', margin: '4px 0', fontSize: '18px', letterSpacing: '0.15em' }}>
                KRTX-9M2P
              </div>
              <div className="term-out ok">Authenticated as pranav@example.com</div>
              <br />
              <div className="term-prompt">$ synapse daemon run</div>
              <div className="term-out ok">Synapse Daemon v0.9.1 — connected</div>
              <div className="term-out info">
                Heartbeat OK · 0 agents running · awaiting commands
              </div>
              <span className="term-cursor" aria-hidden="true"></span>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="section">
        <div className="section-kicker">Features</div>
        <h2 className="section-title">
          Everything you need to run agents <em className="serif-accent">safely.</em>
        </h2>
        <p className="section-subtitle">
          Built for teams that need visibility, control, and auditability over their AI agents —
          without compromising on capability.
        </p>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon">🔒</div>
            <div className="feature-title">On-Device Execution</div>
            <div className="feature-desc">
              Agents run on your machines. Raw API keys, model outputs, and PII never leave the
              host. The cloud only sees redacted telemetry.
            </div>
          </div>
          <div className="feature-card">
            <div className="feature-icon">🔑</div>
            <div className="feature-title">E2E Encrypted Secrets</div>
            <div className="feature-desc">
              Env var values are X25519 sealed-box encrypted in your browser before transmission.
              The cloud stores ciphertext only — it can never decrypt.
            </div>
          </div>
          <div className="feature-card">
            <div className="feature-icon">✋</div>
            <div className="feature-title">Human-in-the-Loop</div>
            <div className="feature-desc">
              Configurable approval gates pause agents before risky actions. Approve from Web UI,
              Slack, Discord, or TUI. Fully audited.
            </div>
          </div>
          <div className="feature-card">
            <div className="feature-icon">💾</div>
            <div className="feature-title">Durable Runs</div>
            <div className="feature-desc">
              SQLite WAL checkpoints survive machine loss. E2E-encrypted to an org recovery key —
              any authorized daemon can resume.
            </div>
          </div>
          <div className="feature-card">
            <div className="feature-icon">📡</div>
            <div className="feature-title">Real-Time Monitoring</div>
            <div className="feature-desc">
              Live trace viewer, token+cost analytics, anomaly detection, and budget alerts. Every
              run logged to an immutable audit trail.
            </div>
          </div>
          <div className="feature-card">
            <div className="feature-icon">🛒</div>
            <div className="feature-title">Marketplace</div>
            <div className="feature-desc">
              Ready-made agent templates, skills, and plugins. One-click install: pr-reviewer,
              incident-commander, browser-use, GitHub, Postgres, Slack.
            </div>
          </div>
        </div>
      </section>

      {/* Architecture */}
      <section className="dark-section fx-grid-dark">
        <div className="section" style={{ color: 'var(--bone)' }}>
          <div className="section-kicker" style={{ color: 'var(--accent)' }}>
            Architecture
          </div>
          <h2 className="section-title">
            Three products. <em className="serif-accent">One trust boundary.</em>
          </h2>
          <p className="section-subtitle" style={{ color: 'rgba(244,239,232,0.65)' }}>
            Control plane in the cloud. Data plane on your machine. The two never swap roles.
          </p>
          <pre className="arch-pre">{`  Web UI (browser)
      │  REST + Supabase Realtime (WSS)
      ▼
  Cloud Backend  ─── FastAPI + Supabase + Arq
      │  outbound-only WebSocket uplink
      │  (daemon initiates — no inbound ports)
      ▼
  TUI Worker Daemon  (your machine)
      ├── agent runtime (API models + CLI tools)
      ├── secrets vault  (X25519 sealed-box)
      ├── PII redaction  (on-device, before upload)
      └── ruleset engine (blockers · guards · caps)`}</pre>
          <div className="invariants">
            <div className="invariant">
              <div className="invariant-num">Invariant 01</div>
              <div className="invariant-text">
                The browser and the daemon never talk directly — the cloud brokers every message.
              </div>
            </div>
            <div className="invariant">
              <div className="invariant-num">Invariant 02</div>
              <div className="invariant-text">
                The cloud never executes agents or holds raw provider keys — those stay on the
                daemon.
              </div>
            </div>
            <div className="invariant">
              <div className="invariant-num">Invariant 03</div>
              <div className="invariant-text">
                The daemon connects outbound-only — no inbound ports are ever opened on your
                machine.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Security */}
      <section className="section">
        <div className="section-kicker">Security</div>
        <h2 className="section-title">
          Security that doesn&apos;t ask you <em className="serif-accent">to trust us.</em>
        </h2>
        <p className="section-subtitle">
          Every layer is designed so the cloud cannot betray you, even if it wanted to.
        </p>
        <div className="features-grid" style={{ marginTop: '32px' }}>
          <div className="feature-card">
            <div className="feature-title">Device Auth (RFC 8628)</div>
            <div className="feature-desc">
              <code>synapse login</code> prints an 8-char code. Approve in the Web UI. No passwords
              ever typed in the terminal. Per-device tokens are revocable.
            </div>
          </div>
          <div className="feature-card">
            <div className="feature-title">X25519 Sealed-Box Encryption</div>
            <div className="feature-desc">
              Your browser encrypts env var values to the daemon&apos;s public key. The cloud
              receives and stores only opaque ciphertext it cannot read.
            </div>
          </div>
          <div className="feature-card">
            <div className="feature-title">On-Device Redaction</div>
            <div className="feature-desc">
              Regex + entropy scanning (Layer A) and optional Presidio PII detection (Layer B) run
              before any byte is uploaded. The cloud only sees scrubbed output.
            </div>
          </div>
          <div className="feature-card">
            <div className="feature-title">Org Recovery Keys</div>
            <div className="feature-desc">
              Run checkpoints are E2E-encrypted to an org recovery key. Any authorized daemon can
              resume a run after total machine loss.
            </div>
          </div>
        </div>
      </section>

      {/* Use Cases */}
      <section
        className="section"
        style={{
          background: 'var(--bone-1,#ebe5dc)',
          paddingTop: '80px',
          paddingBottom: '80px',
          maxWidth: '100%',
        }}
      >
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 32px' }}>
          <div className="section-kicker">Use Cases</div>
          <h2 className="section-title">Built for real engineering workflows.</h2>
          <div className="use-cases-grid">
            <div className="use-case-card">
              <div className="uc-label">DevOps</div>
              <div className="uc-title">Automated Code Review</div>
              <div className="uc-desc">
                Agent reviews PRs and posts inline comments. HITL gate fires for security findings.
                Cost cap prevents runaway spend.
              </div>
            </div>
            <div className="use-case-card">
              <div className="uc-label">SRE</div>
              <div className="uc-title">Incident Response</div>
              <div className="uc-desc">
                Alert fires → agent pulls runbooks from memory, drafts mitigation steps, posts to
                Slack. Destructive actions require human approval.
              </div>
            </div>
            <div className="use-case-card">
              <div className="uc-label">Data Eng</div>
              <div className="uc-title">Pipeline Operations</div>
              <div className="uc-desc">
                Nightly scheduled agent validates data quality. Anomaly → HITL pause for human
                decision. Ruleset blocks DROP TABLE.
              </div>
            </div>
            <div className="use-case-card">
              <div className="uc-label">Support</div>
              <div className="uc-title">Ticket Triage</div>
              <div className="uc-desc">
                Inbound webhook → agent classifies ticket, finds similar past cases in memory,
                drafts response. Human approves before sending.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="section">
        <div className="section-kicker">FAQ</div>
        <h2 className="section-title">Common questions.</h2>
        <div style={{ maxWidth: '720px', marginTop: '0' }}>
          <FaqAccordion items={faqItems} />
        </div>
      </section>

      {/* CTA */}
      <section className="cta-section fx-grid-dark">
        <div className="fx-aurora" aria-hidden="true"></div>
        <div className="cta-inner">
          <h2 className="cta-title">Start in 5 minutes.</h2>
          <p className="cta-subtitle">
            Install the daemon, authenticate with a device code, and run your first agent — all
            from the command line.
          </p>
          <div className="cta-install">
            <span className="cta-prompt">$</span> pip install synapse-worker
          </div>
          <br />
          <Link href="/docs/getting-started" className="btn btn-primary">
            Read the Docs →
          </Link>
        </div>
      </section>
    </>
  )
}
