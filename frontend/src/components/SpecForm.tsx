import { useQuery } from '@tanstack/react-query'
import { Fragment, useState } from 'react'
import { api } from '../api/client'
import { useUpdateProject } from '../api/hooks'
import type { EquipmentSpec, Project, Provenance } from '../api/types'
import { fmt } from '../format'
import { t, type MessageKey } from '../i18n'
import { ErrorBox } from './ErrorBox'

type Section =
  | 'nameplate'
  | 'ecm'
  | 'occ'
  | 'network'
  | 'mcb'
  | 'rcd'
  | 'insulation'
  | 'earth'
  | 'grid'
  | 'trafo'
  | 'cable1'
  | 'cable2'
  | 'loads'
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

const DC_FORM: FormDef = {
  fields: [
    { section: 'nameplate', key: 'P_n', label: 'הספק נקוב P_n', unit: 'W' },
    { section: 'nameplate', key: 'U_n', label: 'מתח עוגן נקוב U_n', unit: 'V' },
    { section: 'nameplate', key: 'I_n', label: 'זרם עוגן נקוב I_n', unit: 'A' },
    { section: 'nameplate', key: 'n_n', label: 'מהירות נקובה n_n', unit: 'rpm' },
    { section: 'nameplate', key: 'If_n', label: 'זרם עירור נקוב (שלט)', unit: 'A' },
    { section: 'nameplate', key: 'n_max', label: 'מהירות מרבית מותרת', unit: 'rpm' },
    { section: 'ecm', key: 'R_a', label: 'R_a התנגדות מעגל העוגן', unit: 'Ω' },
    { section: 'ecm', key: 'R_f', label: 'R_f ליפוף עירור מקבילי', unit: 'Ω' },
    { section: 'ecm', key: 'R_s', label: 'R_s ליפוף עירור טורי', unit: 'Ω' },
    { section: 'ecm', key: 'U_brush', label: 'מפל מברשות (שתי מברשות)', unit: 'V' },
    { section: 'ecm', key: 'rho_s', label: 'ρ_s יחס כריכות טורי/מקבילי', unit: '' },
    { section: 'ecm', key: 'k_ar', label: 'k_ar תגובת עוגן [A עירור / A עוגן]', unit: '' },
    { section: 'ecm', key: 'P_rot_n', label: 'הפסדי סיבוב ב-n_n', unit: 'W' },
    { section: 'ecm', key: 'k_rot', label: 'מעריך P_rot ∝ n^k (1 = מומנט חיכוך קבוע)', unit: '' },
    { section: 'occ', key: 'n_ref', label: 'מהירות ייחוס לאופיין הריקם', unit: 'rpm' },
    { section: 'occ', key: 'a', label: 'שיפוע קו הפער a', unit: 'V/A' },
    { section: 'occ', key: 'I_s', label: 'ברך הרוויה I_s', unit: 'A' },
    { section: 'occ', key: 'm', label: 'חדות הברך m', unit: '' },
    { section: 'occ', key: 'F_res', label: 'שטף שיורי כהיסט בעירור F_res', unit: 'A' },
    { section: 'occ', key: 'F_h', label: 'היסטרזיס: היסט מרבי של ענף הירידה F_h (0 = ללא)', unit: 'A' },
    { section: 'insulation', key: 'armature_Mohm', label: 'עוגן – גוף', unit: 'MΩ' },
    { section: 'insulation', key: 'shunt_Mohm', label: 'עירור מקבילי – גוף', unit: 'MΩ' },
    { section: 'insulation', key: 'series_Mohm', label: 'עירור טורי – גוף', unit: 'MΩ' },
  ],
  derived: [
    { key: 'M_n', label: 'מומנט נקוב', unit: 'N·m', digits: 3 },
    { key: 'k_phi_n', label: 'k·Φ בזרם העירור הנקוב', unit: 'V·s', digits: 4 },
    { key: 'If_at_Un', label: 'זרם עירור ב-U_n ללא ריאוסטט', unit: 'A', digits: 3 },
    { key: 'M_fric', label: 'מומנט חיכוך ב-n_n', unit: 'N·m', digits: 3 },
  ],
  modelNote:
    'מודל: E = (n/n_ref)·OCC(F), F = I_f + ρ_s·I_s − k_ar·|I_a| + F_res; מתח ההדקים U = E − I_a·R_a − ΔU_brush. מחולל מקבילי נבנה מהשטף השיורי, ולכן חיבור הפוך של העירור או התנגדות מעל הקריטית מונעים בנייה. אין היסטרזיס.',
}

const CURVES = ['B', 'C', 'D'].map((c) => ({ value: c, label: `אופיין ${c}` }))

