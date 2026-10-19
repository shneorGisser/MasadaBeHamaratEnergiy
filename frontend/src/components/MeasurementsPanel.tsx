import { useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { mKeys, useComparison, useMeasurementSet, useMeasurementSets, useRuns } from '../api/hooks'
import type { Comparison, MColumn, MSetView, Run, Study } from '../api/types'
import { fmt } from '../format'
import { fmtDate } from '../i18n'
import Chart, { type Series } from './Chart'
import { ErrorBox } from './ErrorBox'
import { curveSeries } from './curves'
import { DataTable } from './RunView'
import StatusBadge from './StatusBadge'

function Cell({
  setId,
  row,
  col,
  view,
  onSaved,
}: {
  setId: string
  row: number
  col: MColumn
  view: MSetView
  onSaved: (v: MSetView) => void
}) {
  const cell = view.cells[`${row}:${col.key}`]
  const [text, setText] = useState(cell ? String(cell.entered_value) : '')
  const [unit, setUnit] = useState(cell?.entered_unit ?? col.unit)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const history = view.history.filter((h) => h.row === row && h.quantity === col.key)

  const commit = async () => {
    const trimmed = text.trim()
    if (trimmed === '') return
    const v = Number(trimmed)
    if (!Number.isFinite(v)) {
      setErr('מספר לא תקין')
      return
    }
    if (cell && cell.entered_value === v && cell.entered_unit === unit) return
    setBusy(true)
    setErr(null)
    try {
      onSaved(await api.post<MSetView>(`/api/measurement-sets/${setId}/entries`, { row_index: row, quantity: col.key, value: v, unit }))
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <td className="mcell" data-testid={`cell-${row}-${col.key}`}>
      <div className="row" style={{ gap: 2, flexWrap: 'nowrap' }}>
        <input
          className={`input num${err ? ' invalid' : ''}${!cell ? ' missing' : ''}`}
          style={{ width: 82, padding: '3px 5px' }}
          value={text}
          placeholder="חסר"
          aria-label={`${col.label_he} שורה ${row + 1}`}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => void commit()}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void commit()
          }}
        />
        {col.units.length > 1 && (
          <select className="input" style={{ padding: '3px 2px', fontSize: 12 }} value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="יחידה">
            {col.units.map((u) => (
              <option key={u}>{u}</option>
            ))}
          </select>
        )}
      </div>
      {cell && cell.versions > 1 && (
        <span
          className="badge warn"
          style={{ fontSize: 10 }}
          data-testid="corrected"
          title={history.map((h) => `${fmtDate(h.created_at)}: ${h.entered_value} ${h.entered_unit}`).join('\n')}
        >
          תוקן ×{cell.versions - 1}
        </span>
      )}
      {err && <div className="small" style={{ color: 'var(--err)' }}>{err}</div>}
    </td>
  )
}

