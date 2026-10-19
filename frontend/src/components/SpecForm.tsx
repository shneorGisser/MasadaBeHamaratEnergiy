import { useQuery } from '@tanstack/react-query'
import { Fragment, useState } from 'react'
import { api } from '../api/client'
import { useUpdateProject } from '../api/hooks'
import type { EquipmentSpec, Project, Provenance } from '../api/types'
import { fmt } from '../format'
import { t } from '../i18n'
import { ErrorBox } from './ErrorBox'

type Section = 'nameplate' | 'ecm' | 'occ' | 'insulation'
interface FieldDef {
  section: Section
  key: string
  label: string
  unit: string
  /** select instead of a number input; values are kept as strings except where `int` */
  choices?: { value: string; label: string; int?: boolean }[]
}
interface FormDef {
  fields: FieldDef[]
  derived: { key: string; label: string; unit: string; digits?: number }[]
  modelNote: string
}

const CONN = [
  { value: 'Y', label: 'Y (כוכב)' },
  { value: 'D', label: 'Δ (משולש)' },
]

/** One form definition per experiment; the backend validates the same fields (single source). */
const FORMS: Record<string, FormDef> = {
  transformer3ph: {
    fields: [
      { section: 'nameplate', key: 'S_n', label: 'הספק נקוב S_n', unit: 'VA' },
      { section: 'nameplate', key: 'U1n', label: 'מתח ראשוני קווי U1n', unit: 'V' },
      { section: 'nameplate', key: 'U2n', label: 'מתח משני קווי U2n', unit: 'V' },
      { section: 'nameplate', key: 'f_n', label: 'תדירות', unit: 'Hz' },
      { section: 'nameplate', key: 'primary', label: 'חיבור ראשוני נקוב', unit: '', choices: CONN },
      { section: 'nameplate', key: 'secondary', label: 'חיבור משני נקוב', unit: '', choices: CONN },
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
    ],
    derived: [
      { key: 'U1_winding', label: 'מתח ליפוף ראשוני', unit: 'V' },
      { key: 'U2_winding', label: 'מתח ליפוף משני', unit: 'V' },
      { key: 'turns_ratio', label: 'יחס כריכות n1/n2', unit: '', digits: 5 },
      { key: 'I1n_line', label: 'I1n (קווי)', unit: 'A' },
      { key: 'I2n_line', label: 'I2n (קווי)', unit: 'A' },
    ],
    modelNote: 'מודל: מעגל תמורה T לכל עמוד, ענף מגנוט רווי X_m(E) = X_m,unsat / (1 + c·(E/E_n)^n). אין צימוד מגנטי בין העמודים.',
  },
  synchronous: {
    fields: [
      { section: 'nameplate', key: 'P_n', label: 'הספק נקוב P_n', unit: 'W' },
      { section: 'nameplate', key: 'U_n', label: 'מתח קווי נקוב U_n', unit: 'V' },
      { section: 'nameplate', key: 'I_n', label: 'זרם קווי נקוב I_n', unit: 'A' },
      { section: 'nameplate', key: 'f_n', label: 'תדירות', unit: 'Hz' },
      {
        section: 'nameplate',
        key: 'poles',
        label: 'מספר קטבים',
        unit: '',
        choices: [2, 4, 6, 8, 10, 12].map((n) => ({ value: String(n), label: `${n} (n_s = ${(6000 / n).toFixed(0)} ב-50 Hz)`, int: true })),
      },
      { section: 'nameplate', key: 'connection', label: 'חיבור הסטטור', unit: '', choices: CONN },
      { section: 'nameplate', key: 'cos_phi_n', label: 'cos φ נקוב (לא חובה)', unit: '' },
      { section: 'nameplate', key: 'If_n', label: 'זרם עירור נקוב', unit: 'A' },
      { section: 'ecm', key: 'Ra', label: 'Ra (ליפוף סטטור)', unit: 'Ω' },
      { section: 'ecm', key: 'Xl', label: 'X_l היגב פיזור (פוטייה)', unit: 'Ω' },
      { section: 'ecm', key: 'k_a', label: 'k_a תגובת עוגן [A עירור / A עוגן]', unit: '' },
      { section: 'ecm', key: 'X2', label: 'X2 היגב סדר שלילי', unit: 'Ω' },
      { section: 'ecm', key: 'X0', label: 'X0 היגב סדר אפס', unit: 'Ω' },
      { section: 'ecm', key: 'R_f', label: 'R_f ליפוף העירור', unit: 'Ω' },
      { section: 'ecm', key: 'P_fw', label: 'הפסדי חיכוך ואוורור', unit: 'W' },
      { section: 'occ', key: 'a', label: 'שיפוע קו הפער a (לליפוף)', unit: 'V/A' },
      { section: 'occ', key: 'I_s', label: 'ברך הרוויה I_s', unit: 'A' },
      { section: 'occ', key: 'm', label: 'חדות הברך m', unit: '' },
      { section: 'occ', key: 'F_res', label: 'שטף שיורי כהיסט בעירור F_res', unit: 'A' },
      { section: 'insulation', key: 'U_frame_Mohm', label: 'סטטור U – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'V_frame_Mohm', label: 'סטטור V – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'W_frame_Mohm', label: 'סטטור W – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'F_frame_Mohm', label: 'רוטור – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'stator_rotor_Mohm', label: 'סטטור – רוטור', unit: 'MΩ' },
    ],
    derived: [
      { key: 'n_sync', label: 'מהירות סינכרונית', unit: 'rpm' },
      { key: 'U_winding', label: 'מתח ליפוף נקוב', unit: 'V' },
      { key: 'Z_base', label: 'עכבת בסיס', unit: 'Ω' },
      { key: 'Xs_unsat', label: 'Xs = X_l + a·k_a (לא רווי)', unit: 'Ω' },
      { key: 'Xs_pu', label: 'Xs ביחידות יחסיות', unit: 'pu', digits: 3 },
    ],
    modelNote:
      'מודל: רוטור גלילי, שיטת כמ״מ עם רוויה: E_r = OCC(|F_f + k_a·I1|) מאחורי עכבות הסדרים (Ra + jX_l, Ra + jX2, Ra + jX0). השטף השיורי כהיסט F_res בזרם העירור. ההיגב הסינכרוני הלא רווי Xs = X_l + a·k_a.',
  },
  induction_motor: {
    fields: [
      { section: 'nameplate', key: 'P_n', label: 'הספק נקוב בציר P_n', unit: 'W' },
      { section: 'nameplate', key: 'U_n', label: 'מתח קווי נקוב U_n', unit: 'V' },
      { section: 'nameplate', key: 'I_n', label: 'זרם קווי נקוב I_n', unit: 'A' },
      { section: 'nameplate', key: 'f_n', label: 'תדירות', unit: 'Hz' },
      { section: 'nameplate', key: 'n_n', label: 'מהירות נקובה n_n', unit: 'rpm' },
      {
        section: 'nameplate',
        key: 'poles',
        label: 'מספר קטבים',
        unit: '',
        choices: [2, 4, 6, 8, 10, 12].map((n) => ({ value: String(n), label: `${n} (n_s = ${(6000 / n).toFixed(0)} ב-50 Hz)`, int: true })),
      },
      { section: 'nameplate', key: 'connection', label: 'חיבור הליפופים', unit: '', choices: CONN },
      { section: 'nameplate', key: 'cos_phi_n', label: 'cos φ נקוב (לא חובה)', unit: '' },
      { section: 'ecm', key: 'R1', label: 'R1 (ליפוף סטטור)', unit: 'Ω' },
      { section: 'ecm', key: 'X1', label: 'X1 פיזור סטטור', unit: 'Ω' },
      { section: 'ecm', key: 'R2p', label: "R2' רוטור מוחזר", unit: 'Ω' },
      { section: 'ecm', key: 'X2p', label: "X2' פיזור רוטור מוחזר", unit: 'Ω' },
      { section: 'ecm', key: 'R_fe', label: 'R_Fe הפסדי ברזל', unit: 'Ω' },
      { section: 'ecm', key: 'Xm', label: 'X_m היגב מגנוט', unit: 'Ω' },
      { section: 'ecm', key: 'P_fw_n', label: 'הפסדי חיכוך ואוורור ב-n_n', unit: 'W' },
      { section: 'insulation', key: 'U_frame_Mohm', label: 'ליפוף U – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'V_frame_Mohm', label: 'ליפוף V – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'W_frame_Mohm', label: 'ליפוף W – מארז', unit: 'MΩ' },
    ],
    derived: [
      { key: 'n_sync', label: 'מהירות סינכרונית n_s', unit: 'rpm' },
      { key: 'slip_n', label: 'החלקה נקובה s_n', unit: '', digits: 4 },
      { key: 'M_n', label: 'מומנט נקוב M_n = 9.55·P_n/n_n', unit: 'N·m' },
      { key: 'U_winding', label: 'מתח על ליפוף', unit: 'V' },
      { key: 'I_winding', label: 'זרם בליפוף', unit: 'A' },
    ],
    modelNote:
      "מודל: מעגל תמורה T לכל ליפוף עם ענף רוטור R2'/s + jX2'. ההחלקה נקבעת מאיזון המומנטים מול הבלם על הענף היציב. ערכי ההתנגדויות הם לליפוף (בין U1 ל-U2), בלי קשר לחיבור.",
  },
}

