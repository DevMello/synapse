'use client'

import { useEffect, useRef, type ElementType, type ReactNode } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

type RevealProps = {
  children: ReactNode
  as?: ElementType
  className?: string
  /** Stagger children instead of revealing the block as one unit. */
  stagger?: boolean
  delay?: number
  y?: number
}

// Scroll-triggered entrance. Reveals the element (or its direct children when
// `stagger`) as it scrolls into view. No-op under reduced motion.
export default function Reveal({
  children,
  as,
  className,
  stagger = false,
  delay = 0,
  y = 28,
}: RevealProps) {
  const ref = useRef<HTMLElement>(null)
  const Tag = (as ?? 'div') as ElementType

  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger)
    const el = ref.current
    if (!el) return

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) return

    const targets = stagger ? (Array.from(el.children) as HTMLElement[]) : [el]

    const ctx = gsap.context(() => {
      gsap.fromTo(
        targets,
        { autoAlpha: 0, y },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.9,
          delay,
          ease: 'power3.out',
          stagger: stagger ? 0.09 : 0,
          scrollTrigger: {
            trigger: el,
            start: 'top 85%',
            once: true,
          },
        },
      )
    }, el)

    return () => ctx.revert()
  }, [stagger, delay, y])

  return (
    <Tag ref={ref} className={className}>
      {children}
    </Tag>
  )
}
