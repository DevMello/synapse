import Link from 'next/link'
import FaqAccordion from '@/components/FaqAccordion'
import Reveal from '@/components/fx/Reveal'
import Magnetic from '@/components/fx/Magnetic'
import Counter from '@/components/fx/Counter'
import SynapseField from '@/components/fx/SynapseField'
import CapabilityShowcase from '@/components/capabilities/CapabilityShowcase'

const features = [
  {
    icon: '🔒',
    title: 'On-Device Execution',
    desc: 'Agents run on your machines. Raw API keys, model outputs, and PII never leave the host. The cloud only sees redacted telemetry.',
  },
  {
    icon: '🔑',
    title: 'E2E Encrypted Secrets',
    desc: 'Env var values are X25519 sealed-box encrypted in your browser before transmission. The cloud stores ciphertext only — it can never decrypt.',
  },
  {
    icon: '✋',
    title: 'Human-in-the-Loop',
    desc: 'Configurable approval gates pause agents before risky actions. Approve from Web UI, Slack, Discord, or TUI. Fully audited.',
  },
  {
    icon: '💾',
    title: 'Durable Runs',
    desc: 'SQLite WAL checkpoints survive machine loss. E2E-encrypted to an org recovery key — any authorized daemon can resume.',
  },
  {
    icon: '📡',
    title: 'Real-Time Monitoring',
    desc: 'Live trace viewer, token + cost analytics, anomaly detection, and budget alerts. Every run logged to an immutable audit trail.',
  },
  {
    icon: '🛒',
    title: 'Marketplace',
    desc: 'Ready-made agent templates, skills, and plugins. One-click install: pr-reviewer, incident-commander, browser-use, GitHub, Postgres, Slack.',
  },
]

const security = [
  {
    title: 'Device Auth (RFC 8628)',
    desc: 'synapse login prints an 8-char code. Approve in the Web UI. No passwords ever typed in the terminal. Per-device tokens are revocable.',
  },
  {
    title: 'X25519 Sealed-Box Encryption',
    desc: "Your browser encrypts env var values to the daemon's public key. The cloud receives and stores only opaque ciphertext it cannot read.",
  },
  {
    title: 'On-Device Redaction',
    desc: 'Regex + entropy scanning and optional Presidio PII detection run before any byte is uploaded. The cloud only sees scrubbed output.',
  },
  {
    title: 'Org Recovery Keys',
    desc: 'Run checkpoints are E2E-encrypted to an org recovery key. Any authorized daemon can resume a run after total machine loss.',
  },
]

const useCases = [
  {
    label: 'DevOps',
    title: 'Server-Side Automation',
    desc: 'Deploy daemon anywhere — servers, containers, edge devices. Agents patch CVEs, monitor logs & hardware signals, scale infrastructure. Data never leaves the host.',
  },
  {
    label: 'SRE',
    title: 'Incident Response',
    desc: 'Alert fires → agent pulls runbooks from memory, drafts mitigation steps, posts to Slack. Destructive actions require human approval.',
  },
  {
    label: 'Data Eng',
    title: 'Pipeline Operations',
    desc: 'Nightly scheduled agent validates data quality. Anomaly → HITL pause for human decision. Ruleset blocks DROP TABLE.',
  },
  {
    label: 'Support',
    title: 'Ticket Triage',
    desc: 'Inbound webhook → agent classifies ticket, finds similar past cases in memory, drafts response. Human approves before sending.',
  },
]

const invariants = [
  {
    num: '01',
    text: 'The browser and the daemon never talk directly — the cloud brokers every message.',
  },
  {
    num: '02',
    text: 'The cloud never executes agents or holds raw provider keys — those stay on the daemon.',
  },
  {
    num: '03',
    text: 'The daemon connects outbound-only — no inbound ports are ever opened on your machine.',
  },
]

