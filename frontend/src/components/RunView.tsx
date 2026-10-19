import { useMemo } from 'react'
import { useReproduce } from '../api/hooks'
import type { Param, ResultTable, Run } from '../api/types'
import { fmt } from '../format'
import { fmtDate, t } from '../i18n'
import Chart from './Chart'
import { ErrorBox } from './ErrorBox'
import StatusBadge from './StatusBadge'

export function DataTable({ table, highlightRow }: { table: ResultTable; highlightRow?: number }) {
  return (
    <div className="table-wrap">
      <table className="data" aria-label={table.title_he}>
        <thead>
          <tr>
            {table.columns.map((c) => (
              <th key={c.key} className={c.unit !== '' || c.key === 'point' ? 'num' : ''}>
                {c.label_he}
                {c.unit && <span className="muted"> [{c.unit}]</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i} style={i === highlightRow ? { background: 'var(--accent-soft)' } : undefined}>
              {table.columns.map((c) => (
                <td key={c.key} className={typeof r[c.key] === 'number' || r[c.key] === null ? 'num' : ''}>
                  {c.key === 'point' ? String(r[c.key]) : fmt(r[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ParamTable({ params, method }: { params: Param[]; method: Param['method'] }) {
  const rows = params.filter((p) => p.method === method)
  if (rows.length === 0) return null
  return (
    <div className="stack" style={{ gap: 6 }}>
      <h3>{method === 'consistent' ? t('run.consistent') : t('run.manual')}</h3>
      <table className="data" data-testid={`params-${method}`}>
        <thead>
          <tr>
            <th>גודל</th>
            <th className="num">ערך</th>
            <th>{t('run.formula')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.key} data-param={p.key}>
              <td>
                {p.label_he}
                {p.note && <div className="muted small">{p.note}</div>}
              </td>
              <td className="num">
                {p.value === null ? (
                  <span className="badge err" title={p.undefined_reason ?? ''}>
                    {t('run.undefined')}
                  </span>
                ) : (
                  <>
                    {fmt(p.value, 5)} {p.unit}
                  </>
                )}
                {p.value === null && p.undefined_reason && <div className="small" style={{ color: 'var(--err)' }}>{p.undefined_reason}</div>}
              </td>
              <td className="formula">{p.formula}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function RunView({ run }: { run: Run }) {
  const reproduce = useReproduce()
  const res = run.result
  const readings = res?.tables[0]

  const charts = useMemo(() => {
    if (!res || !readings) return []
    return res.curves.map((c) => {
      const xc = readings.columns.find((k) => k.key === c.x)
      const yc = readings.columns.find((k) => k.key === c.y)
      const pts = readings.rows
        .map((r) => [r[c.x], r[c.y]] as [unknown, unknown])
        .filter((p): p is [number, number] => typeof p[0] === 'number' && typeof p[1] === 'number')
      return {
        id: c.id,
        title: c.title_he,
        xLabel: `${xc?.label_he ?? c.x} [${xc?.unit ?? ''}]`,
        yLabel: `${yc?.label_he ?? c.y} [${yc?.unit ?? ''}]`,
        series: [{ label: 'סימולציה', kind: 'sim' as const, points: pts }],
      }
    })
  }, [res, readings])

  return (
    <div className="stack" data-testid="run-view" data-run-id={run.id}>
      <div className="row">
        <StatusBadge status={run.status} />
        <span className="badge sim">{t('run.source')}</span>
        {run.label && <strong>{run.label}</strong>}
        <span className="muted small grow">
          {fmtDate(run.created_at)} · {run.model_version} · hash {run.input_hash.slice(0, 10)}
        </span>
        <button className="btn small" onClick={() => reproduce.mutate(run.id)} disabled={reproduce.isPending}>
          {t('run.reproduce')}
        </button>
        {reproduce.data && (
          <span className={`badge ${reproduce.data.identical ? 'ok' : 'err'}`} data-testid="reproduce-result">
            {reproduce.data.identical ? t('run.reproduced') : t('run.notReproduced')}
          </span>
        )}
      </div>
      {reproduce.isError && <ErrorBox error={reproduce.error} />}

      {run.error && (
        <div className="alert error" role="alert" data-testid="run-error">
          <strong>
            {t('run.error')} ({t(`status.${run.status}`)}):
          </strong>{' '}
          {run.error.message}
          {run.error.details != null && (
            <pre className="small" style={{ whiteSpace: 'pre-wrap', margin: '6px 0 0' }}>
              {typeof run.error.details === 'string' ? run.error.details : JSON.stringify(run.error.details, null, 1)}
            </pre>
          )}
        </div>
      )}

      {run.warnings.length > 0 && (
        <div className="alert warn" data-testid="run-warnings">
          <strong>{t('run.warnings')}:</strong>
          <ul style={{ margin: '4px 0 0', paddingInlineStart: 18 }}>
            {Array.from(new Map(run.warnings.map((w) => [w.code + w.message, w])).values()).map((w, i) => (
              <li key={i}>{w.message}</li>
            ))}
          </ul>
        </div>
      )}

      {res &&
        res.tables.map((tb) => (
          <section key={tb.id} className="card stack">
            <h2>{tb.title_he}</h2>
            <DataTable table={tb} highlightRow={tb.id === 'readings' ? res.parameters_at?.row : undefined} />
          </section>
        ))}

      {res && charts.length > 0 && (
        <div className="grid-2">
          {charts.map((c) => (
            <section key={c.id} className="card">
              <Chart title={c.title} xLabel={c.xLabel} yLabel={c.yLabel} series={c.series} />
            </section>
          ))}
        </div>
      )}

      {res && res.parameters.length > 0 && (
        <section className="card stack">
          <h2>{t('run.parameters')}</h2>
          {res.parameters_at && (
            <p className="muted small">
              {t('run.atPoint')} #{(res.parameters_at.row ?? 0) + 1} (מסומנת בטבלה)
            </p>
          )}
          <div className="grid-2">
            <ParamTable params={res.parameters} method="consistent" />
            <ParamTable params={res.parameters} method="manual" />
          </div>
        </section>
      )}

      <details className="card">
        <summary>{t('run.snapshot')}</summary>
        <pre className="small" dir="ltr" style={{ maxHeight: 300, overflow: 'auto' }}>
          {JSON.stringify({ case: run.input_snapshot.case, transformer: run.input_snapshot.transformer }, null, 2)}
        </pre>
      </details>
    </div>
  )
}
