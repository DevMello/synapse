import Link from 'next/link'

const navSections = [
  'App shell & navigation',
  'Dashboard',
  'Agents',
  'Agent detail',
  'Daemons',
  'Connect',
  'Runs',
  'Approvals',
  'Marketplace',
  'Webhooks',
  'Notifications',
  'Settings',
]

const screenCards = [
  {
    title: 'Dashboard',
    emoji: '📊',
    text: 'Fleet-wide health, spend, approvals, active runs, and daemon status in one realtime view.',
  },
  {
    title: 'Agents',
    emoji: '🤖',
    text: 'Browse, filter, and launch agents. Open the wizard to create a new agent or inspect an existing one.',
  },
  {
    title: 'Approvals',
    emoji: '✋',
    text: 'The human-in-the-loop queue. Review paused runs and make approve / deny decisions with context.',
  },
  {
    title: 'Marketplace',
    emoji: '🛒',
    text: 'Install templates, plugins, and capabilities that extend what agents can do.',
  },
]

const shortcuts = [
  ['Cmd/Ctrl + K', 'Open the command palette'],
  ['G then D', 'Jump to Dashboard'],
  ['G then A', 'Jump to Agents'],
  ['G then R', 'Jump to Runs'],
  ['Esc', 'Close palette, drawer, or modal'],
]