const faqItems = [
  {
    question: 'Where does my API key live?',
    answer: (
      <p>
        On your machine only. When you set a secret in the Web UI, your browser encrypts it with the
        daemon&apos;s X25519 public key before the HTTPS request is made. The cloud stores ciphertext
        only — it never sees the plaintext value.
      </p>
    ),
  },
  {
    question: 'Does Synapse open any inbound ports on my machine?',
    answer: (
      <p>
        No. The daemon connects outbound-only to the cloud&apos;s WebSocket hub. Your machine never
        listens for incoming connections — this is one of the three core invariants.
      </p>
    ),
  },
  {
    question: "Can the cloud read my agent's outputs?",
    answer: (
      <p>
        Only redacted versions. Before any log line leaves the daemon, the on-device redaction engine
        strips API keys, passwords, emails, and other PII. The cloud receives scrubbed text only.
      </p>
    ),
  },
  {
    question: 'What happens if the cloud goes down?',
    answer: (
      <p>
        Agents currently running continue executing — the daemon is self-contained for execution. New
        commands from the Web UI won&apos;t reach the daemon until the connection is restored. HITL
        gates remain paused until reconnect.
      </p>
    ),
  },
  {
    question: 'What agent types does Synapse support?',
    answer: (
      <p>
        Two types: API model agents (call an LLM API with a prompt and tools — Claude, GPT-4, Gemini)
        and CLI tool agents (wrap a CLI AI tool like Claude Code, Codex CLI, or Gemini CLI as a
        subprocess). Both are managed identically.
      </p>
    ),
  },
  {
    question: 'Is Synapse open source?',
    answer: (
      <p>
        Yes — MIT license. The worker daemon and cloud backend are fully open source at
        github.com/DevMello/synapse. Self-host the backend, or use the managed cloud option for teams
        who don&apos;t want to run infrastructure.
      </p>
    ),
  },
]

const marqueeItems = [
  'On-device execution',
  'X25519 sealed-box',
  'Outbound-only',
  'PII redaction',
  'Human-in-the-loop',
  'Immutable audit trail',
  'Durable runs',
  'Open source · MIT',
]

