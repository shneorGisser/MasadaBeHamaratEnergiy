import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { keys } from '../api/hooks'
import { fmt } from '../format'
import { ErrorBox } from './ErrorBox'

interface Knob {
  paths: string[]
  factor: number
  rel_std: number | null
  before: Record<string, number>
  after: Record<string, number>
  on_bound: boolean
}
interface Calibration {
  knobs: Knob[]
  before: { rms_rel: number; max_abs_rel: number }
  after: { rms_rel: number; max_abs_rel: number }
  evaluations: number
  converged: boolean
  warnings: { code: string; message: string }[]
  proposed_spec: Record<string, unknown>
  note: string
}

const pct = (v: number) => `${(100 * v).toFixed(1)} %`

/**
 * "Calibrate the model to this set": a least-squares fit of a few spec parameters to the
 * measurements (server side), shown with the error before/after, each factor with its
 * uncertainty and the warnings — and applied to the spec only when the student says so.
 */
export default function CalibratePanel({ projectId, setId }: { projectId: string; setId: string }) {
  const [res, setRes] = useState<Calibration | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [applied, setApplied] = useState(false)
  const qc = useQueryClient()

  const run = async () => {
    setBusy(true)
    setErr(null)
    setApplied(false)
    try {
      setRes(await api.post<Calibration>(`/api/measurement-sets/${setId}/calibrate`, {}))
    } catch (e) {
      setErr(e)
    } finally {
      setBusy(false)
    }
  }
  const apply = async () => {
    if (!res) return
    setErr(null)
    try {
      await api.patch(`/api/projects/${projectId}`, { spec: res.proposed_spec })
      setApplied(true)
      void qc.invalidateQueries({ queryKey: keys.projects }) // also ['projects', id]
    } catch (e) {
      setErr(e)
    }
  }
  const risky = res?.warnings.some((w) => w.code === 'on_bound' || w.code === 'not_identifiable')

  return (
    <section className="card stack" data-testid="calibrate">
      <div className="row" style={{ gap: 8 }}>
        <h3 className="grow" style={{ margin: 0 }}>
          כיול המודל לסט המדידות
        </h3>
        <button className="btn" onClick={() => void run()} disabled={busy} data-testid="calibrate-run">
          {busy ? 'מכייל…' : 'כייל'}
        </button>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        מתאים כמה פרמטרים של המפרט (שיטת הריבועים הפחותים) כך שהסימולציה בנקודות המדידה תשחזר את המדידות. שום דבר לא נשמר עד שלוחצים
        "החל".
      </p>
      {err != null && <ErrorBox error={err} />}
      {res && (
        <>
          <p data-testid="calibrate-summary" style={{ margin: 0 }}>
            שגיאה יחסית RMS: לפני <strong>{pct(res.before.rms_rel)}</strong>, אחרי <strong>{pct(res.after.rms_rel)}</strong> · שגיאה
            מרבית: לפני {pct(res.before.max_abs_rel)}, אחרי {pct(res.after.max_abs_rel)} · {res.evaluations} הרצות
            {!res.converged && ' · לא התכנס'}
          </p>
          <div className="table-wrap">
            <table className="data" aria-label="פרמטרים מכוילים">
              <thead>
                <tr>
                  <th>פרמטר</th>
                  <th>לפני</th>
                  <th>אחרי</th>
                  <th>פקטור</th>
                  <th>אי-ודאות יחסית</th>
                </tr>
              </thead>
              <tbody>
                {res.knobs.flatMap((k) =>
                  k.paths.map((p, i) => (
                    <tr key={p} className={k.on_bound ? 'warn' : undefined}>
                      <td dir="ltr">{p}</td>
                      <td>{fmt(k.before[p])}</td>
                      <td>{fmt(k.after[p])}</td>
                      <td dir="ltr">{i === 0 ? `×${k.factor.toPrecision(4)}` : '〃'}</td>
                      <td dir="ltr">{i === 0 ? (k.rel_std === null ? '—' : `±${pct(k.rel_std)}`) : ''}</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
          {res.warnings.length > 0 && (
            <div className="alert warn">
              <ul style={{ margin: 0, paddingInlineStart: 18 }}>
                {res.warnings.map((w) => (
                  <li key={w.message}>{w.message}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="row" style={{ gap: 8 }}>
            <button className={`btn ${risky ? '' : 'primary'}`} onClick={() => void apply()} disabled={applied} data-testid="calibrate-apply">
              החל על המפרט
            </button>
            {applied && <span className="badge ok">המפרט עודכן (סומן "הותאם"). ריצות קודמות נשארו כפי שהיו — הריצו סימולציה מחדש.</span>}
          </div>
        </>
      )}
    </section>
  )
}