const INSTALL_FORM: FormDef = {
  fields: [
    { section: 'network', key: 'U0', label: 'מתח פאזה נקוב U0', unit: 'V' },
    { section: 'network', key: 'U1', label: 'U L1-N בפועל', unit: 'V' },
    { section: 'network', key: 'U2', label: 'U L2-N בפועל', unit: 'V' },
    { section: 'network', key: 'U3', label: 'U L3-N בפועל', unit: 'V' },
    { section: 'network', key: 'Z_L', label: 'Z_L מוליך פאזה + מקור (לפאזה)', unit: 'Ω' },
    { section: 'network', key: 'Z_N', label: 'Z_N מוליך האפס', unit: 'Ω' },
    { section: 'network', key: 'Z_PE', label: 'Z_PE מסלול מוליך ההגנה', unit: 'Ω' },
    { section: 'network', key: 'In_prot', label: 'זרם נקוב של המא״ז המגן', unit: 'A' },
    { section: 'network', key: 'curve_prot', label: 'אופיין המא״ז המגן', unit: '', choices: CURVES },
    { section: 'network', key: 't_disc', label: 'זמן ניתוק נדרש (תקנה 22)', unit: 's' },
    { section: 'mcb', key: 'curve', label: 'אופיין המא״זים הנבדקים', unit: '', choices: CURVES },
    { section: 'mcb', key: 'tau', label: 'τ קבוע זמן תרמי', unit: 's' },
    { section: 'mcb', key: 'k_t', label: 'k_t סף תרמי (1.13–1.45)', unit: '×In' },
    { section: 'mcb', key: 'k_m', label: 'k_m סף מגנטי', unit: '×In' },
    { section: 'mcb', key: 't_mag', label: 'זמן שחרור מגנטי', unit: 's' },
    { section: 'rcd', key: 'I_dn', label: 'IΔn זרם דלף נקוב', unit: 'A' },
    { section: 'rcd', key: 'k_trip', label: 'זרם ניתוק בפועל (חלק מ-IΔn)', unit: '' },
    { section: 'rcd', key: 't0', label: 'זמן המנגנון', unit: 's' },
    { section: 'rcd', key: 't1', label: 'תוספת זמן בסף הניתוק', unit: 's' },
    { section: 'rcd', key: 't_delay', label: 'השהיה (סוג S; 0 = רגיל)', unit: 's' },
    { section: 'rcd', key: 'R_body', label: 'התנגדות גוף האדם', unit: 'Ω' },
    { section: 'insulation', key: 'R_pf', label: 'ראשוני – ערכה (נפחית)', unit: 'MΩ' },
    { section: 'insulation', key: 'R_sf', label: 'משני – ערכה (נפחית)', unit: 'MΩ' },
    { section: 'insulation', key: 'R_ps', label: 'ראשוני – משני (נפחית)', unit: 'MΩ' },
    { section: 'insulation', key: 'R_su', label: 'התנגדות פני הבידוד (לכל זוג)', unit: 'MΩ' },
    { section: 'insulation', key: 'C_nF', label: 'קיבול הבידוד (לכל זוג)', unit: 'nF' },
    { section: 'insulation', key: 'R_s_kohm', label: 'התנגדות פנימית של המגר', unit: 'kΩ' },
    { section: 'insulation', key: 'display_max', label: 'גבול התצוגה של המגר', unit: 'MΩ' },
    { section: 'insulation', key: 'R_min', label: 'ערך מינימלי מותר', unit: 'MΩ' },
    { section: 'earth', key: 'rho', label: 'ρ התנגדות סגולית של הקרקע', unit: 'Ω·m' },
    { section: 'earth', key: 'rod_L', label: 'אורך מוט ההארקה', unit: 'm' },
    { section: 'earth', key: 'rod_d', label: 'קוטר המוט', unit: 'm' },
    { section: 'earth', key: 'U_touch_max', label: 'מתח מגע מותר', unit: 'V' },
    { section: 'earth', key: 'pe_L', label: 'אורך מוליך ההארקה', unit: 'm' },
    { section: 'earth', key: 'pe_A', label: 'חתך מוליך ההארקה', unit: 'mm²' },
    { section: 'earth', key: 'R_contact', label: 'התנגדות מגע בהדקים', unit: 'Ω' },
    { section: 'earth', key: 'R_pe_max', label: 'התנגדות רציפות מותרת', unit: 'Ω' },
  ],
  derived: [
    { key: 'Z_LPE', label: 'Z לולאת L-PE', unit: 'Ω', digits: 3 },
    { key: 'I_pf_LPE', label: 'זרם קצר צפוי L-PE', unit: 'A' },
    { key: 'Z_max', label: 'Z מרבי מותר (ניתוק מגנטי)', unit: 'Ω', digits: 3 },
    { key: 'I_5s', label: 'זרם לניתוק תרמי ב-5 s (מקור)', unit: '×In', digits: 3 },
    { key: 'R_g', label: 'התנגדות מוט ההארקה', unit: 'Ω' },
    { key: 'R_pe', label: 'התנגדות מוליך ההארקה', unit: 'Ω', digits: 4 },
  ],
  modelNote:
    'מודל: לולאות = סכום טורי של מוליכי פאזה, אפס ו-PE. מא״ז: דו-מתכת מסדר ראשון (τ, k_t) ושחרור מגנטי ב-k_m·In. מפסק פחת מנתק כש-|I_L + I_N| ≥ k_trip·IΔn. מגר: R נפחית ‖ R פנים ‖ C. הארקה: מוט בקרקע אחידה.',
}

