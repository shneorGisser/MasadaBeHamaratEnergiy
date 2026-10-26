/**
 * Sharing a deployment: the feedback button (every page), the project share link and the
 * "open my workspace on another device" link. The server decides who sees what
 * (backend vel/api/workspace.py); these components only call it.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorBox } from './ErrorBox'

type Kind = 'bug' | 'idea' | 'question' | 'other'
const KINDS: [Kind, string][] = [
  ['bug', 'משהו לא עובד'],
  ['idea', 'רעיון לשיפור'],
  ['question', 'שאלה'],
  ['other', 'אחר'],
]

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function FeedbackButton() {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<Kind>('bug')
  const [message, setMessage] = useState('')
  const [contact, setContact] = useState('')
  const location = useLocation()
  const projectId = /^\/projects\/([^/]+)/.exec(location.pathname)?.[1] ?? null
  const send = useMutation({
    mutationFn: () =>
      api.post<{ id: string }>('/api/feedback', {
        message: message.trim(),
        kind,
        contact: contact.trim(),
        page: location.pathname + location.search,
        project_id: projectId,
      }),
    onSuccess: () => {
      setMessage('')
    },
  })
  if (!open)
    return (
      <button className="feedback-fab" data-testid="feedback-open" onClick={() => { send.reset(); setOpen(true) }}>
        משוב
      </button>
    )
  return (
    <section className="feedback-panel card" role="dialog" aria-label="שליחת משוב" data-testid="feedback-panel">
      <div className="row">
        <strong className="grow">מה כדאי שנדע?</strong>
        <button className="btn small" onClick={() => setOpen(false)} aria-label="סגירה">
          סגירה
        </button>
      </div>
      {send.isSuccess ? (
        <p className="badge ok" data-testid="feedback-sent">
          המשוב נשלח. תודה!
        </p>
      ) : (
        <>
          <div className="row" role="radiogroup" aria-label="סוג המשוב">
            {KINDS.map(([k, label]) => (
              <label key={k} className={`chip${kind === k ? ' on' : ''}`}>
                <input type="radio" name="feedback-kind" value={k} checked={kind === k} onChange={() => setKind(k)} />
                {label}
              </label>
            ))}
          </div>
          <label className="field">
            מה קרה, או מה היית רוצה שיהיה?
            <textarea
              className="input"
              name="feedback-message"
              rows={5}
              maxLength={4000}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </label>
          <label className="field">
            איך לחזור אליך (לא חובה)
            <input className="input" name="feedback-contact" maxLength={200} value={contact} onChange={(e) => setContact(e.target.value)} />
          </label>
          <p className="muted small">נשמרים גם העמוד שבו אתה נמצא וסוג הדפדפן, כדי שיהיה אפשר לשחזר את הבעיה.</p>
          {send.isError && <ErrorBox error={send.error} />}
          <button className="btn primary" data-testid="feedback-send" disabled={!message.trim() || send.isPending} onClick={() => send.mutate()}>
            שליחת משוב
          </button>
        </>
      )}
    </section>
  )
}

/** Share link for one project: whoever opens it can copy the project into their own space. */
export function ShareProject({ projectId }: { projectId: string }) {
  const [token, setToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const share = useMutation({
    mutationFn: () => api.post<{ token: string }>(`/api/projects/${projectId}/share`),
    onSuccess: (r) => setToken(r.token),
  })
  const revoke = useMutation({
    mutationFn: () => api.del(`/api/projects/${projectId}/share`),
    onSuccess: () => setToken(null),
  })
  const link = token ? `${window.location.origin}/s/${token}` : ''
  return (
    <details className="card share-box" data-testid="share-box">
      <summary>שיתוף הפרויקט</summary>
      <p className="muted small">
        מי שיפתח את הקישור יקבל עותק של הפרויקט, כולל הסימולציות והמדידות, במרחב שלו. את הפרויקט שלך הוא לא יכול לשנות.
      </p>
      {!token ? (
        <button className="btn" data-testid="share-create" disabled={share.isPending} onClick={() => share.mutate()}>
          יצירת קישור שיתוף
        </button>
      ) : (
        <div className="row">
          <input className="input grow ltr" readOnly value={link} data-testid="share-link" onFocus={(e) => e.currentTarget.select()} />
          <button className="btn" onClick={() => void copyText(link).then(setCopied)}>
            {copied ? 'הועתק' : 'העתקה'}
          </button>
          <button className="btn danger" data-testid="share-revoke" disabled={revoke.isPending} onClick={() => revoke.mutate()}>
            ביטול הקישור
          </button>
        </div>
      )}
      {(share.isError || revoke.isError) && <ErrorBox error={share.error ?? revoke.error} />}
    </details>
  )
}

/** The owner's own workspace link, to continue on another device. Only in per-browser mode. */
export function WorkspaceLink() {
  const ws = useQuery({
    queryKey: ['workspace'],
    queryFn: () => api.get<{ mode: string; token: string | null }>('/api/workspace'),
  })
  const [show, setShow] = useState(false)
  const [copied, setCopied] = useState(false)
  if (!ws.data?.token) return null
  const link = `${window.location.origin}/w#${ws.data.token}`
  return (
    <details className="card" data-testid="workspace-box" onToggle={(e) => setShow(e.currentTarget.open)}>
      <summary>המשך ממכשיר אחר</summary>
      <p className="muted small">
        הפרויקטים שלך שמורים בדפדפן הזה בלבד, בלי שם משתמש וסיסמה. כדי לעבוד עליהם ממכשיר אחר, פתח שם את הקישור הזה. מי שמחזיק
        בקישור יכול לערוך את כל הפרויקטים שלך, אז אל תשלח אותו לאחרים. לשיתוף פרויקט עם חבר יש קישור שיתוף בתוך הפרויקט.
      </p>
      {show && (
        <div className="row">
          <input className="input grow ltr" readOnly value={link} data-testid="workspace-link" onFocus={(e) => e.currentTarget.select()} />
          <button className="btn" onClick={() => void copyText(link).then(setCopied)}>
            {copied ? 'הועתק' : 'העתקה'}
          </button>
        </div>
      )}
    </details>
  )
}
