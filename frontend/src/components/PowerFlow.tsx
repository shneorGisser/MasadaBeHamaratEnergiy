/**
 * Power balance of an induction machine at the live operating point, as a Sankey diagram, with
 * an estimate of where the winding temperature is heading.
 *
 * The powers are the solver's own (internals `<id>.total` and `<id>.mech` of the operating
 * point): P_in = P_cu1 + P_fe + P_ag; P_ag = P_cu2 + P_mech, P_cu2 = s·P_ag; P_mech = P_fw + P2.
 * Nothing here is computed except the sums and the temperature estimate.
 *
 * Temperature (an ESTIMATE, labelled as such). One thermal body, R_th from the nameplate: at
 * rated load the losses P_loss,n = √3·U_n·I_n·cos φ_n − P_n raise the winding by the
 * insulation class's permitted rise (class B: 80 K, class F: 105 K). Holding the present
 * losses then heads for Δθ = P_loss·R_th with an assumed τ = 20 min. The winding itself heats
 * faster than this single body (at locked rotor, within seconds), so the estimate is a lower
 * bound for short overloads. Stall times come from the manufacturer, not from this sketch.
 */
import { useMemo, useState } from 'react'
import { fmt } from '../format'
import { flowOf, type Flow } from './powerflow'

export interface Nameplate {
  P_n: number
  U_n: number
  I_n: number
  cos_phi_n?: number | null
}

const RISE: Record<'B' | 'F', number> = { B: 80, F: 105 }
const LIMIT: Record<'B' | 'F', number> = { B: 130, F: 155 } // hot-spot temperature [°C]
const TAU_MIN = 20
const AMBIENT = 25

const C = {
  in: '#1f6fb2',
  cu1: '#c0392b',
  fe: '#8e44ad',
  cu2: '#d35400',
  fw: '#7f8c8d',
  out: '#2e7d4f',
}

/** Shown value: solver round-off (1e-10 W at no load) is shown as 0. */
const w0 = (p: number) => (Math.abs(p) < 1e-6 ? 0 : p)

/** Main band left → right; each loss drops off downward under the point where the band
 * narrows. Widths ∝ power. Two-line labels (name, value) keep Hebrew and numbers apart. */
function Sankey({ f }: { f: Flow }) {
  const W = 760
  const H = 230
  const top = 48
  const k = 90 / Math.max(f.P_in, 1e-9) // px per W: the input band is 90 px tall
  const w = (p: number) => Math.max(1.5, Math.max(0, p) * k)
  const peels = [
    { x: 190, p: f.P_cu1, color: C.cu1, label: 'נחושת סטטור' },
    { x: 330, p: f.P_fe, color: C.fe, label: 'ברזל' },
    { x: 470, p: f.P_cu2, color: C.cu2, label: 'נחושת רוטור' },
    { x: 610, p: f.P_fw, color: C.fw, label: 'חיכוך ואוורור' },
  ]
  const rem = [f.P_in, f.P_in - f.P_cu1, f.P_ag, f.P_mech, Math.max(0, f.P2)].map(w)
  const xs = [30, ...peels.map((q) => q.x), 700]
  const yBottom = H - 52
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="sankey" role="img" aria-label="מאזן הספקים, דיאגרמת זרימה">
      {xs.slice(0, -1).map((x, i) => (
        <rect key={i} x={x} y={top} width={xs[i + 1]! - x} height={rem[i]!} fill={i === 0 ? C.in : i < 3 ? '#3f86c4' : C.out} opacity={0.85} />
      ))}
      <polygon points={`700,${top - 5} 730,${top + rem[4]! / 2} 700,${top + rem[4]! + 5}`} fill={C.out} opacity={0.85} />
      {peels.map((q, i) => {
        const bw = w(q.p)
        const y0 = top + rem[i + 1]!
        const x0 = q.x - bw
        const cx = q.x - bw / 2
        return (
          <g key={q.label}>
            <rect x={x0} y={y0} width={bw} height={Math.max(0, yBottom - y0)} fill={q.color} opacity={0.8} />
            <text x={cx} y={yBottom + 18} textAnchor="middle" direction="rtl" className="sankey-label">
              {q.label}
            </text>
            <text x={cx} y={yBottom + 36} textAnchor="middle" direction="ltr" className="sankey-value">
              {fmt(w0(q.p), 3)} W
            </text>
          </g>
        )
      })}
      {(
        [
          [30, 'start', 'כניסה', f.P_in],
          [400, 'middle', 'מרווח אוויר', f.P_ag],
          [730, 'end', 'ציר', f.P2],
        ] as const
      ).map(([x, anchor, label, p]) => (
        <g key={label}>
          <text x={x} y={top - 26} textAnchor={anchor} direction="rtl" className="sankey-label">
            {label}
          </text>
          <text x={x} y={top - 10} textAnchor={anchor} direction="ltr" className="sankey-value">
            {fmt(w0(p), 3)} W
          </text>
        </g>
      ))}
    </svg>
  )
}