export default function Page() {
  return (
    <article className="docs-page">
      <nav className="docs-breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span>Docs</span>
        <span aria-hidden="true">›</span>
        <span>Web UI Guide</span>
      </nav>

      <header className="docs-hero">
        <p className="t-kicker">Web UI</p>
        <h1 className="t-h1">Web UI Guide</h1>
        <p className="t-lead">
          A screen-by-screen guide to the Synapse control surface. Use this as a map for where each
          action lives and what each screen is optimized for.
        </p>

        <div className="hero-grid">
          <div className="surface">
            <div className="section-heading">
              <div>
                <p className="section-kicker">Navigation model</p>
                <h2 className="t-h2" style={{ marginBottom: 0 }}>
                  Three regions, one consistent shell.
                </h2>
              </div>
            </div>
            <ul className="lead-list">
              <li>Sticky header with breadcrumb, search, alerts, and user menu.</li>
              <li>Persistent sidebar for app navigation and workspace switching.</li>
              <li>Main content area that owns the page-specific layout.</li>
              <li>Realtime badges for approvals, alerts, and active statuses.</li>
            </ul>
          </div>

          <div className="surface-dark">
            <p className="section-kicker" style={{ color: 'var(--accent)' }}>
              Screen count
            </p>
            <div className="hero-stack" style={{ gridTemplateColumns: '1fr', gap: '10px' }}>
              <div className="stat-card">
                <div className="stat-label">Primary screens</div>
                <div className="stat-value">12+</div>
                <div className="stat-caption">Dashboard, Agents, Daemons, Runs, Approvals, and more.</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Realtime</div>
                <div className="stat-value">Supabase</div>
                <div className="stat-caption">Live updates without manual refresh.</div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section className="doc-section">
        <div className="toc">
          <p className="toc-label">On this page</p>
          <ol className="toc-list">
            {navSections.map((section) => {
              const anchor = section.toLowerCase().replace(/[^a-z0-9]+/g, '-')
              return (
                <li key={section}>
                  <a href={`#${anchor}`}>{section}</a>
                </li>
              )
            })}
          </ol>
        </div>
      </section>

      <section className="doc-section" id="app-shell-navigation">
        <div className="section-heading">
          <div>
            <p className="section-kicker">App shell & navigation</p>
            <h2 className="t-h2">The layout stays the same everywhere</h2>
          </div>
          <p className="t-body">Once you know the shell, every screen becomes easier to scan.</p>
        </div>

        <div className="compare-grid">
          <div className="surface">
            <h3 className="t-h3">Sidebar</h3>
            <ul className="lead-list">
              <li>Logo links back to the dashboard.</li>
              <li>Connect button starts the daemon pairing flow.</li>
              <li>Monitoring, agents, daemons, settings, and workspace links stay visible.</li>
              <li>Active badges update in realtime.</li>
            </ul>
          </div>
          <div className="surface-dark">
            <h3 className="t-h3">Header</h3>
            <ul className="lead-list">
              <li>Breadcrumb reflects the current route.</li>
              <li>Command palette is reachable from <kbd>Cmd/Ctrl + K</kbd>.</li>
              <li>Notifications and alerts sit in the top-right corner.</li>
              <li>Account menu handles security and org switching.</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="doc-section" id="dashboard">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Dashboard</p>
            <h2 className="t-h2">Fleet health at a glance</h2>
          </div>
        </div>

        <div className="feature-strip">
          {screenCards.slice(0, 2).map((card) => (
            <div className="info-card" key={card.title}>
              <div className="info-emoji" aria-hidden="true">
                {card.emoji}
              </div>
              <h3 className="t-h3" style={{ marginBottom: 0 }}>
                {card.title}
              </h3>
              <p>{card.text}</p>
            </div>
          ))}
        </div>

        <div className="table-card" style={{ marginTop: '14px' }}>
          <table className="compact-table">
            <thead>
              <tr>
                <th>Widget</th>
                <th>Purpose</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Daemons online</td>
                <td>Counts online vs. total registered daemons.</td>
              </tr>
              <tr>
                <td>Active runs</td>
                <td>Shows current execution count across the org.</td>
              </tr>
              <tr>
                <td>Spend today</td>
                <td>Highlights daily usage before it grows into a problem.</td>
              </tr>
              <tr>
                <td>Open approvals</td>
                <td>Surfaces paused runs that need a human decision.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="doc-section" id="agents">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Agents</p>
            <h2 className="t-h2">Browse, launch, and inspect agents</h2>
          </div>
        </div>

        <div className="info-grid">
          {screenCards.slice(1, 4).map((card) => (
            <div className="info-card" key={card.title}>
              <div className="info-emoji" aria-hidden="true">
                {card.emoji}
              </div>
              <h3 className="t-h3" style={{ marginBottom: 0 }}>
                {card.title}
              </h3>
              <p>{card.text}</p>
            </div>
          ))}
        </div>

        <div className="table-card" style={{ marginTop: '14px' }}>
          <table className="compact-table">
            <thead>
              <tr>
                <th>Card field</th>
                <th>Meaning</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Status chip</td>
                <td>Running, passed, blocked, or idle.</td>
              </tr>
              <tr>
                <td>Engine</td>
                <td>Model name or CLI tool identifier.</td>
              </tr>
              <tr>
                <td>Host daemon</td>
                <td>Which machine actually runs the agent.</td>
              </tr>
              <tr>
                <td>Daily spend</td>
                <td>Cost signal for spotting runaway usage early.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="doc-section" id="agent-detail">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Agent detail</p>
            <h2 className="t-h2">One page for everything about an agent</h2>
          </div>
        </div>

        <div className="compare-grid">
          <div className="surface">
            <h3 className="t-h3">Overview tab</h3>
            <ul className="lead-list">
              <li>Current status and enable / disable toggle.</li>
              <li>Host daemon and last run information.</li>
              <li>Schedule preview when the agent is automated.</li>
              <li>Error-rate and lifetime run metrics.</li>
            </ul>
          </div>
          <div className="surface-dark">
            <h3 className="t-h3">Other tabs</h3>
            <ul className="lead-list">
              <li>Editor, versions, schedule, tools, plugins, environment, memory.</li>
              <li>Runs, orchestration, analytics, and audit-oriented views.</li>
              <li>Lazy-loaded heavy tabs keep navigation responsive.</li>
              <li>Changes are reflected without leaving the detail page.</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="doc-section" id="daemons">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Operations</p>
            <h2 className="t-h2">Daemons, connect, runs, and approvals</h2>
          </div>
        </div>

        <div className="timeline">
          <div className="step-card">
            <h3 className="step-title">Daemons</h3>
            <p className="step-body">Shows each machine, its status, heartbeat, OS, and last-seen timing.</p>
          </div>
          <div className="step-card">
            <h3 className="step-title">Connect</h3>
            <p className="step-body">Device authorization flow for pairing a new daemon with the org.</p>
          </div>
          <div className="step-card" id="runs">
            <h3 className="step-title">Runs</h3>
            <p className="step-body">Lists active and historical runs with trace access and state filters.</p>
          </div>
          <div className="step-card" id="approvals">
            <h3 className="step-title">Approvals</h3>
            <p className="step-body">Queues HITL decisions with enough context for a safe, fast review.</p>
          </div>
        </div>
      </section>

      <section className="doc-section" id="marketplace">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Settings & ecosystem</p>
            <h2 className="t-h2">Marketplace, webhooks, notifications, and org settings</h2>
          </div>
        </div>

        <div className="info-grid">
          {[
            { id: 'marketplace', title: 'Marketplace', text: 'Install templates, plugins, and capabilities.' },
            { id: 'webhooks', title: 'Webhooks', text: 'Configure inbound and outbound automations.' },
            { id: 'notifications', title: 'Notifications', text: 'Choose how the product reaches you when events happen.' },
            { id: 'settings', title: 'Settings', text: 'Manage org-level preferences and account behavior.' },
            { id: 'account-security', title: 'Account security', text: 'Review login and security settings.' },
            { id: 'organizations', title: 'Organizations', text: 'Switch orgs and manage membership boundaries.' },
          ].map(({ id, title, text }) => (
            <div className="info-card" key={title} id={id}>
              <h3 className="t-h3" style={{ marginBottom: 0 }}>
                {title}
              </h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="doc-section">
        <div className="table-card">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Shortcut</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {shortcuts.map(([combo, action]) => (
                <tr key={combo}>
                  <td>
                    <kbd>{combo}</kbd>
                  </td>
                  <td>{action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="doc-section">
        <div className="callout callout-neutral">
          <strong>Next stop</strong>
          Use the Web UI to explore the dashboards and agent detail tabs in context, then jump back
          to <Link href="/docs/security">Security</Link> when you want to understand why each screen
          is safe to expose.
        </div>
      </section>
    </article>
  )
}
