import { useState } from 'react'
import { useUpdateProject } from '../api/hooks'
import type { Project, Provenance, TransformerSpec } from '../api/types'
import { fmt } from '../format'
import { t } from '../i18n'
import { ErrorBox } from './ErrorBox'

type Section = 'nameplate' | 'ecm' | 'insulation'
interface FieldDef {
  section: Section
  key: string
  label: string
  unit: string
  kind?: 'conn'
}

const FIELDS: FieldDef[] = [
  { section: 'nameplate', key: 'S_n', label: 'הספק נקוב S_n', unit: 'VA' },
  { section: 'nameplate', key: 'U1n', label: 'מתח ראשוני קווי U1n', unit: 'V' },
  { section: 'nameplate', key: 'U2n', label: 'מתח משני קווי U2n', unit: 'V' },
  { section: 'nameplate', key: 'f_n', label: 'תדירות', unit: 'Hz' },
  { section: 'nameplate', key: 'primary', label: 'חיבור ראשוני נקוב', unit: '', kind: 'conn' },
  { section: 'nameplate', key: 'secondary', label: 'חיבור משני נקוב', unit: '', kind: 'conn' },
  { section: 'ecm', key: 'R1', label: 'R1 (ליפוף ראשוני)', unit: 'Ω' },
  { section: 'ecm', key: 'X1', label: 'X1 פיזור ראשוני', unit: 'Ω' },
  { section: 'ecm', key: 'R2', label: 'R2 (ליפוף משני)', unit: 'Ω' },
  { section: 'ecm', key: 'X2', label: 'X2 פיזור משני', unit: 'Ω' },
  { section: 'ecm', key: 'R_fe', label: 'R_Fe הפסדי ברזל', unit: 'Ω' },
  { section: 'ecm', key: 'Xm_unsat', label: 'X_m לא רווי', unit: 'Ω' },
  { section: 'ecm', key: 'sat_c', label: 'עוצמת רוויה c', unit: '' },
  { section: 'ecm', key: 'sat_n', label: 'מעריך רוויה n', unit: '' },
  { section: 'insulation', key: 'primary_core_Mohm', label: 'ראשוני–גרעין', unit: 'MΩ' },
  { section: 'insulation', key: 'secondary_core_Mohm', label: 'משני–גרעין', unit: 'MΩ' },
  { section: 'insulation', key: 'primary_secondary_Mohm', label: 'ראשוני–משני', unit: 'MΩ' },
]

type Draft = Record<string, string>

function toDraft(s: TransformerSpec): Draft {
  const d: Draft = {}
  for (const f of FIELDS) d[`${f.section}.${f.key}`] = String((s[f.section] as unknown as Record<string, unknown>)[f.key])
  return d
}

function fromDraft(base: TransformerSpec, d: Draft, provenance: Provenance, note: string): TransformerSpec | string {
  const out = structuredClone(base) as unknown as Record<Section, Record<string, unknown>> & TransformerSpec
  for (const f of FIELDS) {
    const raw = d[`${f.section}.${f.key}`] ?? ''
    if (f.kind === 'conn') {
      out[f.section][f.key] = raw
      continue
    }
    const v = Number(raw)
    if (raw.trim() === '' || !Number.isFinite(v)) return `${f.label}: ${t('spec.invalidNumber')}`
    out[f.section][f.key] = v
  }
  out.provenance = provenance
  out.provenance_note = note
  return out
}

const SECTION_TITLE: Record<Section, 'spec.nameplate' | 'spec.ecm' | 'spec.insulation'> = {
  nameplate: 'spec.nameplate',
  ecm: 'spec.ecm',
  insulation: 'spec.insulation',
}

export default function TransformerForm({ project }: { project: Project }) {
  const update = useUpdateProject(project.id)
  const [draft, setDraft] = useState<Draft>(() => toDraft(project.transformer))
  const [prov, setProv] = useState<Provenance>(project.transformer.provenance)
  const [note, setNote] = useState(project.transformer.provenance_note)
  const [localError, setLocalError] = useState<string | null>(null)
  const d = project.derived

  const save = () => {
    const spec = fromDraft(project.transformer, draft, prov, note)
    if (typeof spec === 'string') {
      setLocalError(spec)
      return
    }
    setLocalError(null)
    update.mutate({ transformer: spec })
  }

  return (
    <div className="stack" data-testid="transformer-form">
      {project.transformer.provenance === 'assumed' && (
        <div className="alert warn">
          {t('provenance.assumed')}. {project.transformer.provenance_note}
        </div>
      )}
      <div className="grid-2">
        {(['nameplate', 'ecm', 'insulation'] as Section[]).map((sec) => (
          <section key={sec} className="card stack">
            <h2>{t(SECTION_TITLE[sec])}</h2>
            <div className="grid-2" style={{ gap: 10 }}>
              {FIELDS.filter((f) => f.section === sec).map((f) => {
                const k = `${f.section}.${f.key}`
                const val = draft[k] ?? ''
                const invalid = f.kind !== 'conn' && (val.trim() === '' || !Number.isFinite(Number(val)))
                return (
                  <label key={k} className="field">
                    {f.label} {f.unit && <span className="muted">[{f.unit}]</span>}
                    {f.kind === 'conn' ? (
                      <select className="input" name={k} value={val} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}>
                        <option value="Y">Y (כוכב)</option>
                        <option value="D">Δ (משולש)</option>
                      </select>
                    ) : (
                      <input
                        className={`input num${invalid ? ' invalid' : ''}`}
                        name={k}
                        inputMode="decimal"
                        value={val}
                        aria-invalid={invalid}
                        onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
                      />
                    )}
                  </label>
                )
              })}
            </div>
          </section>
        ))}
        <section className="card stack">
          <h2>{t('spec.derived')}</h2>
          <dl className="kv">
            <dt>מתח ליפוף ראשוני</dt>
            <dd className="num">{fmt(d.U1_winding)} V</dd>
            <dt>מתח ליפוף משני</dt>
            <dd className="num">{fmt(d.U2_winding)} V</dd>
            <dt>יחס כריכות n1/n2</dt>
            <dd className="num">{fmt(d.turns_ratio, 5)}</dd>
            <dt>I1n (קווי)</dt>
            <dd className="num">{fmt(d.I1n_line)} A</dd>
            <dt>I2n (קווי)</dt>
            <dd className="num">{fmt(d.I2n_line)} A</dd>
          </dl>
          <p className="muted small">
            מודל: מעגל תמורה T לכל עמוד, ענף מגנוט רווי X_m(E) = X_m,unsat / (1 + c·(E/E_n)^n). אין צימוד מגנטי בין העמודים.
          </p>
          <label className="field">
            {t('spec.provenance')}
            <select className="input" name="provenance" value={prov} onChange={(e) => setProv(e.target.value as Provenance)}>
              {(['assumed', 'nameplate', 'measured', 'fitted'] as Provenance[]).map((p) => (
                <option key={p} value={p}>
                  {t(`provenance.${p}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t('spec.provenanceNote')}
            <input className="input" name="provenance_note" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
        </section>
      </div>
      <div className="row">
        <button className="btn primary" onClick={save} disabled={update.isPending}>
          {t('spec.save')}
        </button>
        {update.isSuccess && <span className="badge ok">{t('spec.saved')}</span>}
      </div>
      {localError && <div className="alert error" role="alert">{localError}</div>}
      {update.isError && <ErrorBox error={update.error} />}
    </div>
  )
}