type Draft = Record<string, string>

function toDraft(form: FormDef, s: EquipmentSpec): Draft {
  const d: Draft = {}
  for (const f of form.fields) {
    const v = (s as unknown as Record<string, Record<string, unknown>>)[f.section]?.[f.key]
    d[`${f.section}.${f.key}`] = v == null ? '' : String(v)
  }
  return d
}

function fromDraft(form: FormDef, base: EquipmentSpec, d: Draft, provenance: Provenance, note: string): EquipmentSpec | string {
  const out = structuredClone(base) as unknown as Record<Section, Record<string, unknown>> & EquipmentSpec
  for (const f of form.fields) {
    const raw = d[`${f.section}.${f.key}`] ?? ''
    if (f.choices) {
      out[f.section][f.key] = f.choices[0]?.int ? Number(raw) : raw
      continue
    }
    if (f.key === 'cos_phi_n' && raw.trim() === '') {
      out[f.section][f.key] = null
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

const SECTION_TITLE: Record<Section, 'spec.nameplate' | 'spec.ecm' | 'spec.occ' | 'spec.insulation'> = {
  nameplate: 'spec.nameplate',
  ecm: 'spec.ecm',
  occ: 'spec.occ',
  insulation: 'spec.insulation',
}

export default function SpecForm({ project }: { project: Project }) {
  const form = FORMS[project.experiment_id]
  if (!form) return <div className="alert error">אין טופס מפרט לניסוי {project.experiment_id}</div>
  return <SpecFormInner project={project} form={form} />
}

function SpecFormInner({ project, form }: { project: Project; form: FormDef }) {
  const update = useUpdateProject(project.id)
  const [draft, setDraft] = useState<Draft>(() => toDraft(form, project.spec))
  const [prov, setProv] = useState<Provenance>(project.spec.provenance)
  const [note, setNote] = useState(project.spec.provenance_note)
  const [localError, setLocalError] = useState<string | null>(null)
  const d = project.derived
  const presets = useQuery({
    queryKey: ['presets', project.experiment_id],
    queryFn: () => api.get<{ id: string; label_he: string; spec: EquipmentSpec }[]>(`/api/experiments/${project.experiment_id}/presets`),
  })
  const [presetMsg, setPresetMsg] = useState<string | null>(null)
  const loadPreset = (id: string) => {
    const p = presets.data?.find((x) => x.id === id)
    if (!p) return
    setDraft(toDraft(form, p.spec))
    setProv(p.spec.provenance)
    setNote(p.spec.provenance_note)
    setPresetMsg(`נטען: ${p.label_he}. לחץ "שמור מפרט" כדי להחיל.`)
  }

  const save = () => {
    const spec = fromDraft(form, project.spec, draft, prov, note)
    if (typeof spec === 'string') {
      setLocalError(spec)
      return
    }
    setLocalError(null)
    update.mutate({ spec })
  }

  return (
    <div className="stack" data-testid="spec-form">
      {project.spec.provenance === 'assumed' && (
        <div className="alert warn">
          {t('provenance.assumed')}. {project.spec.provenance_note}
        </div>
      )}
      <div className="row small">
        <label className="row" style={{ gap: 6 }}>
          טען ערכים מוכנים:
          <select className="input" name="preset" defaultValue="" onChange={(e) => loadPreset(e.target.value)} data-testid="preset">
            <option value="" disabled>
              בחר…
            </option>
            {presets.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label_he}
              </option>
            ))}
          </select>
        </label>
        {presetMsg && <span className="badge warn">{presetMsg}</span>}
      </div>
      <div className="grid-2">
        {(['nameplate', 'ecm', 'occ', 'insulation'] as Section[]).filter((sec) => form.fields.some((f) => f.section === sec)).map((sec) => (
          <section key={sec} className="card stack">
            <h2>{t(SECTION_TITLE[sec])}</h2>
            <div className="grid-2" style={{ gap: 10 }}>
              {form.fields.filter((f) => f.section === sec).map((f) => {
                const k = `${f.section}.${f.key}`
                const val = draft[k] ?? ''
                const optional = f.key === 'cos_phi_n' && val.trim() === ''
                const invalid = !f.choices && !optional && (val.trim() === '' || !Number.isFinite(Number(val)))
                return (
                  <label key={k} className="field">
                    {f.label} {f.unit && <span className="muted">[{f.unit}]</span>}
                    {f.choices ? (
                      <select className="input" name={k} value={val} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}>
                        {f.choices.map((c) => (
                          <option key={c.value} value={c.value}>
                            {c.label}
                          </option>
                        ))}
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
            {form.derived.map((x) => (
              <Fragment key={x.key}>
                <dt>{x.label}</dt>
                <dd className="num">
                  {fmt(d[x.key], x.digits)} {x.unit}
                </dd>
              </Fragment>
            ))}
          </dl>
          <p className="muted small">{form.modelNote}</p>
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
