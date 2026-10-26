/** Landing pages of the sharing links, and the operator's feedback list. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Project } from '../api/types'
import { ErrorBox } from '../components/ErrorBox'
import { t } from '../i18n'

/** /s/:token — a friend's shared project: show what it is, copy it into my space. */
export function SharedProjectPage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const info = useQuery({
    queryKey: ['shared', token],
    queryFn: () => api.get<{ name: string; experiment_title_he: string }>(`/api/shared/${token}`),
    retry: false,
  })
  const copy = useMutation({
    mutationFn: () => api.post<Project>(`/api/shared/${token}/copy`),
    onSuccess: (p) => {
      void qc.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${p.id}`)
    },
  })
  if (info.isLoading) return <p className="muted">{t('common.loading')}</p>
  if (info.isError)
    return (
      <div className="card stack" data-testid="shared-missing">
        <h1>הקישור אינו פעיל</h1>
        <p className="muted">ייתכן שבעל הפרויקט ביטל את השיתוף, או שהקישור הועתק חלקית.</p>
        <Link to="/">לפרויקטים שלי</Link>
      </div>
    )
  return (
    <div className="card stack" data-testid="shared-page">
      <p className="muted small">שיתפו איתך פרויקט</p>
      <h1>{info.data!.name}</h1>
      <p className="muted">{info.data!.experiment_title_he}</p>
      <p>העותק יישמר אצלך, עם הסימולציות והמדידות שבו. שינויים שתעשה בו לא ישפיעו על הפרויקט המקורי.</p>
      {copy.isError && <ErrorBox error={copy.error} />}
      <div className="row">
        <button className="btn primary" data-testid="shared-copy" disabled={copy.isPending} onClick={() => copy.mutate()}>
          העתקה לפרויקטים שלי
        </button>
        <Link to="/">ביטול</Link>
      </div>
    </div>
  )
}

/** /w#token — open my workspace on this device. The token travels in the hash, so it never
 * reaches server logs or the Referer header. */
export function WorkspaceAdoptPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [error, setError] = useState<unknown>(null)
  useEffect(() => {
    const token = window.location.hash.slice(1)
    history.replaceState(null, '', '/w')
    // adopt, then confirm: a concurrent first request could still race the cookie
    const adopt = async () => {
      for (let i = 0; i < 3; i++) {
        await api.post('/api/workspace', { token })
        const ws = await api.get<{ token: string | null }>('/api/workspace')
        if (ws.token === token) return
      }
      throw new Error('הדפדפן לא שמר את המרחב (ייתכן שעוגיות חסומות)')
    }
    adopt()
      .then(() => {
        void qc.invalidateQueries()
        navigate('/', { replace: true })
      })
      .catch(setError)
  }, [navigate, qc])
  if (error)
    return (
      <div className="card stack">
        <h1>לא הצלחנו לפתוח את המרחב</h1>
        <ErrorBox error={error} />
        <Link to="/">לפרויקטים</Link>
      </div>
    )
  return <p className="muted">פותח את המרחב שלך…</p>
}

type FeedbackRow = {
  id: string
  created_at: string
  kind: string
  message: string
  contact: string
  page: string
  from: string
  user_agent: string
}

const KIND_HE: Record<string, string> = { bug: 'תקלה', idea: 'רעיון', question: 'שאלה', other: 'אחר' }

function readKey(): string {
  try {
    return sessionStorage.getItem('vel-admin-key') ?? ''
  } catch {
    return ''
  }
}

/** /feedback — the operator's list. The key (VEL_ADMIN_TOKEN) stays in this tab only. */
export function FeedbackAdminPage() {
  const [key, setKey] = useState(readKey)
  const [draft, setDraft] = useState('')
  const rows = useQuery({
    queryKey: ['feedback', key],
    enabled: Boolean(key),
    retry: false,
    queryFn: async () => {
      const res = await fetch('/api/feedback', { headers: { 'X-Admin-Token': key } })
      if (!res.ok) throw new ApiError(res.status, 'denied', 'המפתח שגוי, או שלא הוגדר VEL_ADMIN_TOKEN בשרת')
      return (await res.json()) as FeedbackRow[]
    },
  })
  const save = (k: string) => {
    try {
      sessionStorage.setItem('vel-admin-key', k)
    } catch {
      /* private mode: keep it in memory only */
    }
    setKey(k)
  }
  return (
    <div className="stack" data-testid="feedback-admin">
      <h1>משוב מהמשתמשים</h1>
      {(!key || rows.isError) && (
        <div className="card stack">
          {rows.isError && <ErrorBox error={rows.error} />}
          <label className="field">
            מפתח מנהל (הערך של VEL_ADMIN_TOKEN)
            <input className="input ltr" type="password" name="admin-key" value={draft} onChange={(e) => setDraft(e.target.value)} />
          </label>
          <button className="btn primary" disabled={!draft} onClick={() => save(draft)}>
            הצגת המשוב
          </button>
        </div>
      )}
      {rows.data && rows.data.length === 0 && <p className="muted">עוד לא התקבל משוב.</p>}
      {rows.data && rows.data.length > 0 && (
        <div className="table-wrap" style={{ maxHeight: 'none' }}>
          <table className="data" aria-label="משוב">
            <thead>
              <tr>
                <th>מתי</th>
                <th>סוג</th>
                <th>הודעה</th>
                <th>איש קשר</th>
                <th>עמוד</th>
                <th>דפדפן</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.map((f) => (
                <tr key={f.id}>
                  <td className="nowrap">{new Date(f.created_at).toLocaleString('he-IL')}</td>
                  <td>{KIND_HE[f.kind] ?? f.kind}</td>
                  <td style={{ whiteSpace: 'pre-wrap', minWidth: 260 }}>{f.message}</td>
                  <td>{f.contact}</td>
                  <td className="ltr small">{f.page}</td>
                  <td className="ltr small" title={f.user_agent}>
                    {f.from}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
