'use client'

import { useEffect, useRef } from 'react'
import * as THREE from 'three'

// A living constellation: glowing nodes drift in 3D and link to nearby neighbours,
// evoking a synapse / agent mesh. Reacts to the pointer with a soft parallax.
// Falls back to the CSS backdrop under reduced-motion or when WebGL is unavailable.
export default function SynapseField() {
  const mountRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) return

    const mount = mountRef.current
    if (!mount) return

    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' })
    } catch {
      return
    }

    const width = mount.clientWidth || window.innerWidth
    const height = mount.clientHeight || window.innerHeight

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(width, height)
    renderer.setClearColor(0x000000, 0)
    mount.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(58, width / height, 0.1, 100)
    camera.position.z = 15

    const group = new THREE.Group()
    scene.add(group)

    // --- Nodes -------------------------------------------------------------
    const isMobile = width < 720
    const COUNT = isMobile ? 46 : 92
    const BOX = { x: 10, y: 6.2, z: 5 }
    const LINK_DIST = isMobile ? 3.4 : 3.0

    const positions = new Float32Array(COUNT * 3)
    const velocities = new Float32Array(COUNT * 3)
    const scales = new Float32Array(COUNT)

    for (let i = 0; i < COUNT; i++) {
      positions[i * 3] = (Math.random() * 2 - 1) * BOX.x
      positions[i * 3 + 1] = (Math.random() * 2 - 1) * BOX.y
      positions[i * 3 + 2] = (Math.random() * 2 - 1) * BOX.z
      velocities[i * 3] = (Math.random() * 2 - 1) * 0.006
      velocities[i * 3 + 1] = (Math.random() * 2 - 1) * 0.006
      velocities[i * 3 + 2] = (Math.random() * 2 - 1) * 0.006
      scales[i] = 0.8 + Math.random() * 1.8
    }

    const pointGeo = new THREE.BufferGeometry()
    pointGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    pointGeo.setAttribute('aScale', new THREE.BufferAttribute(scales, 1))

    const pointMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uColorA: { value: new THREE.Color(0xef6a2a) },
        uColorB: { value: new THREE.Color(0xf7d9c4) },
      },
      vertexShader: `
        attribute float aScale;
        varying float vScale;
        void main() {
          vScale = aScale;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = aScale * (220.0 / -mv.z);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: `
        varying float vScale;
        uniform vec3 uColorA;
        uniform vec3 uColorB;
        void main() {
          vec2 c = gl_PointCoord - 0.5;
          float d = length(c);
          if (d > 0.5) discard;
          float core = smoothstep(0.5, 0.0, d);
          float glow = pow(core, 2.2);
          vec3 col = mix(uColorA, uColorB, clamp(vScale * 0.45, 0.0, 1.0));
          gl_FragColor = vec4(col, glow);
        }
      `,
    })

    const points = new THREE.Points(pointGeo, pointMat)
    group.add(points)

    // --- Links -------------------------------------------------------------
    const MAX_SEG = COUNT * 8
    const linkPos = new Float32Array(MAX_SEG * 2 * 3)
    const linkAlpha = new Float32Array(MAX_SEG * 2)

    const linkGeo = new THREE.BufferGeometry()
    const linkPosAttr = new THREE.BufferAttribute(linkPos, 3)
    const linkAlphaAttr = new THREE.BufferAttribute(linkAlpha, 1)
    linkPosAttr.setUsage(THREE.DynamicDrawUsage)
    linkAlphaAttr.setUsage(THREE.DynamicDrawUsage)
    linkGeo.setAttribute('position', linkPosAttr)
    linkGeo.setAttribute('aAlpha', linkAlphaAttr)

    const linkMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: { uColor: { value: new THREE.Color(0xef6a2a) } },
      vertexShader: `
        attribute float aAlpha;
        varying float vAlpha;
        void main() {
          vAlpha = aAlpha;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying float vAlpha;
        uniform vec3 uColor;
        void main() {
          gl_FragColor = vec4(uColor, vAlpha * 0.5);
        }
      `,
    })

    const links = new THREE.LineSegments(linkGeo, linkMat)
    group.add(links)

    // --- Pointer parallax --------------------------------------------------
    const pointer = { x: 0, y: 0 }
    const targetRot = { x: 0, y: 0 }
    const onPointer = (e: PointerEvent) => {
      const rect = mount.getBoundingClientRect()
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = ((e.clientY - rect.top) / rect.height) * 2 - 1
    }
    window.addEventListener('pointermove', onPointer, { passive: true })

    // --- Animation ---------------------------------------------------------
    let raf = 0
    let running = true
    let prev = performance.now()

    const updateLinks = () => {
      let seg = 0
      for (let i = 0; i < COUNT; i++) {
        const ix = positions[i * 3]
        const iy = positions[i * 3 + 1]
        const iz = positions[i * 3 + 2]
        for (let j = i + 1; j < COUNT; j++) {
          const dx = ix - positions[j * 3]
          const dy = iy - positions[j * 3 + 1]
          const dz = iz - positions[j * 3 + 2]
          const dist = Math.sqrt(dx * dx + dy * dy + dz * dz)
          if (dist < LINK_DIST) {
            if (seg >= MAX_SEG) break
            const a = 1 - dist / LINK_DIST
            const o = seg * 6
            linkPos[o] = ix
            linkPos[o + 1] = iy
            linkPos[o + 2] = iz
            linkPos[o + 3] = positions[j * 3]
            linkPos[o + 4] = positions[j * 3 + 1]
            linkPos[o + 5] = positions[j * 3 + 2]
            linkAlpha[seg * 2] = a
            linkAlpha[seg * 2 + 1] = a
            seg++
          }
        }
        if (seg >= MAX_SEG) break
      }
      linkGeo.setDrawRange(0, seg * 2)
      linkPosAttr.needsUpdate = true
      linkAlphaAttr.needsUpdate = true
    }

    const animate = () => {
      if (!running) return
      const now = performance.now()
      const dt = Math.min((now - prev) / 1000, 0.05)
      prev = now

      for (let i = 0; i < COUNT; i++) {
        positions[i * 3] += velocities[i * 3]
        positions[i * 3 + 1] += velocities[i * 3 + 1]
        positions[i * 3 + 2] += velocities[i * 3 + 2]
        for (let a = 0; a < 3; a++) {
          const idx = i * 3 + a
          const bound = a === 0 ? BOX.x : a === 1 ? BOX.y : BOX.z
          if (positions[idx] > bound || positions[idx] < -bound) velocities[idx] *= -1
        }
      }
      pointGeo.attributes.position.needsUpdate = true
      updateLinks()

      targetRot.y += (pointer.x * 0.28 - targetRot.y) * 0.05
      targetRot.x += (-pointer.y * 0.18 - targetRot.x) * 0.05
      group.rotation.y += (targetRot.y - group.rotation.y) * 0.08 + dt * 0.02
      group.rotation.x += (targetRot.x - group.rotation.x) * 0.08

      renderer.render(scene, camera)
      raf = requestAnimationFrame(animate)
    }
    animate()

    // --- Resize / visibility ----------------------------------------------
    const resize = () => {
      const w = mount.clientWidth
      const h = mount.clientHeight
      if (!w || !h) return
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    const ro = new ResizeObserver(resize)
    ro.observe(mount)

    // Render only when the hero is on-screen AND the tab is visible.
    let docVisible = !document.hidden
    let inView = true
    const sync = () => {
      const shouldRun = docVisible && inView
      if (shouldRun && !running) {
        running = true
        prev = performance.now()
        animate()
      } else if (!shouldRun && running) {
        running = false
        cancelAnimationFrame(raf)
      }
    }
    const onVisibility = () => {
      docVisible = !document.hidden
      sync()
    }
    document.addEventListener('visibilitychange', onVisibility)

    const io = new IntersectionObserver(
      (entries) => {
        inView = entries[0].isIntersecting
        sync()
      },
      { threshold: 0 },
    )
    io.observe(mount)

    return () => {
      running = false
      cancelAnimationFrame(raf)
      window.removeEventListener('pointermove', onPointer)
      document.removeEventListener('visibilitychange', onVisibility)
      io.disconnect()
      ro.disconnect()
      pointGeo.dispose()
      pointMat.dispose()
      linkGeo.dispose()
      linkMat.dispose()
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
    }
  }, [])

  return <div ref={mountRef} className="synapse-field" aria-hidden="true" />
}
