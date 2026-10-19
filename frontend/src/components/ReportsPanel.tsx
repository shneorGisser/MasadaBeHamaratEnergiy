import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { useStudies } from '../api/hooks'
import type { MSet, RunSummary } from '../api/types'
import { fmtDate } from '../i18n'
import { ErrorBox } from './ErrorBox'

interface ReportSummary {
  id: string
  title: string
  status: string
  created_at: string
}

export default function ReportsPanel({ projectId }: { projectId: string }) {
  const qc = useQueryClient()
  const studies = useStudies(projectId)
  const runs = useQuery({ queryKey: ['runs', projectId, 'all'], queryFn: () => api.get<RunSummary[]>(`/api/projects/${projectId}/runs`) })
  const sets = useQuery({ queryKey: ['msets', projectId, 'all'], queryFn: () => api.get<MSet[]>(`/api/projects/${projectId}/measurement-sets`) })
  const reports = useQuery({ queryKey: ['reports', projectId], queryFn: () => api.get<ReportSummary[]>(`/api/projects/${projectId}/reports`) })
  const [title, setTitle] = useState('דו״ח ניסוי 1 — בדיקת שנאי תלת-פזי')
  const [discussion, setDiscussion] = useState('')
  const [pick, setPick] = useState<Record<string, { include: boolean; run: string; set: string }>>({})
  const [err, setErr] = useState<unknown>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const shownId = openId ?? reports.data?.[0]?.id ?? null

  const okRuns = (kind: string) => (runs.data ?? []).filter((r) => r.study_kind === kind && (r.status === 'success' || r.status === 'success_with_warnings'))
  const kindSets = (kind: string) => (sets.data ?? []).filter((s) => s.study_kind === kind)
  const sel = (kind: string) => {
    const p = pick[kind]
    const r = okRuns(kind)[0]?.id ?? ''
    const s = kindSets(kind)[0]?.id ?? ''
    return { include: p?.include ?? Boolean(r || s), run: p?.run ?? r, set: p?.set ?? s }
  }

  const create = async () => {
    setErr(null)
    const sections = (studies.data ?? [])
      .map((st) => ({ kind: st.kind, ...sel(st.kind) }))
      .filter((x) => x.include && (x.run || x.set))
      .map((x) => ({ study_kind: x.kind, run_id: x.run || null, set_id: x.set || null }))
    try {
      const r = await api.post<ReportSummary>(`/api/projects/${projectId}/reports`, { title, sections, student_discussion: discussion })
      await qc.invalidateQueries({ queryKey: ['reports', projectId] })
      void qc.invalidateQueries({ queryKey: ['guide', projectId] })
      setOpenId(r.id)
    } catch (e) {
      setErr(e)
    }
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h2>הפקת דו״ח</h2>
        <p className="muted small">הדו״ח נשמר כתמונת מצב נעולה: תיקון מדידה או ריצה חדשה אחרי ההפקה לא ישנו אותו.</p>
        <label className="field">
          כותרת
          <input className="input" name="report-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <table className="data">
          <thead>
            <tr>
              <th>כלול</th>
              <th>ניסוי</th>
              <th>ריצת סימולציה</th>
              <th>סט מדידות</th>
            </tr>
          </thead>
          <tbody>
            {(studies.data ?? []).map((st) => {
              const v = sel(st.kind)
              const set = (patch: Partial<typeof v>) => setPick({ ...pick, [st.kind]: { ...v, ...patch } })
              return (
                <tr key={st.kind} data-testid={`rs-${st.kind}`}>
                  <td>
                    <input type="checkbox" checked={v.include} onChange={(e) => set({ include: e.target.checked })} />
                  </td>
                  <td>{st.title_he}</td>
                  <td>
                    <select className="input" value={v.run} onChange={(e) => set({ run: e.target.value })}>
                      <option value="">—</option>
                      {okRuns(st.kind).map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.label || fmtDate(r.created_at)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select className="input" value={v.set} onChange={(e) => set({ set: e.target.value })}>
                      <option value="">—</option>
                      {kindSets(st.kind).map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label || s.id.slice(0, 8)}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <label className="field">
          דיון (נכתב על ידי הסטודנט — המערכת אינה מנסחת הסברים לפערים)
          <textarea className="input" name="discussion" rows={5} value={discussion} onChange={(e) => setDiscussion(e.target.value)} />
        </label>
        <div className="row">
          <button className="btn primary" onClick={() => void create()} data-testid="create-report">
            הפק דו״ח
          </button>
        </div>
        {err != null && <ErrorBox error={err} />}
      </section>

      <section className="card stack">
        <h2>דו״חות שהופקו</h2>
        {reports.data?.length === 0 && <p className="muted small">עדיין לא הופקו דו״חות.</p>}
        <ul className="small" data-testid="report-list">
          {reports.data?.map((r) => (
            <li key={r.id}>
              <button className="btn small" onClick={() => setOpenId(r.id)}>
                {r.title}
              </button>{' '}
              <span className="muted">{fmtDate(r.created_at)}</span>{' '}
              <a href={`/api/reports/${r.id}/html`} target="_blank" rel="noreferrer">
                פתח בלשונית
              </a>{' '}
              ·{' '}
              <a href={`/api/reports/${r.id}/pdf`} data-testid="report-pdf">
                PDF
              </a>
            </li>
          ))}
        </ul>
        {shownId && <iframe title="דו״ח" src={`/api/reports/${shownId}/html`} className="report-frame" data-testid="report-frame" />}
      </section>
    </div>
  )
}
