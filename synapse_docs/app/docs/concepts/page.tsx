import Link from 'next/link'

const coreConcepts = [
  {
    title: 'Daemons',
    emoji: '🖥️',
    text: 'Local workers that hold secrets, run agents, enforce guardrails, and connect outbound-only to the cloud.',
  },
  {
    title: 'Agents',
    emoji: '🤖',
    text: 'Configured task runners. They can be API-model agents or CLI-tool agents, but both follow the same policy layer.',
  },
  {
    title: 'Runs',
    emoji: '▶️',
    text: 'One execution of an agent, with full traceability, lineage, checkpoints, and resumability.',
  },
  {
    title: 'HITL gates',
    emoji: '✋',
    text: 'Approval pauses for risky actions. Decisions are audited and can be routed through UI, chat, or TUI.',
  },
  {
    title: 'Guardrails',
    emoji: '🛡️',
    text: 'Daemon-enforced rules for command blocking, write scopes, network allow-lists, and spend caps.',
  },
  {
    title: 'Secrets',
    emoji: '🔐',
    text: 'Env vars are encrypted in the browser and decrypted only on the daemon that owns the keypair.',
  },
  {
    title: 'Redaction',
    emoji: '🧽',
    text: 'PII and secrets are removed on-device before logs or traces leave the host.',
  },
  {
    title: 'Orgs & teams',
    emoji: '🏢',
    text: 'RBAC boundaries that control who can view, approve, run, and administer resources.',
  },
  {
    title: 'Capabilities',
    emoji: '🧩',
    text: 'MCP servers and plugins that extend what an agent can do, gated per agent and per daemon.',
  },
]

const lifecycle = [
  {
    title: 'Pair the daemon',
    body: 'Install the worker, authenticate with device code, and register the daemon with the cloud.',
  },
  {
    title: 'Configure the agent',
    body: 'Choose the engine, prompt, schedule, secrets, and capabilities the agent may use.',
  },
  {
    title: 'Trigger a run',
    body: 'Start manually, on a schedule, or from a webhook. The cloud brokers the request to the daemon.',
  },
  {
    title: 'Enforce policy',
    body: 'Guardrails and HITL gates run on the daemon before risky actions are allowed to continue.',
  },
  {
    title: 'Record the trail',
    body: 'Redacted traces, analytics, and checkpoints are persisted for later review and recovery.',
  },
  {
    title: 'Resume or revoke',
    body: 'Runs can resume after loss. Devices can be revoked without changing the user password.',
  },
]

export default function Page() {
  return (
    <article className="docs-page">
      <nav className="docs-breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span>Docs</span>
        <span aria-hidden="true">›</span>
        <span>Core Concepts</span>
      </nav>

      <header className="docs-hero">
        <p className="t-kicker">Core concepts</p>
        <h1 className="t-h1">How Synapse works</h1>
        <p className="t-lead">
          Synapse is built around a strict control-plane / data-plane split. The cloud brokers and
          records; the daemon executes, protects secrets, and enforces policy.
        </p>

        <div className="hero-grid">
          <div className="surface">
            <div className="section-shell">
              <div className="section-heading">
                <div>
                  <p className="section-kicker">Trust boundary</p>
                  <h2 className="t-h2" style={{ marginBottom: 0 }}>
                    The cloud never becomes the executor.
                  </h2>
                </div>
              </div>
              <div className="diagram">
{`Browser
  │
  ▼
Cloud control plane  ←→  audit trail, routing, realtime UI
  │
  ▼
Daemon on your machine ←→ execution, secrets, redaction, checkpoints`}
              </div>
              <div className="pill-row">
                <span className="pill pill-info">Cloud brokers</span>
                <span className="pill pill-ok">Daemon executes</span>
                <span className="pill pill-warn">Outbound only</span>
              </div>
            </div>
          </div>

          <div className="surface-dark">
            <p className="section-kicker" style={{ color: 'var(--accent)' }}>
              Invariants
            </p>
            <dl className="mini-kv">
              <dt>01</dt>
              <dd>Browser and daemon never talk directly.</dd>
              <dt>02</dt>
              <dd>The cloud never executes agents or holds raw provider keys.</dd>
              <dt>03</dt>
              <dd>The daemon connects outbound-only — no inbound ports.</dd>
            </dl>
          </div>
        </div>

        <div className="hero-stack">
          <div className="stat-card">
            <div className="stat-label">Data plane</div>
            <div className="stat-value">Your machine</div>
            <div className="stat-caption">Secrets, execution, redaction, and policy enforcement stay local.</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Control plane</div>
            <div className="stat-value">The cloud</div>
            <div className="stat-caption">Routes commands, stores audit data, and streams realtime updates.</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Recovery</div>
            <div className="stat-value">Checkpointed</div>
            <div className="stat-caption">Long runs survive machine loss and resume from encrypted checkpoints.</div>
          </div>
        </div>
      </header>

      <section className="doc-section">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Core objects</p>
            <h2 className="t-h2">The pieces you work with every day</h2>
          </div>
          <p className="t-body">Each object below maps to a real screen, config file, or runtime responsibility.</p>
        </div>

        <div className="info-grid">
          {coreConcepts.map((item) => (
            <div className="info-card" key={item.title}>
              <div className="info-emoji" aria-hidden="true">
                {item.emoji}
              </div>
              <h3 className="t-h3" style={{ marginBottom: 0 }}>
                {item.title}
              </h3>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="doc-section">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Lifecycle</p>
            <h2 className="t-h2">How a run moves through the system</h2>
          </div>
          <p className="t-body">A run is the unit of execution, audit, and recovery.</p>
        </div>

        <div className="timeline">
          {lifecycle.map((item) => (
            <div className="step-card" key={item.title}>
              <h3 className="step-title">{item.title}</h3>
              <p className="step-body">{item.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="doc-section">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Reference</p>
            <h2 className="t-h2">Ownership at a glance</h2>
          </div>
        </div>

        <div className="table-card">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Concept</th>
                <th>Owned by</th>
                <th>Why it matters</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Secrets</td>
                <td>Daemon</td>
                <td>Decrypted only where execution happens.</td>
              </tr>
              <tr>
                <td>Routing</td>
                <td>Cloud</td>
                <td>Provides stable brokered communication and realtime UI updates.</td>
              </tr>
              <tr>
                <td>Policy enforcement</td>
                <td>Daemon</td>
                <td>Blocks risky commands even if the cloud is compromised.</td>
              </tr>
              <tr>
                <td>Audit trail</td>
                <td>Cloud</td>
                <td>Stores redacted traces, analytics, and approvals.</td>
              </tr>
              <tr>
                <td>Recovery</td>
                <td>Encrypted checkpoint store</td>
                <td>Lets a new daemon resume a run after machine loss.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="doc-section">
        <div className="callout callout-neutral">
          <strong>Start here next</strong>
          If you want the threat model and encryption details, read the Security page. If you want
          the product surface, read the Web UI Guide.
        </div>
      </section>
    </article>
  )
}
