import Link from 'next/link'

const cols = [
  {
    title: 'Product',
    links: [
      { href: '/docs/getting-started', label: 'Getting Started' },
      { href: '/docs/concepts', label: 'Core Concepts' },
      { href: '/docs/marketplace', label: 'Marketplace' },
      { href: '/docs/cli', label: 'CLI Reference' },
    ],
  },
  {
    title: 'Trust',
    links: [
      { href: '/docs/security', label: 'Security' },
      { href: '/docs/hitl', label: 'Human-in-the-Loop' },
      { href: '/docs/daemon', label: 'Daemon' },
      { href: '/docs/faq', label: 'FAQ' },
    ],
  },
  {
    title: 'Build',
    links: [
      { href: '/docs/agents', label: 'Agents' },
      { href: '/docs/orchestration', label: 'Orchestration' },
      { href: '/docs/scheduling', label: 'Scheduling' },
      { href: '/docs/use-cases', label: 'Use Cases' },
    ],
  },
]

export default function Footer() {
  return (
    <footer className="site-footer fx-grid-dark">
      <div className="footer-glow" aria-hidden="true" />
      <div className="footer-inner">
        <div className="footer-brand">
          <div className="footer-logo">
            <span className="logo-mark" aria-hidden="true" />
            <span>Synapse</span>
          </div>
          <p className="footer-tag">
            Agent management with a hard trust boundary. Execution and secrets never leave your
            machine.
          </p>
          <a
            href="https://github.com/DevMello/synapse"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost-dark btn-sm"
          >
            View on GitHub →
          </a>
        </div>

        <div className="footer-cols">
          {cols.map((col) => (
            <div key={col.title} className="footer-col">
              <div className="footer-col-title">{col.title}</div>
              {col.links.map((l) => (
                <Link key={l.href} href={l.href}>
                  {l.label}
                </Link>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="footer-base">
        <span>© 2026 Synapse</span>
        <span>Open source under the MIT License</span>
      </div>
    </footer>
  )
}
