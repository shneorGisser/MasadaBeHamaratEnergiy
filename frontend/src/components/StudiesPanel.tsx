import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useCreateRun, useRun, useRuns, useStudies } from '../api/hooks'
import type { Study } from '../api/types'
import { parseList } from '../format'
import { fmtDate, t, type MessageKey } from '../i18n'
import SchematicEditor from '../schematic/SchematicEditor'
import { ErrorBox } from './ErrorBox'
import MeasurementsPanel from './MeasurementsPanel'
import RunView from './RunView'
import StatusBadge from './StatusBadge'

const VARIANT_LABEL: Record<string, string> = {
  YY: 'כוכב-כוכב',
  YD: 'כוכב-משולש',
  'Yy-abc': 'כוכב-כוכב, סדר a b c',
  'Yy-bca': 'כוכב-כוכב, סדר b c a',
  'Yy-cab': 'כוכב-כוכב, סדר c a b',
  'Yy-abc-rev': 'כוכב-כוכב, קוטביות הפוכה',
  'Yd-abc-1': 'כוכב-משולש, סגירה x2→y1',
  'Yd-abc-2': 'כוכב-משולש, סגירה x1→y2',
}

const HIDDEN_CASE_KEYS = new Set(['bindings', 'source'])

function CaseEditor({
  study,
  value,
  onChange,
}: {
  study: Study
  value: Record<string, string>
  onChange: (v: Record<string, string>) => void
}) {
  return (
    <div className="stack" style={{ gap: 10 }}>
      {Object.entries(study.default_case)
        .filter(([k]) => !HIDDEN_CASE_KEYS.has(k))
        .map(([k, def]) => {
          const label = t(`case.${k}` as MessageKey)
          const v = value[k] ?? ''
          if (typeof def === 'boolean')
            return (
              <label key={k} className="row small">
                <input
                  type="checkbox"
                  name={`case-${k}`}
                  checked={v === 'true'}
                  onChange={(e) => onChange({ ...value, [k]: String(e.target.checked) })}
                />
                {label}
              </label>
            )
          if (k === 'load_kind')
            return (
              <label key={k} className="field">
                {label}
                <select className="input" name={`case-${k}`} value={v} onChange={(e) => onChange({ ...value, [k]: e.target.value })}>
                  <option value="R">R — התנגדותי</option>
                  <option value="L">L — השראותי</option>
                  <option value="C">C — קיבולי</option>
                </select>
              </label>
            )
          const bad = Array.isArray(def)
            ? parseList(v) === null
            : def === null
              ? v.trim() !== '' && !Number.isFinite(Number(v))
              : !Number.isFinite(Number(v)) || v.trim() === ''
          return (
            <label key={k} className="field">
              {label}
              <input
                className={`input num${bad ? ' invalid' : ''}`}
                name={`case-${k}`}
                value={v}
                aria-invalid={bad}
                onChange={(e) => onChange({ ...value, [k]: e.target.value })}
              />
            </label>
          )
        })}
    </div>
  )
}

function caseToText(c: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(c)) {
    if (HIDDEN_CASE_KEYS.has(k)) continue
    out[k] = Array.isArray(v) ? v.join(', ') : v === null || v === undefined ? '' : String(v)
  }
  return out
}

/** Build the case document; invalid text is sent as-is so the server's validation answers. */
function textToCase(study: Study, text: Record<string, string>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, def] of Object.entries(study.default_case)) {
    if (HIDDEN_CASE_KEYS.has(k)) continue
    const raw = text[k] ?? ''
    if (Array.isArray(def)) out[k] = parseList(raw) ?? raw
    else if (typeof def === 'boolean') out[k] = raw === 'true'
    else if (typeof def === 'string') out[k] = raw
    else if (def === null) out[k] = raw.trim() === '' ? null : Number(raw)
    else out[k] = raw.trim() === '' ? raw : Number(raw)
  }
  return out
}

