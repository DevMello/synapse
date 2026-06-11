'use client'

import { useEffect, useRef } from 'react'
import { gsap } from 'gsap'

// Runs on every navigation (App Router re-instantiates templates per route),
// giving each page a branded curtain wipe + content reveal.
export default function Template({ children }: { children: React.ReactNode }) {
  const overlay = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const el = content.current!
    const ov = overlay.current!

    if (reduce) {
      gsap.set(el, { opacity: 1, y: 0 })
      gsap.set(ov, { display: 'none' })
      return
    }

    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
    tl.set(ov, { display: 'block', scaleY: 1, transformOrigin: 'top' })
      .set(el, { opacity: 0, y: 24 })
      .to(ov, { scaleY: 0, transformOrigin: 'bottom', duration: 0.7, ease: 'power4.inOut' })
      .to(el, { opacity: 1, y: 0, duration: 0.8 }, '-=0.45')
      .set(ov, { display: 'none' })

    return () => {
      tl.kill()
    }
  }, [])

  return (
    <>
      <div ref={overlay} className="route-curtain" aria-hidden="true">
        <span className="route-curtain-mark" />
      </div>
      <div ref={content} className="route-content">
        {children}
      </div>
    </>
  )
}
