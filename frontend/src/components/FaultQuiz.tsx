/**
 * Fault-diagnosis challenge (backend vel/services/faults.py): the bench hides one wiring
 * fault, or none. The student compares what the instruments read with what the correct circuit
 * reads, picks a diagnosis, and only then sees the answer and the symptom to look for.
 */
import { useState } from 'react'
import { api } from '../api/client'
import { fmt, iso } from '../format'
import { ErrorBox } from './ErrorBox'

type Readings = Record<string, Record<string, number | null | undefined>>
interface Quiz {
  seed: number
  options: { id: string; title_he: string }[]
  answer: string
  explanation_he: string
  expected: Readings
  observed: Readings
}

/** What each instrument shows on the bench, recognised by what the solver reports for it (a
 * wattmeter also reports U and I, which its display does not show). */
function shown(r: Record<string, number | null | undefined>): [string, string][] {
  if ('P' in r) return [['P', 'W']]
  if ('n' in r) return [
    ['n', 'rpm'],
    ['M', 'N·m'],
  ]
  if ('U' in r && !('I' in r)) return [['U', 'V']]
  if ('I' in r) return [['I', 'A']]
  return []
}

function rowsOf(q: Quiz) {
  const out: { id: string; q: string; unit: string; exp: number | null; obs: number | null }[] = []
  for (const id of Object.keys(q.expected).sort()) {
    for (const [key, unit] of shown(q.expected[id] ?? {})) {
      const e = q.expected[id]?.[key]
      const o = q.observed[id]?.[key]
      if (typeof e !== 'number' && typeof o !== 'number') continue
      out.push({ id, q: key, unit, exp: typeof e === 'number' ? e : null, obs: typeof o === 'number' ? o : null })
    }
  }
  return out
}

export default function FaultQuiz({ projectId, kind }: { projectId: string; kind: string }) {
  const [quiz, setQuiz] = useState<Quiz | null>(null)
  const [choice, setChoice] = useState<string | null>(null)
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [score, setScore] = useState({ right: 0, total: 0 })

  const next = async () => {
    setBusy(true)
    setError(null)
    try {
      setQuiz(await api.post<Quiz>(`/api/projects/${projectId}/circuits/${kind}/fault-quiz`, {}))
      setChoice(null)
      setChecked(false)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  const check = () => {
    if (!quiz || !choice) return
    setChecked(true)
    setScore((s) => ({ right: s.right + (choice === quiz.answer ? 1 : 0), total: s.total + 1 }))
  }
  const right = quiz && checked && choice === quiz.answer

  return (
    <details className="card" style={{ padding: 10 }} data-testid="fault-quiz">
      <summary>אתגר אבחון: מה לא בסדר בחיבור?</summary>
      <div className="stack" style={{ gap: 8, marginTop: 8 }}>
        <p className="muted small">
          השולחן חווט עם תקלה אחת מוסתרת, או בלי תקלה. השוו את קריאות המכשירים לקריאות של המעגל התקין ובחרו אבחנה. כל תקלה היא שינוי אמיתי במעגל, והקריאות מחושבות
          באותו פותר.
        </p>
        <div className="row">
          <button className="btn primary" onClick={() => void next()} disabled={busy} data-testid="fq-new">
            {quiz ? 'אתגר חדש' : 'התחל אתגר'}
          </button>
          {score.total > 0 && (
            <span className="badge" data-testid="fq-score">
              <bdi dir="ltr">
                {score.right}/{score.total}
              </bdi>{' '}
              נכונות
            </span>
          )}
        </div>
        {error != null && <ErrorBox error={error} />}
        {quiz && (
          <>
            <table className="data" aria-label="קריאות המכשירים">
              <thead>
                <tr>
                  <th>מכשיר</th>
                  <th className="num">במעגל התקין</th>
                  <th className="num">על השולחן שלכם</th>
                </tr>
              </thead>
              <tbody>
                {rowsOf(quiz).map((r) => {
                  const diff = r.exp !== null && r.obs !== null && Math.abs(r.obs - r.exp) > 1e-3 * Math.max(Math.abs(r.exp), 1e-9)
                  return (
                    <tr key={`${r.id}-${r.q}`}>
                      <td>
                        {r.id} · {r.q}
                      </td>
                      <td className="num">{r.exp === null ? '—' : `${fmt(r.exp)} ${r.unit}`}</td>
                      <td className="num" style={diff ? { fontWeight: 700 } : undefined}>
                        {r.obs === null ? '—' : `${fmt(r.obs)} ${r.unit}`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <fieldset className="stack" style={{ gap: 4, border: 0, padding: 0 }} disabled={checked}>
              <legend className="small">האבחנה שלכם:</legend>
              {quiz.options.map((o) => (
                <label key={o.id} className="row small" style={{ gap: 6 }}>
                  <input type="radio" name="fq" value={o.id} checked={choice === o.id} onChange={() => setChoice(o.id)} />
                  {iso(o.title_he)}
                </label>
              ))}
            </fieldset>
            {!checked ? (
              <button className="btn" onClick={check} disabled={!choice} data-testid="fq-check">
                בדוק
              </button>
            ) : (
              <div className={`card stack ${right ? 'ok-box' : 'warn-box'}`} style={{ gap: 4, padding: 10 }} data-testid="fq-result" role="status">
                <strong>{right ? 'נכון.' : `לא בדיוק. התשובה: ${iso(quiz.options.find((o) => o.id === quiz.answer)?.title_he ?? '')}`}</strong>
                <span className="small">{iso(quiz.explanation_he)}</span>
              </div>
            )}
          </>
        )}
      </div>
    </details>
  )
}