export default function PowerFlow({
  internals,
  motorId,
  nameplate,
  insulation = 'B',
}: {
  internals: Record<string, Record<string, number>> | undefined
  motorId: string
  nameplate: Nameplate | null
  insulation?: 'B' | 'F'
}) {
  const [minutes, setMinutes] = useState(10)
  const f = useMemo(() => flowOf(internals, motorId), [internals, motorId])
  if (!f) return null
  const generator = f.P_ag < 0
  const lossTotal = f.P_cu1 + f.P_fe + f.P_cu2 + f.P_fw
  const pLossN =
    nameplate && nameplate.cos_phi_n ? Math.sqrt(3) * nameplate.U_n * nameplate.I_n * nameplate.cos_phi_n - nameplate.P_n : null
  const rTh = pLossN && pLossN > 0 ? RISE[insulation] / pLossN : null
  const rise = rTh ? lossTotal * rTh : null
  const thetaSs = rise === null ? null : AMBIENT + rise
  const thetaT = rise === null ? null : AMBIENT + rise * (1 - Math.exp(-minutes / TAU_MIN))
  const over = thetaSs !== null && thetaSs > LIMIT[insulation]
  return (
    <section className="card stack" data-testid="power-flow" aria-label="מאזן הספקים">
      <div className="row">
        <strong className="grow">מאזן הספקים בנקודת העבודה</strong>
        <span className="badge sim">מהפותר</span>
      </div>
      {generator ? (
        <p className="muted" data-testid="power-flow-generator">
          המכונה בהחלקה שלילית (מצב גנרטור): ההספק זורם מהציר אל הרשת, והדיאגרמה בכיוון אחד לא מתאימה לו. הערכים בטבלה.
        </p>
      ) : (
        <Sankey f={f} />
      )}
      <div className="table-wrap" style={{ maxHeight: 'none' }}>
        <table className="data" aria-label="פירוק ההספקים">
          <tbody>
            {(
              [
                ['P_in', 'הספק חשמלי נכנס', 'P_in', f.P_in],
                ['P_cu1', 'הפסדי נחושת בסטטור', '3·I₁²·R₁', f.P_cu1],
                ['P_fe', 'הפסדי ברזל', 'P_fe', f.P_fe],
                ['P_ag', 'הספק במרווח האוויר', 'P_ag', f.P_ag],
                ['P_cu2', 'הפסדי נחושת ברוטור', `s·P_ag, s = ${fmt(f.s, 3)}`, f.P_cu2],
                ['P_mech', 'הספק מכני פנימי', '(1 − s)·P_ag', f.P_mech],
                ['P_fw', 'חיכוך ואוורור', 'P_fw', f.P_fw],
                ['P2', 'הספק בציר', 'P₂', f.P2],
              ] as const
            ).map(([k, label, formula, v]) => (
              <tr key={k} data-key={k}>
                <td>
                  {label}{' '}
                  <bdi dir="ltr" className="muted small">
                    {formula}
                  </bdi>
                </td>
                <td className="num">
                  <bdi dir="ltr">{fmt(w0(v), 4)} W</bdi>
                </td>
                <td className="num muted">
                  <bdi dir="ltr">{f.P_in > 0 ? `${fmt((100 * w0(v)) / f.P_in, 3)} %` : '—'}</bdi>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rTh !== null && thetaSs !== null && thetaT !== null && (
        <div className={`stack thermal${over ? ' hot' : ''}`} data-testid="thermal-estimate" style={{ gap: 6 }}>
          <div className="row">
            <strong className="grow">לאן הטמפרטורה הולכת (הערכה)</strong>
            <span className="badge assumed">הערכה · מהשלט, τ מוערך</span>
          </div>
          <p className="small">
            ההפסדים כאן <bdi>{fmt(lossTotal, 3)} W</bdi>; בעומס נקוב, לפי השלט, <bdi>{fmt(pLossN!, 3)} W</bdi>, שמחממים את הליפוף בעד{' '}
            <bdi>{RISE[insulation]} K</bdi> (מחלקת בידוד {insulation}). אם מחזיקים את הנקודה הזו, הליפוף מתקרב ל-
            <strong>
              <bdi> {fmt(thetaSs, 3)} °C</bdi>
            </strong>
          </p>
          <label className="row small" style={{ gap: 6 }}>
            אחרי
            <input
              type="range"
              min={0}
              max={90}
              step={1}
              value={minutes}
              onChange={(e) => setMinutes(Number(e.target.value))}
              aria-label="זמן החזקה בדקות"
              data-testid="thermal-minutes"
              style={{ width: 160 }}
            />
            <bdi>{minutes} דק׳</bdi>: כ-<bdi data-testid="thermal-theta">{fmt(thetaT, 3)} °C</bdi>
          </label>
          <div className="thermal-bar" dir="ltr" aria-hidden>
            <span style={{ width: `${Math.min(100, (100 * (thetaT - AMBIENT)) / (LIMIT[insulation] - AMBIENT))}%` }} />
          </div>
          {over && (
            <p className="alert warn small" data-testid="thermal-over">
              מעל גבול מחלקה {insulation} ({LIMIT[insulation]} °C). נקודה כזו מותרת רק לזמן קצר. ברוטור נעול הליפוף מתחמם הרבה יותר מהר
              מההערכה הזו, בשניות.
            </p>
          )}
          <p className="muted small">
            גוף תרמי אחד, R_th = {fmt(rTh, 3)} K/W מהשלט, τ = {TAU_MIN} דק׳ משוער, סביבה {AMBIENT} °C. זו הערכה להמחשה, לא נתון יצרן.
          </p>
        </div>
      )}
    </section>
  )
}
