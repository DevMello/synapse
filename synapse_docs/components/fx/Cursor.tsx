'use client'

import { useEffect, useRef } from 'react'

// A two-part custom cursor: a precise dot + a trailing ring that eases behind it
// and swells over interactive targets. Desktop / fine-pointer only.
export default function Cursor() {
  const dotRef = useRef<HTMLDivElement>(null)
  const ringRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fine = window.matchMedia('(pointer: fine)').matches
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!fine || reduce) return

    const dot = dotRef.current!
    const ring = ringRef.current!

    let mouseX = window.innerWidth / 2
    let mouseY = window.innerHeight / 2
    let ringX = mouseX
    let ringY = mouseY
    let hovering = false
    let visible = false
    let raf = 0

    const onMove = (e: MouseEvent) => {
      mouseX = e.clientX
      mouseY = e.clientY
      if (!visible) {
        visible = true
        document.body.classList.add('cursor-active')
      }
      const target = e.target as HTMLElement
      const interactive = target.closest(
        'a, button, [data-cursor], input, textarea, summary, .faq-question',
      )
      const next = Boolean(interactive)
      if (next !== hovering) {
        hovering = next
        ring.classList.toggle('is-hover', hovering)
      }
    }

    const onLeave = () => {
      visible = false
      document.body.classList.remove('cursor-active')
    }

    const tick = () => {
      ringX += (mouseX - ringX) * 0.16
      ringY += (mouseY - ringY) * 0.16
      // Use the independent `translate` property so CSS keeps ownership of `scale`.
      dot.style.translate = `${mouseX}px ${mouseY}px`
      ring.style.translate = `${ringX}px ${ringY}px`
      raf = requestAnimationFrame(tick)
    }

    window.addEventListener('mousemove', onMove)
    document.documentElement.addEventListener('mouseleave', onLeave)
    raf = requestAnimationFrame(tick)

    return () => {
      window.removeEventListener('mousemove', onMove)
      document.documentElement.removeEventListener('mouseleave', onLeave)
      cancelAnimationFrame(raf)
      document.body.classList.remove('cursor-active')
    }
  }, [])

  return (
    <>
      <div ref={ringRef} className="cursor-ring" aria-hidden="true" />
      <div ref={dotRef} className="cursor-dot" aria-hidden="true" />
    </>
  )
}
