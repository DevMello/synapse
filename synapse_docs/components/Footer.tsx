import Link from 'next/link'

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-logo">
          <span className="logo-mark" aria-hidden="true" />
          Synapse
        </div>
        <div className="footer-links">
          <Link href="/docs/getting-started">Getting Started</Link>
          <Link href="/docs/concepts">Core Concepts</Link>
          <Link href="/docs/security">Security</Link>
          <Link href="/docs/use-cases">Use Cases</Link>
          <Link href="/docs/faq">FAQ</Link>
          <a href="https://github.com/DevMello/synapse" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </div>
        <div className="footer-copy">© 2026 Synapse. Open source under the MIT License.</div>
      </div>
    </footer>
  )
}
