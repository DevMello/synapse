import Link from 'next/link'

export default function Nav() {
  return (
    <nav className="site-nav">
      <div className="nav-inner">
        <Link href="/" className="nav-logo">
          <span className="logo-mark" />
          Synapse
        </Link>
        <div className="nav-links">
          <Link href="/">Home</Link>
          <Link href="/docs/getting-started">Docs</Link>
          <a href="https://github.com/DevMello/synapse" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
          <Link href="/docs/getting-started" className="btn btn-primary">
            Get Started
          </Link>
        </div>
      </div>
    </nav>
  )
}
