import { BaseEdge, getSmoothStepPath, type Edge, type EdgeProps } from '@xyflow/react'
import { useEffect, useRef } from 'react'

/**
 * A cable that shows the current through it, the way Falstad's CircuitJS does (an idea, not its
 * GPL code): dots ride along the wire.
 *
 * DC: the dots drift at a speed ∝ √(|I| / I_max), in the direction of the current (wire end
 * a → b is the edge's source → target). AC: what moves is the charge displaced by
 * i(t) = √2·I·cos(ωt + φ), i.e. the dots oscillate about their rest positions with an
 * amplitude ∝ |I| and the current's phase — so the three phases visibly lag each other by
 * 120°. Time is slowed to SLOW_HZ; the picture is qualitative, the label carries the value.
 */
export interface CurrentData extends Record<string, unknown> {
  /** route around the components (router.ts), from terminal to terminal */
  points?: [number, number][]
  /** DC: signed amperes (a → b); AC: RMS magnitude; null = undefined (parallel ideal paths);
   * absent = no current shown */
  I?: number | null
  /** AC only: phase of the current [deg] */
  angle?: number
  dc?: boolean
  /** largest |I| among the cables, for scaling */
  scale?: number
  /** print the value next to the cable */
  showLabel?: boolean
}

/** Polyline path through the routed points, attached to React Flow's handle anchors. */
function routedPath(points: [number, number][], sx: number, sy: number, tx: number, ty: number): [string, number, number, number] {
  // the router's first and last points are the terminals on the outline; React Flow's anchors
  // sit on the handles just outside, on the same line — start and end there instead
  const pts: [number, number][] = [[sx, sy], ...points.slice(1, -1), [tx, ty]]
  let best = 0
  let lx = (sx + tx) / 2
  let ly = (sy + ty) / 2
  let total = 0
  for (let i = 1; i < pts.length; i++) {
    const [a, b] = [pts[i - 1]!, pts[i]!]
    const len = Math.abs(b[0] - a[0]) + Math.abs(b[1] - a[1])
    total += len
    if (len > best) {
      best = len
      lx = (a[0] + b[0]) / 2
      ly = (a[1] + b[1]) / 2
    }
  }
  return [`M${pts.map((p) => `${p[0]},${p[1]}`).join('L')}`, lx, ly, total]
}
export type CurrentEdgeType = Edge<CurrentData, 'current'>

const SPACING = 22 // px between dots
const DC_SPEED = 70 // px/s at I = I_max
const AC_AMPLITUDE = 0.45 * SPACING
const SLOW_HZ = 0.6
const MIN_FRACTION = 1e-4 // below this share of I_max a cable counts as dead
const LABEL_MIN_SPAN = 90 // px: shorter cables (star bridges, instrument links) show the value on hover only

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}

function formatCurrent(i: number): string {
  const a = Math.abs(i)
  if (a >= 1) return `${a.toFixed(2)} A`
  if (a >= 1e-3) return `${(a * 1000).toFixed(1)} mA`
  return `${(a * 1e6).toFixed(0)} µA`
}

export default function CurrentEdge(props: EdgeProps<CurrentEdgeType>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, style } = props
  const routed = data?.points && data.points.length >= 2 ? routedPath(data.points, sourceX, sourceY, targetX, targetY) : null
  const [path, labelX, labelY] = routed ?? getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition })
  const pathRef = useRef<SVGPathElement>(null)
  const dotsRef = useRef<SVGGElement>(null)

  const hasCurrent = data !== undefined && 'I' in data
  const I = data?.I ?? null
  const share = I === null || !data?.scale ? 0 : Math.abs(I) / data.scale
  const live = share > MIN_FRACTION

  useEffect(() => {
    const p = pathRef.current
    const g = dotsRef.current
    if (!p || !g || !live || !data) return
    const len = p.getTotalLength()
    const n = Math.max(1, Math.floor(len / SPACING))
    const dots = Array.from(g.children) as SVGCircleElement[]
    const place = (offset: number) => {
      for (let k = 0; k < dots.length; k++) {
        const dot = dots[k]
        if (!dot) continue
        if (k >= n) {
          dot.setAttribute('visibility', 'hidden')
          continue
        }
        const s = (((k * SPACING + offset) % len) + len) % len
        const pt = p.getPointAtLength(s)
        dot.setAttribute('visibility', 'visible')
        dot.setAttribute('cx', String(pt.x))
        dot.setAttribute('cy', String(pt.y))
      }
    }
    if (reducedMotion()) {
      place(0)
      return
    }
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const t = (now - t0) / 1000
      const offset = data.dc
        ? Math.sign(data.I ?? 0) * DC_SPEED * Math.sqrt(share) * t
        : AC_AMPLITUDE * Math.min(1, Math.sqrt(share)) * Math.sin(2 * Math.PI * SLOW_HZ * t + ((data.angle ?? 0) * Math.PI) / 180)
      place(offset)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [path, live, share, data])

  const title =
    I === null ? 'זרם לא מוגדר: כבל במקביל לכבל אחר (מסלול אידיאלי כפול)' : `${formatCurrent(I)}${data?.dc ? '' : ` ∠${(data?.angle ?? 0).toFixed(0)}°`}`
  // enough dots for the routed path (a smooth-step path is at most the Manhattan distance + bends)
  const span = routed ? routed[3] : Math.abs(targetX - sourceX) + Math.abs(targetY - sourceY)
  const maxDots = Math.ceil((span + 80) / SPACING) + 1
  return (
    <>
      <BaseEdge id={id} path={path} style={{ ...style, stroke: live ? '#1f6fb2' : style?.stroke, strokeOpacity: live ? 0.55 : 1 }} />
      <path ref={pathRef} d={path} fill="none" stroke="none" />
      <g ref={dotsRef} data-testid={`current-${id}`} data-current={I ?? ''} pointerEvents="none">
        {live && Array.from({ length: maxDots }, (_, k) => <circle key={k} r={2.6} fill="#f2a900" stroke="#7a5200" strokeWidth={0.6} visibility="hidden" />)}
      </g>
      {hasCurrent && (
      <g transform={`translate(${labelX}, ${labelY})`}>
        <title>{title}</title>
        {((live && data?.showLabel && span >= LABEL_MIN_SPAN) || I === null) && (
          <text
            className="current-label"
            textAnchor="middle"
            dy={-6}
            fontSize={10}
            fill={I === null ? '#a2462e' : '#1f4f7a'}
            stroke="#fff"
            strokeWidth={3}
            paintOrder="stroke"
          >
            {I === null ? '?' : formatCurrent(I)}
          </text>
        )}
      </g>
      )}
    </>
  )
}
