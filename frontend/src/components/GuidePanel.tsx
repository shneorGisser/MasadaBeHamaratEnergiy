import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorBox } from './ErrorBox'

interface GuideStep {
  id: string
  kind: 'ack' | 'spec' | 'simulate' | 'measure' | 'compare' | 'report'
  title_he: string
  body_he: string
  study: string | null
  done: boolean
  detail: string
}
interface Guide {
  steps: GuideStep[]
  done: number
  total: number
}

function target(projectId: string, s: GuideStep): string | null {
  if (s.kind === 'spec') return `/projects/${projectId}/spec`
  if (s.kind === 'report') return `/projects/${projectId}/reports`
  if (!s.study) return null
  const mode = s.kind === 'measure' || s.kind === 'compare' ? 'measure' : 'sim'
  return `/projects/${projectId}?study=${s.study}&mode=${mode}`
}

/** Guided mode: the manual's procedure, with completion computed from real project data. */
export default function GuidePanel({ projectId }: { projectId: string }) {
  const qc = useQueryClient()
  const guide = useQuery({ queryKey: ['guide', projectId], queryFn: () => api.get<Guide>(`/api/projects/${projectId}/guide`) })
  const ack = useMutation({
    mutationFn: (stepId: string) => api.post<Guide>(`/api/projects/${projectId}/guide/ack`, { step_id: stepId }),
    onSuccess: (g) => qc.setQueryData(['guide', projectId], g),
  })
  if (guide.isLoading) return <p className="muted">טוען…</p>
  if (guide.isError) return <ErrorBox error={guide.error} />
  const g = guide.data!
  const nextId = g.steps.find((s) => !s.done)?.id
  return (
    <div className="stack" data-testid="guide">
      <div className="row">
        <h2 className="grow">מצב מודרך — לפי סדר החוברת</h2>
        <span className="badge ok" data-testid="guide-progress">
          {g.done} / {g.total}
        </span>
      </div>
      <div style={{ height: 8, background: 'var(--surface-2)', borderRadius: 4 }}>
        <div style={{ width: `${(100 * g.done) / g.total}%`, height: 8, background: 'var(--ok)', borderRadius: 4 }} />
      </div>
      <p className="muted small">
        שלב מסומן כהושלם רק כשיש לו נתונים אמיתיים בפרויקט (ריצה מוצלחת, שורת מדידה מלאה, דו״ח). מצב חופשי ומצב מודרך משתמשים באותו מנוע ובאותם נתונים.
      </p>
      {ack.isError && <ErrorBox error={ack.error} />}
      <ol className="guide-list">
        {g.steps.map((s) => {
          const to = target(projectId, s)
          return (
            <li key={s.id} className={`card guide-step${s.done ? ' done' : ''}${s.id === nextId ? ' next' : ''}`} data-step={s.id} data-done={s.done}>
              <div className="row">
                <span className="guide-check" aria-hidden>
                  {s.done ? '✓' : '○'}
                </span>
                <strong className="grow">{s.title_he}</strong>
                {s.detail && <span className="muted small">{s.detail}</span>}
                {(s.kind === 'ack' || (s.kind === 'spec' && !s.done)) && !s.done && (
                  <button className="btn small" onClick={() => ack.mutate(s.id)} data-testid={`ack-${s.id}`}>
                    {s.kind === 'spec' ? 'המשך עם ערכים מוערכים' : 'קראתי'}
                  </button>
                )}
                {to && (
                  <Link className="btn small" to={to} data-testid={`go-${s.id}`}>
                    עבור
                  </Link>
                )}
              </div>
              <p className="small" style={{ margin: '6px 0 0' }}>
                {s.body_he}
              </p>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