export default function Home() {
  return (
    <>
      {/* ───────────────────────── Hero ───────────────────────── */}
      <section className="hero">
        <SynapseField />
        <div className="hero-veil" aria-hidden="true" />
        <div className="hero-inner">
          <div className="eyebrow">
            <span className="eyebrow-pulse" aria-hidden="true" />
            Open source · Now in public beta
          </div>
          <h1 className="hero-title">
            Agent management with a{' '}
            <em className="serif-accent">hard trust boundary.</em>
          </h1>
          <p className="hero-lead">
            Deploy AI agents on your own machines. Execution, secrets, and PII redaction never leave
            the host. The cloud is only a broker and historian.
          </p>
          <div className="hero-actions">
            <Magnetic strength={0.4}>
              <Link href="/docs/getting-started" className="btn btn-primary">
                Get Started →
              </Link>
            </Magnetic>
            <Magnetic strength={0.3}>
              <a
                href="https://github.com/DevMello/synapse"
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-ghost-dark"
              >
                View on GitHub
              </a>
            </Magnetic>
          </div>

          <div className="hero-terminal">
            <div className="term-bar">
              <div className="term-dots">
                <i />
                <i />
                <i />
              </div>
              <span className="term-file">synapse</span>
            </div>
            <div className="term-body">
              <div className="term-prompt">$ synapse login</div>
              <div className="term-out info">Visit https://app.synapse.sh/devices and enter code:</div>
              <div className="term-code">KRTX-9M2P</div>
              <div className="term-out ok">Authenticated as pranav@example.com</div>
              <br />
              <div className="term-prompt">$ synapse daemon run</div>
              <div className="term-out ok">Synapse Daemon v0.9.1 — connected</div>
              <div className="term-out info">
                Heartbeat OK · 0 agents running · awaiting commands
                <span className="term-cursor" aria-hidden="true" />
              </div>
            </div>
          </div>
        </div>

        <a href="#features" className="scroll-cue" aria-label="Scroll to content">
          <span className="scroll-cue-track">
            <span className="scroll-cue-thumb" />
          </span>
          Scroll
        </a>
      </section>

      {/* ───────────────────────── Marquee ───────────────────────── */}
      <div className="marquee" aria-hidden="true">
        <div className="marquee-track">
          {[...marqueeItems, ...marqueeItems].map((item, i) => (
            <span key={i} className="marquee-item">
              {item}
              <span className="marquee-dot" />
            </span>
          ))}
        </div>
      </div>

      {/* ───────────────────────── Stats ───────────────────────── */}
      <section className="section stats-section">
        <Reveal className="stats-grid" stagger>
          <div className="stat-block">
            <div className="stat-num">
              <Counter value={3} />
            </div>
            <div className="stat-label">Core invariants, always enforced</div>
          </div>
          <div className="stat-block">
            <div className="stat-num">
              <Counter value={0} />
            </div>
            <div className="stat-label">Inbound ports opened on your machine</div>
          </div>
          <div className="stat-block">
            <div className="stat-num">
              <Counter value={100} suffix="%" />
            </div>
            <div className="stat-label">Secrets encrypted before they leave the browser</div>
          </div>
          <div className="stat-block">
            <div className="stat-num">
              <Counter value={5} suffix=" min" />
            </div>
            <div className="stat-label">From install to your first agent run</div>
          </div>
        </Reveal>
      </section>

      {/* ───────────────────────── Features ───────────────────────── */}
      <section className="section" id="features">
        <Reveal>
          <div className="section-kicker">Features</div>
          <h2 className="section-title">
            Everything you need to run agents <em className="serif-accent">safely.</em>
          </h2>
          <p className="section-subtitle">
            Built for teams that need visibility, control, and auditability over their AI agents —
            without compromising on capability.
          </p>
        </Reveal>
        <Reveal className="features-grid" stagger>
          {features.map((f) => (
            <article className="feature-card" key={f.title} data-cursor>
              <div className="feature-icon">{f.icon}</div>
              <h3 className="feature-title">{f.title}</h3>
              <p className="feature-desc">{f.desc}</p>
            </article>
          ))}
        </Reveal>
      </section>

      {/* ───────────────────────── Capabilities ───────────────────────── */}
      <section className="section" id="capabilities">
        <Reveal>
          <div className="section-kicker">Capabilities</div>
          <h2 className="section-title">
            One control plane. <em className="serif-accent">Every capability.</em>
          </h2>
          <p className="section-subtitle">
            Daemons, approvals, alerts, schedules, a marketplace, versioned prompts, MCP tools,
            on-device filtering, capability packs, and an editable memory — things no other agent
            platform puts behind a single hard trust boundary.
          </p>
        </Reveal>
        <Reveal>
          <CapabilityShowcase />
        </Reveal>
      </section>

      {/* ───────────────────────── Architecture ───────────────────────── */}
      <section className="dark-section fx-grid-dark">
        <div className="dark-glow" aria-hidden="true" />
        <div className="section">
          <Reveal>
            <div className="section-kicker accent">Architecture</div>
            <h2 className="section-title light">
              Three products. <em className="serif-accent">One trust boundary.</em>
            </h2>
            <p className="section-subtitle light">
              Control plane in the cloud. Data plane on your machine. The two never swap roles.
            </p>
          </Reveal>

          <Reveal className="arch-layout">
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
              {invariants.map((inv) => (
                <div className="invariant" key={inv.num}>
                  <div className="invariant-num">Invariant {inv.num}</div>
                  <div className="invariant-text">{inv.text}</div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ───────────────────────── Security ───────────────────────── */}
      <section className="section">
        <Reveal>
          <div className="section-kicker">Security</div>
          <h2 className="section-title">
            Security that doesn&apos;t ask you <em className="serif-accent">to trust us.</em>
          </h2>
          <p className="section-subtitle">
            Every layer is designed so the cloud cannot betray you, even if it wanted to.
          </p>
        </Reveal>
        <Reveal className="security-grid" stagger>
          {security.map((s, i) => (
            <article className="security-card" key={s.title} data-cursor>
              <span className="security-index">{String(i + 1).padStart(2, '0')}</span>
              <h3 className="security-title">{s.title}</h3>
              <p className="security-desc">{s.desc}</p>
            </article>
          ))}
        </Reveal>
      </section>

      {/* ───────────────────────── Use Cases ───────────────────────── */}
      <section className="section usecase-section">
        <Reveal>
          <div className="section-kicker">Use Cases</div>
          <h2 className="section-title">Built for real engineering workflows.</h2>
        </Reveal>
        <Reveal className="use-cases-grid" stagger>
          {useCases.map((u) => (
            <article className="use-case-card" key={u.title} data-cursor>
              <div className="uc-label">{u.label}</div>
              <h3 className="uc-title">{u.title}</h3>
              <p className="uc-desc">{u.desc}</p>
            </article>
          ))}
        </Reveal>
      </section>

      {/* ───────────────────────── FAQ ───────────────────────── */}
      <section className="section faq-section">
        <Reveal>
          <div className="section-kicker">FAQ</div>
          <h2 className="section-title">Common questions.</h2>
        </Reveal>
        <Reveal className="faq-wrap">
          <FaqAccordion items={faqItems} />
        </Reveal>
      </section>

      {/* ───────────────────────── CTA ───────────────────────── */}
      <section className="cta-section fx-grid-dark">
        <div className="dark-glow" aria-hidden="true" />
        <Reveal className="cta-inner">
          <h2 className="cta-title">
            Start in <em className="serif-accent">5 minutes.</em>
          </h2>
          <p className="cta-subtitle">
            Install the daemon, authenticate with a device code, and run your first agent — all from
            the command line.
          </p>
          <div className="cta-install" data-cursor>
            <span className="cta-prompt">$</span> pip install synapse-worker
          </div>
          <Magnetic strength={0.4}>
            <Link href="/docs/getting-started" className="btn btn-primary btn-lg">
              Read the Docs →
            </Link>
          </Magnetic>
        </Reveal>
      </section>
    </>
  )
}
