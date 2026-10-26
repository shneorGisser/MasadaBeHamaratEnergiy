/**
 * /power-electronics — the converters of the lab's Appli-com racks, simulated in the browser
 * with ngspice (eecircuit-engine) and set against their textbook theory.
 */
import { useMemo, useState } from 'react'
import { ErrorBox } from '../components/ErrorBox'
import ScopeChart from '../components/ScopeChart'
import { fmt } from '../format'
import { TOPOLOGIES, defaults, type Check, type Mode, type P } from '../powerelec/circuits'
import { simulate } from '../powerelec/client'
import type { BenchResult } from '../powerelec/run'

function verdict(c: Check): { cls: string; text: string } {
  if (c.theory === null || !Number.isFinite(c.sim)) return { cls: '', text: 'סימולציה בלבד' }
  if (c.tol === null) return { cls: 'assumed', text: 'להשוואה בלבד' }
  const rel = Math.abs(c.sim - c.theory) / Math.max(Math.abs(c.theory), 1e-9)
  return rel <= c.tol ? { cls: 'ok', text: 'תואם' } : { cls: 'err', text: 'סוטה' }
}

function deviation(c: Check): string {
  if (c.theory === null || !Number.isFinite(c.sim) || Math.abs(c.theory) < 1e-12) return '—'
  return `${fmt((100 * (c.sim - c.theory)) / Math.abs(c.theory), 3)} %`
}