function StudyWorkspace({ projectId, study }: { projectId: string; study: Study }) {
  const [caseText, setCaseText] = useState(() => caseToText(study.default_case))
  const [label, setLabel] = useState('')
  const [params, setParams] = useSearchParams()
  const runs = useRuns(projectId, study.kind)
  const create = useCreateRun(projectId)
  const qc = useQueryClient()
  const [variantBusy, setVariantBusy] = useState(false)
  const [variantMsg, setVariantMsg] = useState<string | null>(null)
  const selectedRunId = params.get('run') ?? runs.data?.[0]?.id ?? null
  const run = useRun(selectedRunId)

  const selectRun = (id: string) => {
    const next = new URLSearchParams(params)
    next.set('run', id)
    setParams(next, { replace: true })
  }

  const onRun = () => {
    create.mutate(
      { study_kind: study.kind, case: textToCase(study, caseText), label },
      { onSuccess: (r) => selectRun(r.id) },
    )
  }

  const resetVariant = async (variant: string) => {
    setVariantBusy(true)
    setVariantMsg(null)
    try {
      await api.post(`/api/projects/${projectId}/circuits/${study.kind}/reset`, { variant })
      setVariantMsg(variant ? `המעגל נטען בתצורה ${VARIANT_LABEL[variant] ?? variant}` : 'המעגל נטען לפי החוברת')
      void qc.invalidateQueries({ queryKey: ['circuit', projectId, study.kind] })
    } catch (e) {
      setVariantMsg(String(e))
    } finally {
      setVariantBusy(false)
    }
  }

  return (
    <div className="stack">
      <section className="card stack">
        <div className="row">
          <h2 className="grow">{study.title_he}</h2>
          <span className="muted small">חוברת: {study.manual_ref}</span>
        </div>
        {study.editable_circuit && (
          <div className="row">
            <span className="small muted">{t('study.variant')}:</span>
            {(study.variants.length > 0 ? study.variants : ['']).map((v) => (
              <button key={v} className="btn small" disabled={variantBusy} onClick={() => void resetVariant(v)}>
                {t('study.resetCircuit')}{v ? ` — ${VARIANT_LABEL[v] ?? v}` : ''}
              </button>
            ))}
            {variantMsg && <span className="badge ok">{variantMsg}</span>}
          </div>
        )}
        {study.editable_circuit && (
          <details open className="card" style={{ padding: 10 }} data-testid="circuit-section">
            <summary>מעגל הניסוי (סכמה דו-ממדית)</summary>
            <div style={{ marginTop: 10 }}>
              <SchematicEditor projectId={projectId} kind={study.kind} />
            </div>
          </details>
        )}
        <h3>{t('study.case')}</h3>
        <CaseEditor study={study} value={caseText} onChange={setCaseText} />
        <div className="row">
          <label className="field grow">
            {t('study.label')}
            <input className="input" name="run-label" value={label} onChange={(e) => setLabel(e.target.value)} />
          </label>
          <button className="btn primary" style={{ alignSelf: 'end' }} onClick={onRun} disabled={create.isPending} data-testid="run-button">
            {create.isPending ? t('study.running') : t('study.run')}
          </button>
        </div>
        {create.isError && <ErrorBox error={create.error} />}
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 280px) 1fr', gap: 16, alignItems: 'start' }}>
        <section className="card stack" style={{ gap: 6 }} aria-label={t('study.history')}>
          <h3>{t('study.history')}</h3>
          {runs.isError && <ErrorBox error={runs.error} />}
          {runs.data?.length === 0 && <p className="muted small">{t('study.noRuns')}</p>}
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 4 }} data-testid="run-history">
            {runs.data?.map((r) => (
              <li key={r.id}>
                <button
                  className="btn small"
                  style={{
                    width: '100%',
                    textAlign: 'start',
                    background: r.id === selectedRunId ? 'var(--sim-soft)' : undefined,
                  }}
                  onClick={() => selectRun(r.id)}
                >
                  <StatusBadge status={r.status} /> <span className="small">{r.label || fmtDate(r.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <div>
          {run.isLoading && <p className="muted">{t('common.loading')}</p>}
          {run.isError && <ErrorBox error={run.error} />}
          {run.data && <RunView run={run.data} />}
        </div>
      </div>
    </div>
  )
}

export default function StudiesPanel({ projectId }: { projectId: string }) {
  const studies = useStudies(projectId)
  const [params, setParams] = useSearchParams()
  if (studies.isLoading) return <p className="muted">{t('common.loading')}</p>
  if (studies.isError) return <ErrorBox error={studies.error} />
  const list = studies.data ?? []
  const kind = params.get('study') ?? 'no_load'
  const mode = params.get('mode') === 'measure' ? 'measure' : 'sim'
  const study = list.find((s) => s.kind === kind) ?? list[0]
  if (!study) return null
  return (
    <div className="stack">
      <div className="tabs" role="tablist" aria-label={t('study.select')}>
        {list.map((s) => (
          <button
            key={s.kind}
            role="tab"
            className="tab"
            aria-selected={s.kind === study.kind}
            onClick={() => setParams({ study: s.kind, mode })}
          >
            {s.title_he}
          </button>
        ))}
      </div>
      <div className="row" role="tablist" aria-label="מצב">
        {(
          [
            ['sim', 'סימולציה'],
            ['measure', 'מדידות מעבדה והשוואה'],
          ] as const
        ).map(([m, label]) => (
          <button
            key={m}
            role="tab"
            className={`btn small${mode === m ? ' primary' : ''}`}
            aria-selected={mode === m}
            onClick={() => setParams({ study: study.kind, mode: m })}
          >
            {label}
          </button>
        ))}
      </div>
      {mode === 'measure' ? (
        <MeasurementsPanel key={study.kind} projectId={projectId} study={study} />
      ) : (
        <StudyWorkspace key={study.kind} projectId={projectId} study={study} />
      )}
    </div>
  )
}
