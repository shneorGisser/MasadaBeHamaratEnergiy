/**
 * Phasor diagram of the live operating point: every voltmeter's voltage and the current through
 * every ammeter, drawn from a common origin. Angles are the solver's (reference: phase L1 of
 * the first AC source); voltages and currents have separate scales, as on a lab sketch.
 * Counter-clockwise is leading.
 */
export interface Phasor {
  label: string
  mag: number
  angle_deg: number
  kind: 'U' | 'I'
}

const COLORS = { U: ['#1f6fb2', '#2f7f7a', '#4b6b2f', '#7a3e8f'], I: ['#a2462e', '#b07a1f', '#c0392b', '#7a5200'] }

export default function PhasorDiagram({ phasors }: { phasors: Phasor[] }) {
  if (!phasors.length) return null
  const size = 240
  const c = size / 2
  const r = c - 34
  const maxOf = (k: Phasor['kind']) => Math.max(1e-30, ...phasors.filter((p) => p.kind === k).map((p) => p.mag))
  const scale = { U: r / maxOf('U'), I: r / maxOf('I') }
  const count = { U: 0, I: 0 }
  // labels of phasors that share a direction are pushed outward until they no longer collide
  const placed: [number, number][] = []
  const labelAt = (a: number, len: number): [number, number] => {
    let d = len + 14
    for (let k = 0; k < 12; k++) {
      const x = c + d * Math.cos(a)
      const y = c - d * Math.sin(a)
      if (!placed.some(([px, py]) => Math.abs(px - x) < 26 && Math.abs(py - y) < 11)) {
        placed.push([x, y])
        return [x, y]
      }
      d += 11
    }
    return [c + (len + 14) * Math.cos(a), c - (len + 14) * Math.sin(a)]
  }
  return (
    <figure className="stack" style={{ gap: 4, margin: 0 }} data-testid="phasors">
      <figcaption className="small">
        <strong>דיאגרמת פאזורים</strong>
        <br />
        <span className="muted">U ו-I בקני מידה נפרדים. נגד כיוון השעון = מקדים.</span>
      </figcaption>
      <svg width="100%" viewBox={`0 0 ${size} ${size}`} role="img" aria-label="phasor diagram" style={{ direction: 'ltr' }}>
        <defs>
          {(['U', 'I'] as const).flatMap((k) =>
            COLORS[k].map((col, i) => (
              <marker key={`${k}${i}`} id={`ph-${k}${i}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill={col} />
              </marker>
            )),
          )}
        </defs>
        <circle cx={c} cy={c} r={r} fill="none" stroke="#ddd" strokeDasharray="3 3" />
        <line x1={8} y1={c} x2={size - 8} y2={c} stroke="#ccc" />
        <line x1={c} y1={8} x2={c} y2={size - 8} stroke="#ccc" />
        {phasors.map((p) => {
          const i = count[p.kind]++ % COLORS[p.kind].length
          const col = COLORS[p.kind][i]
          const a = (p.angle_deg * Math.PI) / 180
          const len = p.mag * scale[p.kind]
          const x = c + len * Math.cos(a)
          const y = c - len * Math.sin(a)
          const [lx, ly] = labelAt(a, len)
          return (
            <g key={`${p.kind}-${p.label}`} data-phasor={p.label}>
              <line x1={c} y1={c} x2={x} y2={y} stroke={col} strokeWidth={p.kind === 'U' ? 2 : 1.6} strokeDasharray={p.kind === 'I' ? '5 3' : undefined} markerEnd={`url(#ph-${p.kind}${i})`} />
              <text x={lx} y={ly + 3} fontSize={9} textAnchor="middle" fill={col} stroke="#fff" strokeWidth={2.5} paintOrder="stroke">
                {p.label}
              </text>
            </g>
          )
        })}
      </svg>
    </figure>
  )
}
