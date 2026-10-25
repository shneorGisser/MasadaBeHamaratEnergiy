import { useMemo, useState } from 'react'
import { fmt } from '../format'
import Chart, { type Series } from './Chart'
import { harmonics, stats, valueAt } from './scope'

/**
 * A time chart with oscilloscope tools: click to place cursor A, click again for B (a third
 * click starts over). Shows the values at the cursors, Δt and 1/Δt, mean / RMS / peak-to-peak
 * over [A, B], and the harmonics of one trace over the whole periods inside [A, B].
 */
export default function ScopeChart(props: { title: string; xLabel: string; yLabel: string; series: Series[] }) {
  const [cur, setCur] = useState<number[]>([])
  const [sel, setSel] = useState(0)
  const [f0, setF0] = useState(50)
  const pick = (x: number) => setCur((c) => (c.length >= 2 ? [x] : [...c, x]))
  const [a, b] = cur
  const rows = useMemo(
    () =>
      props.series.map((s) => ({
        label: s.label.replace(/^סימולציה · /, ''),
        ya: a === undefined ? null : valueAt(s.points, a),
        yb: b === undefined ? null : valueAt(s.points, b),
        st: a !== undefined && b !== undefined ? stats(s.points, a, b) : null,
      })),
    [props.series, a, b],
  )
  const h = useMemo(() => {
    const s = props.series[sel]
    return s && a !== undefined && b !== undefined && f0 > 0 ? harmonics(s.points, a, b, f0) : null
  }, [props.series, sel, a, b, f0])

  return (
    <div className="stack" style={{ gap: 6 }}>
      <Chart {...props} markers={cur} onPick={pick} />
      <div className="row small" style={{ gap: 8, flexWrap: 'wrap' }} data-testid="scope">
        <span className="muted grow">
          {cur.length === 0 ? 'סקופ: לחצו על הגרף לסמן A' : cur.length === 1 ? 'לחצו שוב לסמן B' : 'לחיצה נוספת מתחילה מחדש'}
        </span>
        {cur.length > 0 && (
          <button className="btn small" onClick={() => setCur([])}>
            נקה סמנים
          </button>
        )}
      </div>
      {cur.length > 0 && (
        <div className="table-wrap">
          <table className="data" aria-label="מדידות סקופ" data-testid="scope-table">
            <thead>
              <tr>
                <th>עקומה</th>
                <th>y(A)</th>
                <th>y(B)</th>
                <th>Δy</th>
                <th>ממוצע</th>
                <th>RMS</th>
                <th>שיא-לשיא</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td>{fmt(r.ya)}</td>
                  <td>{fmt(r.yb)}</td>
                  <td>{r.ya !== null && r.yb !== null ? fmt(r.yb - r.ya) : '—'}</td>
                  <td>{fmt(r.st?.mean ?? null)}</td>
                  <td>{fmt(r.st?.rms ?? null)}</td>
                  <td>{fmt(r.st?.pp ?? null)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted" style={{ margin: '4px 0' }} dir="ltr">
            A = {fmt(a ?? null)} s{b !== undefined && ` · B = ${fmt(b)} s · Δt = ${fmt(Math.abs(b - (a ?? 0)))} s · 1/Δt = ${fmt(1 / Math.abs(b - (a ?? 0)))} Hz`}
          </p>
        </div>
      )}
      {cur.length === 2 && (
        <div className="stack" style={{ gap: 6 }}>
          <div className="row small" style={{ gap: 8, flexWrap: 'wrap' }}>
            <label className="row" style={{ gap: 4 }}>
              הרמוניות של
              <select className="input" style={{ width: 'auto' }} value={sel} onChange={(e) => setSel(Number(e.target.value))} name="scope-series">
                {props.series.map((s, i) => (
                  <option key={s.label} value={i}>
                    {s.label.replace(/^סימולציה · /, '')}
                  </option>
                ))}
              </select>
            </label>
            <label className="row" style={{ gap: 4 }}>
              f₀ [Hz]
              <input className="input" style={{ width: 80 }} type="number" value={f0} min={1} onChange={(e) => setF0(Number(e.target.value))} name="scope-f0" />
            </label>
          </div>
          {h ? (
            <div className="table-wrap" style={{ maxHeight: 240, overflow: 'auto' }}>
              <table className="data" aria-label="הרמוניות" data-testid="harmonics-table">
                <thead>
                  <tr>
                    <th>n</th>
                    <th>RMS</th>
                    <th>% מהיסודית</th>
                    <th>פאזה [°]</th>
                  </tr>
                </thead>
                <tbody>
                  {h.rms.map((v, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>{fmt(v)}</td>
                      <td>{h.rms[0] ? ((100 * v) / h.rms[0]).toFixed(2) : '—'}</td>
                      <td>{h.phase[i]!.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small" style={{ margin: '4px 0' }} data-testid="thd">
                THD = {h.thd === null ? '—' : `${(100 * h.thd).toFixed(2)} %`} · רכיב DC = {fmt(h.dc)} · חלון {h.periods} מחזורים ({fmt(h.t0)}–{fmt(h.t1)} s)
              </p>
            </div>
          ) : (
            <p className="small muted">לחישוב הרמוניות צריך לפחות מחזור שלם של f₀ בין A ל-B.</p>
          )}
        </div>
      )}
    </div>
  )
}
