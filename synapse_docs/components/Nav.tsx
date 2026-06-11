'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import Magnetic from '@/components/fx/Magnetic'
import SearchCommand from '@/components/SearchCommand'

const links = [
  { href: '/', label: 'Home' },
  { href: '/docs/getting-started', label: 'Docs' },
  { href: '/docs/security', label: 'Security' },
  { href: '/docs/use-cases', label: 'Use Cases' },
]

export default function Nav() {
  const pathname = usePathname()
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Close the mobile sheet whenever the route changes.
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href)

  // Transparent nav over the dark hero needs light text until the user scrolls.
  const overHero = pathname === '/' && !scrolled && !open

  return (
    <nav
      className={`site-nav${scrolled ? ' is-scrolled' : ''}${overHero ? ' is-over-hero' : ''}${
        open ? ' is-menu-open' : ''
      }`}
    >
      <div className="nav-inner">
        <Link href="/" className="nav-logo" data-cursor>
          <span className="logo-mark" />
          <span>Synapse</span>
        </Link>

        <div className="nav-links">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`nav-link${isActive(l.href) ? ' active' : ''}`}
            >
              {l.label}
            </Link>
          ))}
          <a
            href="https://github.com/DevMello/synapse"
            target="_blank"
            rel="noopener noreferrer"
            className="nav-link"
          >
            GitHub
          </a>
          <SearchCommand />
          <Magnetic strength={0.35}>
            <Link href="/docs/getting-started" className="btn btn-primary btn-sm">
              Get Started
            </Link>
          </Magnetic>
        </div>

        <button
          className={`nav-burger${open ? ' is-open' : ''}`}
          aria-label="Toggle menu"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span />
          <span />
        </button>
      </div>

      <div className={`nav-sheet${open ? ' is-open' : ''}`}>
        <div className="nav-sheet-inner">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="nav-sheet-link">
              {l.label}
            </Link>
          ))}
          <a
            href="https://github.com/DevMello/synapse"
            target="_blank"
            rel="noopener noreferrer"
            className="nav-sheet-link"
          >
            GitHub
          </a>
          <Link href="/docs/getting-started" className="btn btn-primary nav-sheet-cta">
            Get Started →
          </Link>
        </div>
      </div>
    </nav>
  )
}
