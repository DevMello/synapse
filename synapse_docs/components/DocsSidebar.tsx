'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/docs/getting-started', label: 'Getting Started' },
  { href: '/docs/concepts', label: 'Core Concepts' },
  { href: '/docs/daemon', label: 'Daemon Management' },
  { href: '/docs/agents', label: 'Agent Management' },
  { href: '/docs/hitl', label: 'Human-in-the-Loop' },
  { href: '/docs/security', label: 'Security' },
  { href: '/docs/web-ui', label: 'Web UI Guide' },
  { href: '/docs/scheduling', label: 'Scheduling & Webhooks' },
  { href: '/docs/marketplace', label: 'Marketplace' },
  { href: '/docs/orchestration', label: 'Agent Orchestration' },
  { href: '/docs/memory', label: 'Memory System' },
  { href: '/docs/cli', label: 'CLI Reference' },
  { href: '/docs/use-cases', label: 'Use Cases' },
  { href: '/docs/faq', label: 'FAQ' },
]

export default function DocsSidebar() {
  const pathname = usePathname()
  return (
    <aside className="docs-sidebar">
      <h3>Documentation</h3>
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={pathname === item.href ? 'active' : undefined}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  )
}
