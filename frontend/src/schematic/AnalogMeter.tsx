/**
 * Moving-coil style dial for an instrument node: needle on a 100° arc over the meter range.
 * The range is the next standard lab range (1 – 1.5 – 2.5 – 3 – 5 – 6 – 7.5 × 10ⁿ) above the
 * reading, as a student would select it; an AC meter shows the RMS value, a DC meter's needle
 * deflects to the left for a negative reading (marked with a red end stop).
 */
import { meterRange } from './meter'

const SPAN = (100 * Math.PI) / 180

function fmtRange(r: number, unit: string): string {
  if (r >= 1000) return `${r / 1000}k${unit}`
  if (r < 1) return `${+(r * 1000).toPrecision(3)}m${unit}`
  return `${+r.toPrecision(3)}${unit}`
}

export default function AnalogMeter({ value, unit, signed }: { value: number; unit: string; signed: boolean }) {
  const range = meterRange(value)
  const cx = 32
  const cy = 38
  const r = 28
  const frac = signed ? (value / range + 1) / 2 : Math.min(1, Math.abs(value) / range)
  const angle = -SPAN / 2 + SPAN * Math.min(1, Math.max(0, frac))
  const pt = (rad: number, rr: number) => [cx + rr * Math.sin(rad), cy - rr * Math.cos(rad)] as const
  const ticks = Array.from({ length: 11 }, (_, k) => -SPAN / 2 + (SPAN * k) / 10)
  const [nx, ny] = pt(angle, r - 3)
  const [ax, ay] = pt(-SPAN / 2, r)
  const [bx, by] = pt(SPAN / 2, r)
  return (
    <svg width={64} height={44} viewBox="0 0 64 44" className="sch-meter" data-testid="analog-meter" data-range={range} aria-label={`${value} ${unit}`}>
      <path d={`M${ax} ${ay} A${r} ${r} 0 0 1 ${bx} ${by}`} fill="none" stroke="currentColor" strokeWidth={1.2} />
      {ticks.map((t, k) => {
        const [x1, y1] = pt(t, r)
        const [x2, y2] = pt(t, k % 5 === 0 ? r - 5 : r - 3)
        return <line key={k} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeWidth={k % 5 === 0 ? 1.2 : 0.7} />
      })}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#c0392b" strokeWidth={1.6} strokeLinecap="round" style={{ transition: 'all 0.6s ease-out' }} />
      <circle cx={cx} cy={cy} r={2.2} fill="#333" />
      <text x={62} y={42} fontSize={7} textAnchor="end" fill="currentColor">
        {fmtRange(range, unit)}
      </text>
    </svg>
  )
}