function MeasurementTable({ view, onSaved }: { view: MSetView; onSaved: (v: MSetView) => void }) {
  const d = view.definition
  const rows = Array.from({ length: view.set.n_rows }, (_, i) => i)
  const addRow = async () => onSaved(await api.patch<MSetView>(`/api/measurement-sets/${view.set.id}`, { n_rows: view.set.n_rows + 1 }))
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="table-wrap" style={{ maxHeight: 520 }}>
        <table className="data" aria-label="טבלת מדידות">
          <thead>
            <tr>
              <th>#</th>
              {d.columns.map((c) => (
                <th key={c.key}>
                  {c.label_he}
                  {c.unit && <span className="muted"> [{c.unit}]</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r}>
                <td className="small">{d.row_labels[r] ?? r + 1}</td>
                {d.columns.map((c) => (
                  <Cell key={`${view.set.id}-${r}-${c.key}`} setId={view.set.id} row={r} col={c} view={view} onSaved={onSaved} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row small">
        {d.rows === 'free' && (
          <button className="btn small" onClick={() => void addRow()} data-testid="add-row">
            + שורה
          </button>
        )}
        <span className={`badge ${view.missing.length ? 'warn' : 'ok'}`} data-testid="missing-count">
          {view.missing.length ? `${view.missing.length} ערכים חסרים` : 'הטבלה מלאה'}
        </span>
        <span className="muted">תיקון ערך יוצר רשומה חדשה; הערך המקורי נשמר בהיסטוריה.</span>
      </div>
    </div>
  )
}

function NewSetForm({ projectId, study, onCreated }: { projectId: string; study: Study; onCreated: (id: string) => void }) {
  const [label, setLabel] = useState('')
  const [date, setDate] = useState('')
  const [instruments, setInstruments] = useState('')
  const [loadKind, setLoadKind] = useState('R')
  const [err, setErr] = useState<unknown>(null)
  const qc = useQueryClient()
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const v = await api.post<MSetView>(`/api/projects/${projectId}/measurement-sets`, {
        study_kind: study.kind,
        label,
        lab_date: date,
        instruments,
        conditions: study.kind === 'load' ? { load_kind: loadKind } : {},
      })
      void qc.invalidateQueries({ queryKey: mKeys.sets(projectId, study.kind) })
      onCreated(v.set.id)
    } catch (e2) {
      setErr(e2)
    }
  }
  return (
    <form className="row" onSubmit={(e) => void submit(e)} aria-label="סט מדידות חדש">
      <label className="field grow">
        שם הסט
        <input className="input" name="set-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="למשל: מעבדה 12.10, שולחן 4" />
      </label>
      <label className="field">
        תאריך
        <input className="input" type="date" name="set-date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label className="field grow">
        מכשירים
        <input className="input" name="set-instruments" value={instruments} onChange={(e) => setInstruments(e.target.value)} placeholder="דגם, תחום, דיוק" />
      </label>
      {study.kind === 'load' && (
        <label className="field">
          סוג עומס
          <select className="input" name="set-load-kind" value={loadKind} onChange={(e) => setLoadKind(e.target.value)}>
            <option>R</option>
            <option>L</option>
            <option>C</option>
          </select>
        </label>
      )}
      <button className="btn primary" type="submit" style={{ alignSelf: 'end' }} data-testid="create-set">
        צור סט מדידות
      </button>
      {err != null && <ErrorBox error={err} />}
    </form>
  )
}

function pct(x: number | null): string {
  return x === null ? '—' : `${(100 * x).toFixed(2)}%`
}

function ComparisonView({ cmp, view }: { cmp: Comparison; view: MSetView }) {
  const qcols = useMemo(() => view.definition.columns.concat(view.derived_columns.map((c) => ({ ...c, units: [] }))), [view])
  const label = (q: string) => qcols.find((c) => c.key === q)?.label_he ?? q
  const charts = useMemo(() => {
    // only curves of the main readings table can be compared with a measured table
    return cmp.curves
      .filter((c) => !c.table || c.table === 'readings')
      .map((c) => {
        const series: Series[] = curveSeries(
          // a model-only companion series (Kloss, Ef at no load) has no measured counterpart
          c.y3 ? c : { ...c, y2: undefined },
          [
            { label: 'סימולציה', kind: 'sim', rows: cmp.simulated_rows },
            { label: 'מדידה', kind: 'meas', rows: cmp.measured_analysis.rows },
          ],
          qcols,
        )
        return { ...c, series }
      })
  }, [cmp, qcols])

  return (
    <div className="stack" data-testid="comparison">
      <div className="row small">
        <span className="badge meas">מדידה</span>
        <span className="badge sim">סימולציה</span>
        <span className="badge theory">מודל (פרמטרי המפרט)</span>
        <span className="grow" />
        <span data-testid="cmp-summary">
          שורות: {cmp.summary.rows} (ריקות שדולגו: {cmp.summary.empty_rows_skipped}) · ללא התאמה: {cmp.summary.unmatched_rows} · חסרים: {cmp.summary.missing_measurements} · שגיאה יחסית מרבית:{' '}
          {pct(cmp.summary.max_abs_rel_error)}
        </span>
      </div>
      <ul className="small muted" style={{ margin: 0 }}>
        {cmp.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      <div className="table-wrap" style={{ maxHeight: 560 }}>
        <table className="data" aria-label="השוואה">
          <thead>
            <tr>
              <th>שורה</th>
              <th>גודל</th>
              <th className="num">נמדד</th>
              <th className="num">מסומלץ</th>
              <th className="num">שגיאה מוחלטת</th>
              <th className="num">שגיאה יחסית</th>
            </tr>
          </thead>
          <tbody>
            {cmp.pairs.flatMap((p) =>
              p.simulated_row === null
                ? [
                    <tr key={`u${p.measured_row}`} data-testid="unmatched">
                      <td>{p.measured_row + 1}</td>
                      <td colSpan={5} style={{ color: 'var(--warn)' }}>
                        {p.unmatched_reason}
                      </td>
                    </tr>,
                  ]
                : p.cells.map((c, k) => (
                    <tr key={`${p.measured_row}-${c.quantity}`} data-q={`${p.measured_row}:${c.quantity}`}>
                      <td>{k === 0 ? p.measured_row + 1 : ''}</td>
                      <td>
                        {label(c.quantity)} {c.unit && <span className="muted">[{c.unit}]</span>}
                      </td>
                      <td className="num" style={{ color: 'var(--meas)' }}>
                        {c.measured === null ? <span className="badge warn">חסר</span> : fmt(c.measured)}
                      </td>
                      <td className="num" style={{ color: 'var(--sim)' }}>
                        {fmt(c.simulated)}
                      </td>
                      <td className="num">{fmt(c.abs_error)}</td>
                      <td className="num" title={c.undefined_reason ?? ''} data-rel={c.rel_error ?? ''}>
                        {c.rel_error === null ? <span className="muted small">{c.measured === null ? '—' : c.undefined_reason ?? '—'}</span> : pct(c.rel_error)}
                      </td>
                    </tr>
                  )),
            )}
          </tbody>
        </table>
      </div>
      {cmp.parameters.length > 0 && (
        <section className="card stack">
          <h3>פרמטרים: מודל · מחולץ מהסימולציה · מחולץ מהמדידה</h3>
          <table className="data" data-testid="param-triad">
            <thead>
              <tr>
                <th>גודל</th>
                <th className="num">מודל</th>
                <th className="num">סימולציה</th>
                <th className="num">מדידה</th>
                <th className="num">שגיאה יחסית</th>
              </tr>
            </thead>
            <tbody>
              {cmp.parameters.map((p) => (
                <tr key={p.key} data-param={p.key}>
                  <td>
                    {p.label_he} {p.method === 'manual' && <span className="badge warn">נוסחת החוברת</span>}
                  </td>
                  <td className="num" style={{ color: 'var(--theory)' }}>
                    {fmt(p.theory, 5)} {p.theory !== null && p.unit}
                  </td>
                  <td className="num" style={{ color: 'var(--sim)' }}>
                    {fmt(p.simulated, 5)}
                  </td>
                  <td className="num" style={{ color: 'var(--meas)' }}>
                    {fmt(p.measured, 5)}
                  </td>
                  <td className="num" title={p.undefined_reason ?? ''}>
                    {p.rel_error === null ? <span className="muted small">{p.undefined_reason ?? '—'}</span> : pct(p.rel_error)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {charts.length > 0 && (
        <div className="grid-2">
          {charts.map((c) => (
            <section key={c.id} className="card">
              <Chart title={c.title_he} xLabel={label(c.x)} yLabel={label(c.y)} series={c.series} />
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

export default function MeasurementsPanel({ projectId, study }: { projectId: string; study: Study }) {
  const sets = useMeasurementSets(projectId, study.kind)
  const runs = useRuns(projectId, study.kind)
  const [setId, setSetId] = useState<string | null>(null)
  const activeSetId = setId ?? sets.data?.[0]?.id ?? null
  const view = useMeasurementSet(activeSetId)
  const qc = useQueryClient()
  const [runId, setRunId] = useState<string | null>(null)
  const [reference, setReference] = useState<'simulation' | 'measurement'>('simulation')
  const okRuns = (runs.data ?? []).filter((r) => r.status === 'success' || r.status === 'success_with_warnings')
  const activeRunId = runId && okRuns.some((r) => r.id === runId) ? runId : (okRuns[0]?.id ?? null)
  const cmp = useComparison(view.data ? activeRunId : null, activeSetId, reference)
  const [simErr, setSimErr] = useState<unknown>(null)
  const [simBusy, setSimBusy] = useState(false)

  const onSaved = (v: MSetView) => {
    qc.setQueryData(mKeys.set(v.set.id), v)
    void qc.invalidateQueries({ queryKey: ['cmp'] })
  }

  const simulateMatching = async () => {
    if (!activeSetId) return
    setSimBusy(true)
    setSimErr(null)
    try {
      const run = await api.post<Run>(`/api/measurement-sets/${activeSetId}/simulate`)
      await qc.invalidateQueries({ queryKey: ['runs', projectId] })
      setRunId(run.id)
    } catch (e) {
      setSimErr(e)
    } finally {
      setSimBusy(false)
    }
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h2>מדידות אמת מהמעבדה</h2>
        <p className="muted small">ערכים שנמדדו בפועל במעבדה הפיזית. הם מסומנים כמדידה ואינם מתערבבים עם תוצאות סימולציה.</p>
        <NewSetForm projectId={projectId} study={study} onCreated={setSetId} />
        {sets.isError && <ErrorBox error={sets.error} />}
        {(sets.data?.length ?? 0) > 0 && (
          <label className="field">
            סט מדידות
            <select className="input" name="set-select" value={activeSetId ?? ''} onChange={(e) => setSetId(e.target.value)}>
              {sets.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label || s.id.slice(0, 8)} {s.lab_date && `· ${s.lab_date}`}
                  {s.conditions.load_kind ? ` · עומס ${s.conditions.load_kind}` : ''}
                </option>
              ))}
            </select>
          </label>
        )}
        {view.isError && <ErrorBox error={view.error} />}
        {view.data && <MeasurementTable key={view.data.set.id} view={view.data} onSaved={onSaved} />}
      </section>

      {view.data && (view.data.analysis.parameters.length > 0 || view.data.derived_columns.length > 0) && (
        <section className="card stack">
          <h2>ניתוח המדידות (אותן משוואות כמו בסימולציה)</h2>
          {view.data.analysis.warnings.map((w) => (
            <div key={w.code} className="alert warn small">
              {w.message}
            </div>
          ))}
          {view.data.derived_columns.length > 0 && (
            <DataTable
              table={{
                id: 'mderived',
                title_he: 'גדלים נגזרים מהמדידה',
                columns: [{ key: 'point', label_he: '#', unit: '' }, ...view.data.derived_columns],
                rows: view.data.analysis.rows,
              }}
            />
          )}
          {view.data.analysis.summary && (
            <DataTable
              table={{
                id: 'msummary',
                title_he: 'התנגדות ממוצעת לליפוף (נמדד)',
                columns: [
                  { key: 'winding', label_he: 'ליפוף', unit: '' },
                  { key: 'R_avg', label_he: 'R ממוצע', unit: 'Ω' },
                  { key: 'n', label_he: 'מדידות', unit: '' },
                ],
                rows: view.data.analysis.summary,
              }}
            />
          )}
        </section>
      )}

      {view.data && (
        <section className="card stack">
          <h2>השוואה: מדידה מול סימולציה</h2>
          <div className="row">
            <label className="field grow">
              ריצת סימולציה לייחוס
              <select className="input" name="cmp-run" value={activeRunId ?? ''} onChange={(e) => setRunId(e.target.value)}>
                {okRuns.length === 0 && <option value="">אין ריצות מוצלחות</option>}
                {okRuns.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label || fmtDate(r.created_at)} · {r.input_hash.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              ערך ייחוס לשגיאה יחסית
              <select className="input" name="cmp-ref" value={reference} onChange={(e) => setReference(e.target.value as 'simulation' | 'measurement')}>
                <option value="simulation">סימולציה</option>
                <option value="measurement">מדידה</option>
              </select>
            </label>
            <button className="btn primary" style={{ alignSelf: 'end' }} onClick={() => void simulateMatching()} disabled={simBusy} data-testid="simulate-matching">
              סימולציה בנקודות המדידה
            </button>
          </div>
          {simErr != null && <ErrorBox error={simErr} />}
          {runs.data && activeRunId && <StatusBadge status={runs.data.find((r) => r.id === activeRunId)!.status} />}
          {cmp.isError && <ErrorBox error={cmp.error} />}
          {cmp.data && <ComparisonView cmp={cmp.data} view={view.data} />}
        </section>
      )}
    </div>
  )
}