export default function PowerElectronicsPage() {
  const [id, setId] = useState(TOPOLOGIES[0]!.id)
  const topo = TOPOLOGIES.find((t) => t.id === id)!
  const [params, setParams] = useState<Record<string, P>>(() =>
    Object.fromEntries(TOPOLOGIES.map((t) => [t.id, defaults(t)])),
  )
  const [mode, setMode] = useState<Mode>('ideal')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [result, setResult] = useState<{ key: string; id: string; r: BenchResult } | null>(null)
  const p = params[id]!
  const runKey = JSON.stringify([id, p, mode])
  const fresh = result?.key === runKey

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await simulate(id, p, mode)
      setResult({ key: runKey, id, r })
    } catch (e) {
      setError(e)
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  const charts = useMemo(() => {
    if (!result || result.id !== id) return []
    return topo.probes.map((pr) => ({
      title: `${pr.label}${pr.unit ? ` [${pr.unit}]` : ''}`,
      yLabel: pr.unit,
      series: [{ label: `סימולציה · ${pr.label}`, kind: 'sim' as const, points: result.r.traces[pr.key] ?? [] }],
    }))
  }, [result, topo, id])

  return (
    <div className="stack" data-testid="pe-bench">
      <div className="page-head">
        <div className="grow">
          <h1>ספסל אלקטרוניקת הספק</h1>
          <p className="muted small">
            הממירים של מתלי ה-Appli-com במעבדה. הסימולציה רצה בדפדפן עם ngspice (SPICE אמיתי שקומפל ל-WebAssembly), ולצד כל
            תוצאה מוצגת התאוריה מהספר והסטייה ממנה.
          </p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="ממיר">
        {TOPOLOGIES.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={t.id === id}
            className={`tab${t.id === id ? ' active' : ''}`}
            data-testid={`pe-tab-${t.id}`}
            onClick={() => setId(t.id)}
          >
            {t.title}
          </button>
        ))}
      </div>

      <div className="pe-grid">
        <section className="card stack" aria-label="המעגל והפיזיקה">
          <img className="pe-schematic" src={`/pe/${topo.id}.svg`} alt={`סכמת ${topo.title}`} />
          <p>{topo.summary}</p>
          <p className="muted small">
            <strong>במתלה:</strong> {topo.rack}
          </p>
          <details open>
            <summary>הפיזיקה, צעד אחר צעד</summary>
            <ol className="pe-physics">
              {topo.physics.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ol>
          </details>
        </section>

        <section className="card stack" aria-label="פרמטרים">
          {topo.params.map((q) => (
            <label key={q.key} className="field pe-param">
              <span>
                {q.label} {q.unit && <span className="muted">[{q.unit}]</span>}
              </span>
              <div className="row">
                <input
                  type="range"
                  className="grow"
                  min={q.min}
                  max={q.max}
                  step={q.step}
                  value={p[q.key]}
                  aria-label={q.label}
                  onChange={(e) => setParams((s) => ({ ...s, [id]: { ...p, [q.key]: Number(e.target.value) } }))}
                />
                <input
                  type="number"
                  className="input pe-num ltr"
                  name={`pe-${q.key}`}
                  min={q.min}
                  max={q.max}
                  step={q.step}
                  value={p[q.key]}
                  onChange={(e) => {
                    const v = Number(e.target.value)
                    if (Number.isFinite(v)) setParams((s) => ({ ...s, [id]: { ...p, [q.key]: Math.min(q.max, Math.max(q.min, v)) } }))
                  }}
                />
              </div>
            </label>
          ))}
          <fieldset className="row pe-mode">
            <legend className="small muted">רכיבים</legend>
            <label>
              <input type="radio" name="pe-mode" checked={mode === 'ideal'} onChange={() => setMode('ideal')} /> אידאליים (מה שהנוסחאות מניחות)
            </label>
            <label>
              <input type="radio" name="pe-mode" checked={mode === 'real'} onChange={() => setMode('real')} /> מציאותיים (מפל על דיודה, R_on)
            </label>
          </fieldset>
          <div className="row">
            <button className="btn primary" data-testid="pe-run" disabled={busy} onClick={() => void run()}>
              {busy ? 'מריץ…' : 'הרץ סימולציה'}
            </button>
            <button className="btn" onClick={() => setParams((s) => ({ ...s, [id]: defaults(topo) }))}>
              ערכי ברירת מחדל
            </button>
            {busy && !result && <span className="muted small">בהרצה הראשונה נטען מנוע ה-SPICE (כ-20 MB), זה לוקח כמה שניות.</span>}
          </div>
          {error != null && <ErrorBox error={error} />}
        </section>
      </div>

      {result && result.id === id && (
        <section className="card stack" aria-label="תוצאות" data-testid="pe-results">
          <div className="row">
            <h2 className="grow">תאוריה מול סימולציה</h2>
            {!fresh && <span className="badge warn">הפרמטרים השתנו מאז ההרצה</span>}
            <span className="muted small ltr">
              {result.r.points} נקודות · {fmt(result.r.ms / 1000, 3)} s · חלון {fmt(result.r.window[0] * 1e3, 4)}–{fmt(result.r.window[1] * 1e3, 4)} ms
            </span>
          </div>
          <div className="table-wrap" style={{ maxHeight: 'none' }}>
            <table className="data" aria-label="תאוריה מול סימולציה">
              <thead>
                <tr>
                  <th>גודל</th>
                  <th>סימולציה</th>
                  <th>תאוריה</th>
                  <th>סטייה</th>
                  <th>נוסחה</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {result.r.checks.map((c) => {
                  const v = verdict(c)
                  return (
                    <tr key={c.key} data-check={c.key}>
                      <td>
                        {c.label}
                        {c.note && <div className="muted small">{c.note}</div>}
                      </td>
                      <td className="ltr num">
                        <bdi>
                          {fmt(c.sim, 4)} {c.unit}
                        </bdi>
                      </td>
                      <td className="ltr num">
                        <bdi>{c.theory === null ? '—' : `${fmt(c.theory, 4)} ${c.unit}`}</bdi>
                      </td>
                      <td className="ltr num">
                        <bdi>{deviation(c)}</bdi>
                      </td>
                      <td className="ltr small">
                        <bdi>{c.formula}</bdi>
                      </td>
                      <td>{v.text && <span className={`badge ${v.cls}`}>{v.text}</span>}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="muted small">
            הממוצעים, ה-RMS וה-THD מחושבים על מחזורים שלמים בסוף הריצה (מצב יציב). "להשוואה בלבד": התאוריה מניחה מקרה מוגבל יותר
            (למשל L → ∞), ולכן אין לה סף התאמה.
          </p>
          <div className="pe-charts">
            {charts.map((c) => (
              <ScopeChart key={c.title} title={c.title} xLabel="t [s]" yLabel={c.yLabel} series={c.series} />
            ))}
          </div>
          <details>
            <summary>ה-netlist (אפשר להריץ אותו גם ב-LTspice או ב-ngspice)</summary>
            <pre className="ltr pe-netlist">{result.r.netlist}</pre>
          </details>
        </section>
      )}
    </div>
  )
}
