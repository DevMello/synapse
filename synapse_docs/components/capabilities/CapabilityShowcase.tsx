'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { gsap } from 'gsap'
import { capabilities } from './data'

const AUTO_MS = 6000

export default function CapabilityShowcase() {
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const reduceRef = useRef(false)

  useEffect(() => {
    reduceRef.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }, [])

  // Auto-advance through capabilities until the user interacts/hovers.
  useEffect(() => {
    if (paused || reduceRef.current) return
    const id = window.setTimeout(() => setActive((i) => (i + 1) % capabilities.length), AUTO_MS)
    return () => window.clearTimeout(id)
  }, [active, paused])

  // Animate the mock panel on every change.
  useEffect(() => {
    const el = panelRef.current
    if (!el || reduceRef.current) return
    const ctx = gsap.context(() => {
      gsap.fromTo(
        el,
        { autoAlpha: 0, y: 18, scale: 0.985 },
        { autoAlpha: 1, y: 0, scale: 1, duration: 0.55, ease: 'power3.out' },
      )
    }, el)
    return () => ctx.revert()
  }, [active])

  const cap = capabilities[active]

  return (
    <div
      className="cap-showcase"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="cap-rail" role="tablist" aria-label="Synapse capabilities">
        {capabilities.map((c, i) => (
          <button
            key={c.id}
            role="tab"
            aria-selected={i === active}
            className={`cap-tab${i === active ? ' is-active' : ''}`}
            onClick={() => {
              setActive(i)
              setPaused(true)
            }}
          >
            <span className="cap-tab-label">{c.label}</span>
            <span className="cap-tab-tag">{c.tag}</span>
            {i === active && !paused && (
              <span key={active} className="cap-tab-progress" aria-hidden="true" />
            )}
          </button>
        ))}
      </div>

      <div className="cap-stage">
        <div className="cap-panel" ref={panelRef} key={cap.id}>
          <div className="cap-mock">{cap.mock}</div>
        </div>
        <div className="cap-caption">
          <h3 className="cap-caption-title">{cap.label}</h3>
          <p className="cap-caption-blurb">{cap.blurb}</p>
          <Link href={cap.href} className="cap-caption-link">
            Explore {cap.label.toLowerCase()} →
          </Link>
        </div>
      </div>
    </div>
  )
}
