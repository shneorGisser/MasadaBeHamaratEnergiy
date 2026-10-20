import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useSelection } from '../selection'
import { ErrorBox } from './ErrorBox'

interface End {
  component: string
  label: string
  type: string
  type_he: string
  terminal: string
}
interface Step {
  index: number
  wire_id: string
  group: number
  kind: 'power' | 'measure'
  from: End
  to: End
  colour_he: string
  colour: string
  advice: string[]
}
interface Guide {
  groups: { index: number; title_he: string; kind: string; steps: [number, number] }[]
  steps: Step[]
  before: string[]
  after: string[]
}

function EndText({ e }: { e: End }) {
  return (
    <span>
      <strong>{e.label}</strong>
      {e.label !== e.component && <span className="muted"> ({e.component})</span>} · הדק <strong className="num">{e.terminal}</strong>
    </span>
  )
}

/**
 * Cable-by-cable wiring guide for the study's saved circuit, in the order the bench is wired:
 * current paths from the supply outward, voltage leads last. The current cable is highlighted
 * on the schematic and on the 3D bench.
 */
export default function WiringGuide({ projectId, kind }: { projectId: string; kind: string }) {
  const q = useQuery({
    queryKey: ['circuit', projectId, kind, 'wiring'],
    queryFn: () => api.get<Guide>(`/api/projects/${projectId}/circuits/${kind}/wiring`),
  })
  const [open, setOpen] = useState(false)
  const [cur, setCur] = useState(0)
  const [doneSet, setDone] = useState<Set<number>>(new Set())
  const highlight = useSelection((s) => s.highlightWire)
  const g = q.data
  const n = g?.steps.length ?? 0
  const step = g?.steps[Math.min(cur, Math.max(n - 1, 0))]

  useEffect(() => {
    highlight(open && step ? step.wire_id : null)
  }, [open, step, highlight])
  useEffect(() => () => highlight(null), [highlight])

  const go = (i: number) => setCur(Math.max(0, Math.min(n - 1, i)))
  const markAndNext = () => {
    if (!step) return
    setDone(new Set(doneSet).add(step.index))
    go(cur + 1)
  }

  return (
    <details className="card" style={{ padding: 10 }} data-testid="wiring-guide" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>מדריך חיבור — איזה כבל, מאיפה ולאן{g ? ` (${n} כבלים)` : ''}</summary>
      {q.isError && <ErrorBox error={q.error} />}
      {g && step && (
        <div className="stack" style={{ marginTop: 10 }}>
          <div className="grid-2">
            <section className="stack" style={{ gap: 4 }}>
              <h3>לפני שמתחילים</h3>
              <ul className="small" style={{ margin: 0 }}>
                {g.before.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </section>
            <section className="stack" style={{ gap: 4 }}>
              <h3>בסיום</h3>
              <ul className="small" style={{ margin: 0 }}>
                {g.after.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </section>
          </div>

          <section className="card stack" style={{ gap: 6, borderInlineStart: `6px solid ${step.colour}` }} data-testid="wiring-step">
            <div className="row small">
              <span className="badge">
                כבל {step.index} מתוך {n}
              </span>
              <span className="muted">{g.groups[step.group]?.title_he}</span>
              <span className="grow" />
              <span className="badge ok">
                {doneSet.size}/{n} חוברו
              </span>
            </div>
            <div className="row" style={{ fontSize: 17, gap: 10 }} data-testid="wiring-step-text">
              <EndText e={step.from} />
              <span aria-hidden>←</span>
              <EndText e={step.to} />
            </div>
            <div className="row small" style={{ gap: 6 }}>
              <span style={{ display: 'inline-block', width: 28, height: 8, borderRadius: 4, background: step.colour }} aria-hidden />
              <span>
                צבע הכבל: <strong>{step.colour_he}</strong>
                {step.kind === 'measure' && ' · כבל מדידה (במקביל)'}
              </span>
            </div>
            {step.advice.map((a) => (
              <div key={a} className="alert info small">
                {a}
              </div>
            ))}
            <div className="row">
              <button className="btn" onClick={() => go(cur - 1)} disabled={cur === 0} data-testid="wiring-prev">
                הקודם
              </button>
              <button className="btn primary" onClick={markAndNext} data-testid="wiring-next">
                {cur >= n - 1 ? 'חובר — סיום' : 'חובר, לכבל הבא'}
              </button>
              <span className="muted small">הכבל הנוכחי מסומן באדום בסכמה ובשולחן התלת-ממדי.</span>
            </div>
          </section>

          <div className="table-wrap" style={{ maxHeight: 320 }}>
            <table className="data" aria-label="רשימת הכבלים">
              <thead>
                <tr>
                  <th>#</th>
                  <th>מ-</th>
                  <th>אל</th>
                  <th>צבע</th>
                  <th>מעגל</th>
                </tr>
              </thead>
              <tbody>
                {g.steps.map((s, i) => (
                  <tr
                    key={s.wire_id}
                    onClick={() => go(i)}
                    style={{ cursor: 'pointer', background: i === cur ? 'var(--sim-soft)' : undefined, opacity: doneSet.has(s.index) && i !== cur ? 0.55 : 1 }}
                    data-step={s.index}
                  >
                    <td>{doneSet.has(s.index) ? '✓' : s.index}</td>
                    <td>
                      {s.from.component}.{s.from.terminal}
                    </td>
                    <td>
                      {s.to.component}.{s.to.terminal}
                    </td>
                    <td>
                      <span style={{ display: 'inline-block', width: 14, height: 8, borderRadius: 3, background: s.colour, marginInlineEnd: 4 }} aria-hidden />
                      {s.colour_he}
                    </td>
                    <td className="small muted">{g.groups[s.group]?.title_he}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small" style={{ margin: 0 }}>
            הסדר: כל מסלול זרם מהמקור (+ / L1) דרך המכשירים בטור אל המכונה, אחר כך החזרות והגישורים, ומדי המתח בסוף. שמות ההדקים הם כמו בסכמה; עד לצילום לוחות ההדקים במעבדה ייתכן שהסימון על הציוד שונה (למשל B2/C1 במקום A1/A2). צבעי הספקים לפי IEC 60445.
          </p>
        </div>
      )}
    </details>
  )
}
