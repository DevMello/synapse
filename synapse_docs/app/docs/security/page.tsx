import Link from 'next/link'
import { CapabilityMock } from '@/components/capabilities/data'

const securityLayers = [
  {
    title: 'Device authorization',
    emoji: '🔑',
    text: 'Browser-approved device codes keep credentials out of the terminal and let you revoke a daemon instantly.',
  },
  {
    title: 'X25519 encryption',
    emoji: '🔐',
    text: 'Env vars are encrypted in the browser and stored as ciphertext; only the daemon can decrypt them.',
  },
  {
    title: 'On-device redaction',
    emoji: '🧽',
    text: 'Secrets and PII are removed before traces leave the host, so the cloud only receives scrubbed output.',
  },
  {
    title: 'RBAC + audit',
    emoji: '🧾',
    text: 'Permissions, approvals, and mutations are recorded with enough context to review every decision later.',
  },
]

const controlPoints = [
  ['Cloud sees', 'Agent metadata, redacted traces, encrypted blobs, run state'],
  ['Cloud never sees', 'Raw API keys, unredacted output, daemon private keys'],
  ['Storage boundary', 'Plaintext lives only on the daemon host or in the user keychain'],
  ['Recovery boundary', 'Encrypted checkpoints can be decrypted by authorized daemons'],
]

const authFlow = [
  {
    title: 'Request code',
    body: 'The daemon requests a short-lived device code and verification URI from the cloud.',
  },
  {
    title: 'Approve in browser',
    body: 'The user signs in through an already-authenticated browser session and confirms the device.',
  },
  {
    title: 'Rotate tokens',
    body: 'The daemon polls until approval, then receives rotating tokens stored in the OS keychain.',
  },
  {
    title: 'Revoke cleanly',
    body: 'Revocation invalidates the device without changing the user password or affecting other daemons.',
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
        <span>Security</span>
      </nav>

      <header className="docs-hero">
        <p className="t-kicker">Security</p>
        <h1 className="t-h1">Security Architecture</h1>
        <p className="t-lead">
          Synapse treats the cloud as a broker, not a place to trust with secrets. Execution,
          decryption, and redaction stay on your machine.
        </p>

        <div className="hero-grid">
          <div className="surface-dark">
            <p className="section-kicker" style={{ color: 'var(--accent)' }}>
              Trust model
            </p>
            <div className="diagram dark">
{`Browser
  │ approve device code
  ▼
Cloud control plane
  │ route, audit, realtime
  ▼
Daemon on your machine
  ├─ decrypt env vars
  ├─ run agents
  ├─ redact output
  └─ store checkpoints`}
            </div>
          </div>

          <div className="surface">
            <h2 className="t-h2">What makes the boundary hard?</h2>
            <ul className="lead-list">
              <li>Cloud never receives plaintext secrets.</li>
              <li>Daemon connects outbound only.</li>
              <li>Policy is enforced where code actually runs.</li>
              <li>Every decision is recorded and reviewable.</li>
            </ul>
          </div>
        </div>

        <div className="hero-stack">
          <div className="stat-card">
            <div className="stat-label">Auth</div>
            <div className="stat-value">RFC 8628</div>
            <div className="stat-caption">Device code flow without terminal passwords.</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Encryption</div>
            <div className="stat-value">X25519</div>
            <div className="stat-caption">Browser-side sealed-box encryption for env vars and checkpoints.</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Redaction</div>
            <div className="stat-value">On-device</div>
            <div className="stat-caption">PII and secrets are scrubbed before upload.</div>
          </div>
        </div>
      </header>

      <CapabilityMock id="filtering" />

      <section className="doc-section">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Cloud boundary</p>
            <h2 className="t-h2">What the cloud sees and what it does not</h2>
          </div>
        </div>

        <div className="compare-grid">
          <div className="surface">
            <h3 className="t-h3">Cloud sees</h3>
            {controlPoints.slice(0, 2).map(([label, value]) => (
              <div className="mini-kv" key={label} style={{ marginBottom: '12px' }}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </div>
          <div className="surface-dark">
            <h3 className="t-h3">Cloud never sees</h3>
            {controlPoints.slice(2).map(([label, value]) => (
              <div className="mini-kv" key={label} style={{ marginBottom: '12px' }}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="doc-section">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Protection layers</p>
            <h2 className="t-h2">Defense in depth</h2>
          </div>
          <p className="t-body">Each layer covers a different failure mode, from compromise to misconfiguration.</p>
        </div>

        <div className="feature-strip">
          {securityLayers.map((item) => (
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
            <p className="section-kicker">Device auth</p>
            <h2 className="t-h2">How login works</h2>
          </div>
        </div>

        <div className="timeline">
          {authFlow.map((item) => (
            <div className="step-card" key={item.title}>
              <h3 className="step-title">{item.title}</h3>
              <p className="step-body">{item.body}</p>
            </div>
          ))}
        </div>

        <div className="table-card" style={{ marginTop: '14px' }}>
          <table className="compact-table">
            <thead>
              <tr>
                <th>Property</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Access tokens</td>
                <td>Short-lived and stored in the OS keychain, not plaintext files.</td>
              </tr>
              <tr>
                <td>Refresh tokens</td>
                <td>Rotating per device; reuse yields a fresh token pair.</td>
              </tr>
              <tr>
                <td>Revocation</td>
                <td>Immediate for the targeted device and isolated from other daemons.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="doc-section">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Operational controls</p>
            <h2 className="t-h2">Who can change what</h2>
          </div>
        </div>

        <div className="table-card">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Control</th>
                <th>Purpose</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>RBAC</td>
                <td>Limits who can view, approve, and administer resources.</td>
              </tr>
              <tr>
                <td>Recovery keys</td>
                <td>Decrypt encrypted run checkpoints after machine loss.</td>
              </tr>
              <tr>
                <td>Audit trail</td>
                <td>Records approvals, revocations, and state changes for later review.</td>
              </tr>
              <tr>
                <td>MFA</td>
                <td>Supports stronger browser-session protection for human access.</td>
              </tr>
              <tr>
                <td>Command signing</td>
                <td>Protects daemon-side command execution from forged cloud messages.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="doc-section">
        <div className="callout callout-neutral">
          <strong>Need the product surface?</strong>
          Read the <Link href="/docs/web-ui">Web UI Guide</Link> for the screens that expose these
          controls, or jump back to <Link href="/docs/concepts">Core Concepts</Link> for the system
          model.
        </div>
      </section>
    </article>
  )
}
