import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import type { FromWorker, ToWorker } from '../scripting/worker'
import { examplesFor } from '../scripting/examples'
import Chart, { type Series } from './Chart'

const PALETTE = ['#1f6fb2', '#b07a1f', '#4b6b2f', '#a2462e', '#6a4c93', '#2e7d7d']

interface PlotSpec {
  title: string
  xlabel: string
  ylabel: string
  log: boolean
  x: number[]
  series: { name: string; y: (number | null)[] }[]
}
interface Line {
  kind: 'out' | 'err' | 'info'
  text: string
}

function storageKey(projectId: string) {
  return `vel.script.${projectId}`
}
function loadDraft(projectId: string): string | null {
  try {
    return localStorage.getItem(storageKey(projectId))
  } catch {
    return null
  }
}
function saveDraft(projectId: string, code: string) {
  try {
    localStorage.setItem(storageKey(projectId), code)
  } catch {
    /* private mode: the draft lives only in this page */
  }
}

/**
 * MATLAB-style scripting: Python (Pyodide) in a worker, calling the project's studies through
 * the run API. Every run a script makes is a normal, immutable run of the project.
 */
export default function ScriptPanel({ projectId, experimentId }: { projectId: string; experimentId: string }) {
  const examples = examplesFor(experimentId)
  const [code, setCode] = useState(() => loadDraft(projectId) ?? examples[examples.length - 1]?.code ?? '')
  const [lines, setLines] = useState<Line[]>([])
  const [plots, setPlots] = useState<PlotSpec[]>([])
  const [busy, setBusy] = useState(false)
  const worker = useRef<Worker | null>(null)
  const qc = useQueryClient()

  useEffect(() => () => worker.current?.terminate(), [])

  const getWorker = () => {
    if (!worker.current) {
      const w = new Worker(new URL('../scripting/worker.ts', import.meta.url), { type: 'module' })
      w.onmessage = (ev: MessageEvent<FromWorker>) => {
        const m = ev.data
        if (m.type === 'stdout') setLines((l) => [...l, { kind: 'out', text: m.text }])
        else if (m.type === 'stderr') setLines((l) => [...l, { kind: 'err', text: m.text }])
        else if (m.type === 'status') setLines((l) => [...l, { kind: 'info', text: m.text }])
        else if (m.type === 'plot') setPlots((p) => [...p, JSON.parse(m.spec) as PlotSpec])
        else {
          setBusy(false)
          void qc.invalidateQueries({ queryKey: ['runs', projectId] })
          setLines((l) => [
            ...l,
            m.type === 'done'
              ? { kind: 'info', text: `הסתיים (${(m.ms / 1000).toFixed(1)} s)` }
              : { kind: 'err', text: m.text },
          ])
        }
      }
      worker.current = w
    }
    return worker.current
  }

  const run = () => {
    saveDraft(projectId, code)
    setLines([])
    setPlots([])
    setBusy(true)
    const msg: ToWorker = { type: 'run', code, projectId }
    getWorker().postMessage(msg)
  }
  const stop = () => {
    worker.current?.terminate()
    worker.current = null
    setBusy(false)
    setLines((l) => [...l, { kind: 'err', text: 'הסקריפט נעצר. ריצות שכבר הסתיימו נשמרו בפרויקט.' }])
  }

  return (
    <div className="stack" data-testid="script-panel">
      <section className="card stack">
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <h2 className="grow" style={{ margin: 0 }}>
            סקריפט Python
          </h2>
          <select
            className="input"
            style={{ width: 'auto' }}
            aria-label="דוגמה"
            name="script-example"
            value=""
            onChange={(e) => {
              const ex = examples.find((x) => x.id === e.target.value)
              if (ex) setCode(ex.code)
            }}
          >
            <option value="">טען דוגמה…</option>
            {examples.map((x) => (
              <option key={x.id} value={x.id}>
                {x.title}
              </option>
            ))}
          </select>
          {busy ? (
            <button className="btn" onClick={stop} data-testid="script-stop">
              עצור
            </button>
          ) : (
            <button className="btn primary" onClick={run} data-testid="script-run">
              הרץ סקריפט
            </button>
          )}
        </div>
        <textarea
          className="input"
          name="script-code"
          dir="ltr"
          spellCheck={false}
          value={code}
          rows={Math.min(28, Math.max(10, code.split('\n').length + 1))}
          style={{ fontFamily: 'var(--mono)', fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre', tabSize: 4 }}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Tab') {
              e.preventDefault()
              const t = e.currentTarget
              const a = t.selectionStart
              const next = code.slice(0, a) + '    ' + code.slice(t.selectionEnd)
              setCode(next)
              requestAnimationFrame(() => t.setSelectionRange(a + 4, a + 4))
            } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !busy) {
              e.preventDefault()
              run()
            }
          }}
        />
        <p className="muted small" style={{ margin: 0 }}>
          Python 3 בדפדפן (Pyodide). <code dir="ltr">await vlab.run(study, **case)</code> מריץ ניסוי של הפרויקט בשרת —
          כל ריצה נשמרת בהיסטוריה כרגיל. <code dir="ltr">vlab.param</code>, <code dir="ltr">vlab.column</code>,{' '}
          <code dir="ltr">vlab.plot</code> לעיבוד ולגרפים. Ctrl+Enter מריץ.
        </p>
      </section>

      {lines.length > 0 && (
        <section className="card">
          <pre className="script-out" dir="ltr" data-testid="script-output">
            {lines.map((l, i) => (
              <div key={i} dir="auto" className={`script-${l.kind}`}>
                {l.text}
              </div>
            ))}
          </pre>
        </section>
      )}

      {plots.length > 0 && (
        <div className="grid-2">
          {plots.map((p, i) => (
            <section key={i} className="card">
              <Chart
                title={p.title}
                xLabel={p.xlabel}
                yLabel={p.ylabel}
                log={p.log}
                series={p.series.map<Series>((s, k) => ({
                  label: s.name,
                  kind: 'sim',
                  color: PALETTE[k % PALETTE.length],
                  points: p.x
                    .map((x, j) => [x, s.y[j]] as [number, number | null])
                    .filter((pt): pt is [number, number] => pt[1] !== null),
                }))}
              />
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
