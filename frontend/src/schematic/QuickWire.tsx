/**
 * Wiring from the keyboard (Ctrl+K): type the two terminals, e.g. "M.U2" and "M.V1", Enter.
 *
 * Why: dragging between small handles is slow on a laptop touchpad and impossible without a
 * mouse. Every connection made here goes through the same onConnect as a drag, and is
 * announced in an aria-live region for screen readers. Terminal names are "component.terminal",
 * as in the nets list and the wiring guide; matching ignores case and spaces.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Connection, Edge } from '@xyflow/react'
import type { CompNode } from './model'
import { findTerminal, terminalsOf } from './quickwire'

export default function QuickWire({
  nodes,
  edges,
  onConnect,
  onClose,
}: {
  nodes: CompNode[]
  edges: Edge[]
  onConnect: (c: Connection) => void
  onClose: () => void
}) {
  const all = useMemo(() => terminalsOf(nodes), [nodes])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [announce, setAnnounce] = useState('')
  const fromRef = useRef<HTMLInputElement>(null)
  useEffect(() => fromRef.current?.focus(), [])

  const connect = () => {
    const a = findTerminal(all, from)
    const b = findTerminal(all, to)
    if ('error' in a) return setError(a.error)
    if ('error' in b) return setError(b.error)
    if (a.key === b.key) return setError('אותו הדק בשני הצדדים')
    const dup = edges.some(
      (e) =>
        (e.source === a.component && e.sourceHandle === a.terminal && e.target === b.component && e.targetHandle === b.terminal) ||
        (e.source === b.component && e.sourceHandle === b.terminal && e.target === a.component && e.targetHandle === a.terminal),
    )
    if (dup) return setError(`${a.key} ו-${b.key} כבר מחוברים`)
    onConnect({ source: a.component, sourceHandle: a.terminal, target: b.component, targetHandle: b.terminal })
    setError(null)
    setAnnounce(`חובר: ${a.key} אל ${b.key}`)
    setFrom('')
    setTo('')
    fromRef.current?.focus()
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="card modal"
        style={{ width: 'min(520px, 100%)' }}
        role="dialog"
        aria-modal="true"
        aria-label="חיבור מהמקלדת"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        data-testid="quick-wire"
      >
        <div className="row">
          <h3 className="grow">חיבור מהמקלדת</h3>
          <button className="btn small" onClick={onClose}>
            סגירה
          </button>
        </div>
        <p className="muted small">
          כתבו רכיב.הדק (למשל <bdi className="formula">M.U2</bdi>), או רק שם הדק אם הוא ייחודי. Enter מחבר ומשאיר את החלון פתוח לכבל הבא; Esc סוגר.
        </p>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault()
            connect()
          }}
        >
          <label className="field grow">
            מ-
            <input ref={fromRef} className="input ltr" list="qw-terminals" value={from} onChange={(e) => setFrom(e.target.value)} name="qw-from" autoComplete="off" />
          </label>
          <label className="field grow">
            אל
            <input className="input ltr" list="qw-terminals" value={to} onChange={(e) => setTo(e.target.value)} name="qw-to" autoComplete="off" />
          </label>
          <button className="btn primary" type="submit" style={{ alignSelf: 'end' }} data-testid="qw-connect">
            חבר
          </button>
        </form>
        <datalist id="qw-terminals">
          {all.map((t) => (
            <option key={t.key} value={t.key}>
              {t.label}
            </option>
          ))}
        </datalist>
        {error && (
          <p className="badge warn" role="alert">
            {error}
          </p>
        )}
        <p className="small" aria-live="polite" data-testid="qw-announce">
          {announce}
        </p>
      </section>
    </div>
  )
}
