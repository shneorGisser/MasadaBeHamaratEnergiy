/**
 * "The phasor is a snapshot of the wave": the live operating point's phasors turning at ωt, next
 * to the waves they generate. Each instantaneous value is the projection of its rotating phasor
 * on the vertical axis, u(t) = √2·U·sin(ωt + φ), so a horizontal line from the arrow tip lands
 * on the wave at the current instant. With the three line currents of a balanced three-wire
 * system the instantaneous sum is shown — it is zero at every t, which the phasor picture shows
 * as the three arrows closing a triangle.
 *
 * Scales follow PhasorDiagram: voltages and currents each have their own (RMS → radius), so the
 * waves are drawn at those scales too; the numbers shown are the true instantaneous values.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { fmt } from '../format'
import type { Phasor } from './PhasorDiagram'

const COLORS = { U: ['#1f6fb2', '#2f7f7a', '#4b6b2f', '#7a3e8f'], I: ['#a2462e', '#b07a1f', '#c0392b', '#7a5200'] }
const W = 760
const H = 320
const R = 120 // phasor circle radius
const CX = 140
const CY = H / 2 + 8
const X0 = 300 // wave panel: x of ωt = 0
const XW = 440 // width of one period

function reducedMotion(): boolean {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

export default function PhasorWaves({ phasors, onClose }: { phasors: Phasor[]; onClose: () => void }) {
  const [deg, setDeg] = useState(0)
  const [playing, setPlaying] = useState(false)
  const raf = useRef<number | null>(null)
  useEffect(() => {
    if (!playing) return
    let last = performance.now()
    const step = (now: number) => {
      setDeg((d) => (d + ((now - last) / 1000) * 45) % 360) // one turn in 8 s
      last = now
      raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => {
      if (raf.current !== null) cancelAnimationFrame(raf.current)
    }
  }, [playing])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  const items = useMemo(() => {
    const maxOf = (k: Phasor['kind']) => Math.max(1e-30, ...phasors.filter((p) => p.kind === k).map((p) => p.mag))
    const count = { U: 0, I: 0 }
    return phasors.map((p) => {
      const i = count[p.kind]++ % COLORS[p.kind].length
      return { ...p, color: COLORS[p.kind][i]!, len: (p.mag / maxOf(p.kind)) * R, phi: (p.angle_deg * Math.PI) / 180 }
    })
  }, [phasors])
  const wt = (deg * Math.PI) / 180
  const xNow = X0 + (deg / 360) * XW
  const currents = items.filter((p) => p.kind === 'I')
  const iSum = currents.length === 3 ? currents.reduce((s, p) => s + Math.SQRT2 * p.mag * Math.sin(wt + p.phi), 0) : null
  const iPeak = currents.length === 3 ? Math.max(...currents.map((p) => Math.SQRT2 * p.mag)) : 1

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="card modal phasor-waves" role="dialog" aria-modal="true" aria-label="פאזורים וגלים" onClick={(e) => e.stopPropagation()} data-testid="phasor-waves">
        <div className="row">
          <h3 className="grow">הפאזור הוא "צילום" של הגל ברגע אחד</h3>
          <button className="btn small" onClick={onClose}>
            סגירה
          </button>
        </div>
        <p className="muted small">
          כל פאזור מסתובב במהירות ω. הערך הרגעי הוא ההיטל שלו על הציר האנכי:{' '}
          <bdi dir="ltr" className="formula">
            u(t) = √2·U·sin(ωt + φ)
          </bdi>
          . הזיזו את ωt וראו איך הקו האופקי מקצה החץ פוגש את הגל.
        </p>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="rotating phasors and their waves" style={{ direction: 'ltr', maxHeight: '60vh' }}>
          <circle cx={CX} cy={CY} r={R} fill="none" stroke="#ddd" strokeDasharray="3 3" />
          <line x1={CX - R - 10} y1={CY} x2={X0 + XW + 10} y2={CY} stroke="#bbb" />
          <line x1={CX} y1={CY - R - 10} x2={CX} y2={CY + R + 10} stroke="#ccc" />
          <line x1={X0} y1={CY - R - 10} x2={X0} y2={CY + R + 10} stroke="#bbb" />
          <text x={X0} y={CY - R - 14} fontSize={11} textAnchor="middle" fill="#666">
            ωt = 0
          </text>
          <text x={X0 + XW} y={CY - R - 14} fontSize={11} textAnchor="middle" fill="#666">
            360°
          </text>
          <line x1={xNow} y1={CY - R - 6} x2={xNow} y2={CY + R + 6} stroke="#b07a1f" strokeWidth={1.5} strokeDasharray="5 4" />
          {items.map((p) => {
            const a = wt + p.phi
            const tx = CX + p.len * Math.cos(a)
            const ty = CY - p.len * Math.sin(a)
            const wave: string[] = []
            for (let k = 0; k <= 180; k++) {
              const th = (k / 180) * 2 * Math.PI
              wave.push(`${(X0 + (k / 180) * XW).toFixed(1)},${(CY - p.len * Math.sin(th + p.phi)).toFixed(1)}`)
            }
            return (
              <g key={`${p.kind}-${p.label}`} data-wave={p.label}>
                <polyline points={wave.join(' ')} fill="none" stroke={p.color} strokeWidth={1.6} strokeDasharray={p.kind === 'I' ? '6 4' : undefined} opacity={0.85} />
                <line x1={tx} y1={ty} x2={xNow} y2={ty} stroke={p.color} strokeWidth={0.8} strokeDasharray="2 3" />
                <line x1={CX} y1={CY} x2={tx} y2={ty} stroke={p.color} strokeWidth={2.2} strokeDasharray={p.kind === 'I' ? '6 3' : undefined} />
                <circle cx={tx} cy={ty} r={3} fill={p.color} />
                <circle cx={xNow} cy={ty} r={3.5} fill="#fff" stroke={p.color} strokeWidth={1.6} />
              </g>
            )
          })}
        </svg>
        <div className="row">
          <label className="field grow">
            ωt = {Math.round(deg)}°
            <input type="range" dir="ltr" min={0} max={359} step={1} value={Math.round(deg)} onChange={(e) => setDeg(Number(e.target.value))} data-testid="phasor-wt" aria-label="ωt" />
          </label>
          <button className="btn" onClick={() => setPlaying((v) => !v)} aria-pressed={playing}>
            {playing ? 'עצירה' : reducedMotion() ? 'הפעלה (תנועה מופחתת מופעלת במערכת)' : 'סיבוב'}
          </button>
        </div>
        <table className="data small" aria-label="ערכים רגעיים">
          <thead>
            <tr>
              <th>גודל</th>
              <th className="num">RMS</th>
              <th className="num">φ</th>
              <th className="num">ערך רגעי ב-ωt</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={`${p.kind}-${p.label}`}>
                <td style={{ color: p.color }}>{p.label}</td>
                <td className="num">
                  {fmt(p.mag)} {p.kind === 'U' ? 'V' : 'A'}
                </td>
                <td className="num">{(Math.abs(p.angle_deg) < 0.05 ? 0 : p.angle_deg).toFixed(1)}°</td>
                <td className="num">
                  {fmt(Math.SQRT2 * p.mag * Math.sin(wt + p.phi))} {p.kind === 'U' ? 'V' : 'A'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {iSum !== null && (
          <p className={`badge ${Math.abs(iSum) < 1e-3 * iPeak ? 'ok' : 'warn'}`} data-testid="current-sum">
            סכום שלושת הזרמים הרגעיים: {fmt(iSum, 3)} A{' '}
            {Math.abs(iSum) < 1e-3 * iPeak ? '(אפס בכל רגע: אין מוליך אפס, אז הזרם שנכנס בקו אחד יוצא בשניים האחרים)' : '(לא אפס: יש מסלול רביעי, אפס או הארקה)'}
          </p>
        )}
      </section>
    </div>
  )
}