const NETWORK_FORM: FormDef = {
  fields: [
    { section: 'grid', key: 'U_n_kV', label: 'מתח נקוב', unit: 'kV' },
    { section: 'grid', key: 'Sk_max_MVA', label: "S''k מרבי", unit: 'MVA' },
    { section: 'grid', key: 'Sk_min_MVA', label: "S''k מזערי", unit: 'MVA' },
    { section: 'grid', key: 'RX', label: 'R/X של הרשת', unit: '' },
    { section: 'grid', key: 'f', label: 'תדירות', unit: 'Hz' },
    { section: 'trafo', key: 'S_n_kVA', label: 'הספק נקוב', unit: 'kVA' },
    { section: 'trafo', key: 'U1_kV', label: 'מתח ראשוני', unit: 'kV' },
    { section: 'trafo', key: 'U2_V', label: 'מתח משני (קווי)', unit: 'V' },
    { section: 'trafo', key: 'uk', label: 'מתח קצר u_k', unit: '%' },
    { section: 'trafo', key: 'P_cu_kW', label: 'הפסדי נחושת בעומס נקוב', unit: 'kW' },
    { section: 'trafo', key: 'P_0_kW', label: 'הפסדי ריקם', unit: 'kW' },
    { section: 'trafo', key: 'i0', label: 'זרם ריקם', unit: '%' },
    { section: 'cable1', key: 'L_m', label: 'אורך', unit: 'm' },
    { section: 'cable1', key: 'r', label: "R' ב-20 °C", unit: 'Ω/km' },
    { section: 'cable1', key: 'x', label: "X'", unit: 'Ω/km' },
    { section: 'cable1', key: 'r0_r', label: "R0'/R' (סדר אפס)", unit: '' },
    { section: 'cable1', key: 'x0_x', label: "X0'/X' (סדר אפס)", unit: '' },
    { section: 'cable1', key: 'I_max', label: 'זרם מותר', unit: 'A' },
    { section: 'cable2', key: 'L_m', label: 'אורך', unit: 'm' },
    { section: 'cable2', key: 'r', label: "R' ב-20 °C", unit: 'Ω/km' },
    { section: 'cable2', key: 'x', label: "X'", unit: 'Ω/km' },
    { section: 'cable2', key: 'r0_r', label: "R0'/R' (סדר אפס)", unit: '' },
    { section: 'cable2', key: 'x0_x', label: "X0'/X' (סדר אפס)", unit: '' },
    { section: 'cable2', key: 'I_max', label: 'זרם מותר', unit: 'A' },
    { section: 'loads', key: 'P2_kW', label: 'עומס בלוח המעבדה P', unit: 'kW' },
    { section: 'loads', key: 'pf2', label: 'cos φ בלוח המעבדה', unit: '' },
    { section: 'loads', key: 'P3_kW', label: 'עומס בעמדה P', unit: 'kW' },
    { section: 'loads', key: 'pf3', label: 'cos φ בעמדה', unit: '' },
  ],
  derived: [
    { key: 'I_n_lv', label: 'זרם נקוב של השנאי (מ״נ)', unit: 'A' },
    { key: 'Z_T', label: 'עכבת השנאי (מ״נ)', unit: 'Ω', digits: 5 },
    { key: 'Ik_T', label: 'זרם קצר בהדקי השנאי (רשת אינסופית)', unit: 'kA', digits: 2 },
    { key: 'R_C1', label: 'R כבל ראשי', unit: 'Ω', digits: 4 },
    { key: 'R_C2', label: 'R כבל לעמדה', unit: 'Ω', digits: 4 },
  ],
  modelNote:
    "מודל: הזנה רדיאלית — רשת מ״ג (S''k) → שנאי Dyn → כבל ראשי → לוח המעבדה → כבל → העמדה. זרימת עומסים בהספק קבוע; קצרים לפי IEC 60909-0. כל חישוב נפתר ב-pandapower ובפותר ישיר, ומוצג ההפרש ביניהם.",
}

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
      { section: 'occ', key: 'F_h', label: 'היסטרזיס: היסט מרבי של ענף הירידה F_h (0 = ללא)', unit: 'A' },
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
  dc_motor: DC_FORM,
  dc_generator: DC_FORM,
  installation: INSTALL_FORM,
  network: NETWORK_FORM,
  wound_rotor: {
    fields: [
      { section: 'nameplate', key: 'P_n', label: 'הספק נקוב בציר P_n', unit: 'W' },
      { section: 'nameplate', key: 'U_n', label: 'מתח סטטור קווי U_n', unit: 'V' },
      { section: 'nameplate', key: 'I_n', label: 'זרם סטטור קווי I_n', unit: 'A' },
      { section: 'nameplate', key: 'f_n', label: 'תדירות', unit: 'Hz' },
      { section: 'nameplate', key: 'n_n', label: 'מהירות נקובה n_n', unit: 'rpm' },
      {
        section: 'nameplate',
        key: 'poles',
        label: 'מספר קטבים',
        unit: '',
        choices: [2, 4, 6, 8, 10, 12].map((n) => ({ value: String(n), label: `${n} (n_s = ${(6000 / n).toFixed(0)} ב-50 Hz)`, int: true })),
      },
      { section: 'nameplate', key: 'connection', label: 'חיבור הסטטור', unit: '', choices: CONN },
      { section: 'nameplate', key: 'cos_phi_n', label: 'cos φ נקוב (לא חובה)', unit: '' },
      { section: 'nameplate', key: 'U2_n', label: 'מתח רוטור נח (קווי)', unit: 'V' },
      { section: 'nameplate', key: 'I2_n', label: 'זרם רוטור נקוב', unit: 'A' },
      { section: 'ecm', key: 'R1', label: 'R1 (ליפוף סטטור)', unit: 'Ω' },
      { section: 'ecm', key: 'X1', label: 'X1 פיזור סטטור', unit: 'Ω' },
      { section: 'ecm', key: 'R2', label: 'R2 פאזת רוטור (בפועל)', unit: 'Ω' },
      { section: 'ecm', key: 'X2', label: 'X2 פיזור רוטור (בפועל, ב-f_n)', unit: 'Ω' },
      { section: 'ecm', key: 'k', label: 'k יחס כריכות סטטור/רוטור', unit: '' },
      { section: 'ecm', key: 'R_fe', label: 'R_Fe הפסדי ברזל', unit: 'Ω' },
      { section: 'ecm', key: 'Xm', label: 'X_m היגב מגנוט', unit: 'Ω' },
      { section: 'ecm', key: 'P_fw_n', label: 'חיכוך ואוורור ב-n_n', unit: 'W' },
      { section: 'insulation', key: 'U_frame_Mohm', label: 'סטטור U – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'V_frame_Mohm', label: 'סטטור V – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'W_frame_Mohm', label: 'סטטור W – מארז', unit: 'MΩ' },
      { section: 'insulation', key: 'rotor_frame_Mohm', label: 'רוטור – מארז', unit: 'MΩ' },
    ],
    derived: [
      { key: 'n_sync', label: 'מהירות סינכרונית', unit: 'rpm' },
      { key: 'slip_n', label: 'החלקה נקובה', unit: '', digits: 4 },
      { key: 'M_n', label: 'מומנט נקוב', unit: 'N·m' },
      { key: 'R2_referred', label: "R2' = k²·R2 (מוחזר לסטטור)", unit: 'Ω' },
      { key: 'X2_referred', label: "X2' = k²·X2", unit: 'Ω' },
    ],
    modelNote:
      'מודל: מעגל T לכל פאזה עם שנאי אידיאלי k בין סטטור לרוטור, טבעות R1–R3 נגישות (כוכב פנימי). ברוטור מסתובב המעגל החיצוני של הרוטור נפתר בתדר ההחלקה. רוטור נעול בזווית α: יחס מרוכב k·e^{j(p/2)α}.',
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

const SECTION_TITLE: Record<Section, MessageKey> = {
  nameplate: 'spec.nameplate',
  ecm: 'spec.ecm',
  occ: 'spec.occ',
  network: 'spec.network',
  mcb: 'spec.mcb',
  rcd: 'spec.rcd',
  insulation: 'spec.insulation',
  earth: 'spec.earth',
  grid: 'spec.grid',
  trafo: 'spec.trafo',
  cable1: 'spec.cable1',
  cable2: 'spec.cable2',
  loads: 'spec.loads',
}
const SECTIONS = Object.keys(SECTION_TITLE) as Section[]

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
        {SECTIONS.filter((sec) => form.fields.some((f) => f.section === sec)).map((sec) => (
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
