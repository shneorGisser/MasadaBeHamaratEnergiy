/** Wire types mirroring the backend pydantic models. */

export type Connection = 'Y' | 'D'
export type Provenance = 'assumed' | 'nameplate' | 'measured' | 'fitted'

export interface Nameplate {
  S_n: number
  U1n: number
  U2n: number
  f_n: number
  primary: Connection
  secondary: Connection
}

export interface EquivalentCircuit {
  R1: number
  X1: number
  R2: number
  X2: number
  R_fe: number
  Xm_unsat: number
  sat_c: number
  sat_n: number
}

export interface Insulation {
  primary_core_Mohm: number
  secondary_core_Mohm: number
  primary_secondary_Mohm: number
}

export interface TransformerSpec {
  schema_version: 1
  provenance: Provenance
  provenance_note: string
  nameplate: Nameplate
  ecm: EquivalentCircuit
  insulation: Insulation
}

export interface MotorSpec {
  schema_version: 1
  provenance: Provenance
  provenance_note: string
  nameplate: {
    P_n: number
    U_n: number
    I_n: number
    f_n: number
    n_n: number
    poles: number
    connection: Connection
    cos_phi_n: number | null
  }
  ecm: { R1: number; X1: number; R2p: number; X2p: number; R_fe: number; Xm: number; P_fw_n: number }
  insulation: { U_frame_Mohm: number; V_frame_Mohm: number; W_frame_Mohm: number }
}

export interface SyncSpec {
  schema_version: 1
  provenance: Provenance
  provenance_note: string
  nameplate: {
    P_n: number
    U_n: number
    I_n: number
    f_n: number
    poles: number
    connection: Connection
    cos_phi_n: number | null
    If_n: number
  }
  ecm: { Ra: number; Xl: number; k_a: number; X2: number; X0: number; R_f: number; P_fw: number }
  occ: { a: number; I_s: number; m: number; F_res: number }
  insulation: {
    U_frame_Mohm: number
    V_frame_Mohm: number
    W_frame_Mohm: number
    F_frame_Mohm: number
    stator_rotor_Mohm: number
  }
}

export interface WoundSpec {
  schema_version: 1
  provenance: Provenance
  provenance_note: string
  nameplate: Record<string, number | string | null>
  ecm: Record<string, number>
  insulation: Record<string, number>
}

export interface DCSpec {
  schema_version: 1
  provenance: Provenance
  provenance_note: string
  nameplate: Record<string, number>
  ecm: Record<string, number>
  occ: Record<string, number>
  insulation: Record<string, number>
}

/** Experiment 8: the supply, its protective devices, a megger test object and an earth rod. */
export interface InstallSpec {
  schema_version: 1
  provenance: Provenance
  provenance_note: string
  network: Record<string, number | string>
  mcb: Record<string, number | string>
  rcd: Record<string, number>
  insulation: Record<string, number>
  earth: Record<string, number>
}

/** Equipment spec of whichever experiment the project belongs to. */
export type EquipmentSpec = TransformerSpec | MotorSpec | SyncSpec | WoundSpec | DCSpec | InstallSpec

export interface Experiment {
  id: string
  version: number
  title_he: string
  summary_he: string
  manual_ref: string
  equipment_he: string
  studies: string[]
}

export interface Project {
  id: string
  name: string
  experiment_id: string
  experiment_version: number
  spec: EquipmentSpec
  derived: Record<string, number>
  notes: string
  created_at: string
  updated_at: string
}

export type RunStatus =
  | 'success'
  | 'success_with_warnings'
  | 'invalid_input'
  | 'invalid_circuit'
  | 'solver_failure'
  | 'convergence_failure'
  | 'unsupported'
  | 'constraint_violation'

export interface Study {
  kind: string
  title_he: string
  manual_ref: string
  default_case: Record<string, unknown>
  variants: string[]
  editable_circuit: boolean
  condition_keys?: string[]
}

export interface Column {
  key: string
  label_he: string
  unit: string
}

export interface ResultTable {
  id: string
  title_he: string
  columns: Column[]
  rows: Record<string, unknown>[]
}

export interface Param {
  key: string
  label_he: string
  value: number | null
  unit: string
  formula: string
  method: 'consistent' | 'manual' | 'analytic'
  undefined_reason: string | null
  note: string
}

export interface Curve {
  id: string
  title_he: string
  x: string
  y: string
  /** optional second series from the same table (e.g. Kloss formula next to the model) */
  y2?: string
  /** optional third series from the same table */
  y3?: string
  /** table id the curve reads from (default: the first table) */
  table?: string
  /** split the points into one series per value of this column (e.g. frequency) */
  group?: string
  /** logarithmic axes (time–current characteristics) */
  log?: boolean
}

export interface RunResult {
  tables: ResultTable[]
  parameters: Param[]
  curves: Curve[]
  parameters_at?: Record<string, number>
}

export interface RunWarning {
  code: string
  message: string
  row?: number
  column?: string
}

export interface RunSummary {
  id: string
  project_id: string
  study_kind: string
  label: string
  status: RunStatus
  model_version: string
  input_hash: string
  n_warnings: number
  created_at: string
}

export interface Run extends RunSummary {
  input_snapshot: {
    spec?: EquipmentSpec
    /** runs created before the multi-experiment refactor */
    transformer?: TransformerSpec
    circuit: unknown
    case: Record<string, unknown>
    model_version: string
    study_kind: string
  }
  warnings: RunWarning[]
  error: { message: string; details?: unknown } | null
  result: RunResult | null
}

export interface Reproduction {
  identical: boolean
  input_hash_matches: boolean
  model_version_then: string
  model_version_now: string
}

export interface MSet {
  id: string
  project_id: string
  study_kind: string
  label: string
  lab_date: string
  instruments: string
  notes: string
  conditions: Record<string, string>
  n_rows: number
  created_at: string
}

export interface MColumn extends Column {
  units: string[]
}

export interface MCell {
  entry_id: string
  value: number
  entered_value: number
  entered_unit: string
  instrument_range: string
  note: string
  versions: number
}

export interface MHistory {
  id: string
  row: number
  quantity: string
  entered_value: number
  entered_unit: string
  value: number
  supersedes_id: string | null
  note: string
  created_at: string
}

export interface MSetView {
  set: MSet
  definition: {
    kind: string
    rows: 'free' | 'fixed'
    match: string
    row_labels: string[]
    condition_keys: string[]
    columns: MColumn[]
  }
  derived_columns: Column[]
  cells: Record<string, MCell>
  missing: { row: number; quantity: string }[]
  analysis: {
    rows: Record<string, unknown>[]
    parameters: Param[]
    parameters_at: Record<string, number> | null
    warnings: RunWarning[]
    summary?: { winding: string; R_avg: number; n: number }[]
  }
  history: MHistory[]
}

export interface CmpCell {
  quantity: string
  unit: string
  measured: number | null
  simulated: number | null
  abs_error: number | null
  rel_error: number | null
  undefined_reason: string | null
}

export interface Comparison {
  run_id: string
  set_id: string
  reference: 'simulation' | 'measurement'
  match_key: string
  match_tolerance: number
  pairs: {
    measured_row: number
    simulated_row: number | null
    unmatched_reason: string | null
    match_value: string | null
    cells: CmpCell[]
  }[]
  parameters: {
    key: string
    label_he: string
    unit: string
    method: string
    theory: number | null
    simulated: number | null
    measured: number | null
    abs_error: number | null
    rel_error: number | null
    undefined_reason: string | null
  }[]
  summary: {
    rows: number
    empty_rows_skipped: number
    unmatched_rows: number
    cells: number
    missing_measurements: number
    max_abs_rel_error: number | null
    median_abs_rel_error: number | null
  }
  curves: Curve[]
  simulated_rows: Record<string, unknown>[]
  measured_analysis: MSetView['analysis']
  notes: string[]
  diagnosis?: Finding[]
}

/** An automatic hypothesis about why measurement and simulation differ (never changes data). */
export interface Finding {
  code: string
  severity: 'info' | 'warn'
  message: string
  quantity?: string
  rows?: number[]
  factor?: number
  known?: string | null
}

export interface ProbeCandidate {
  id: string
  label_he: string
  status: RunStatus | 'invalid_input'
  error?: string | null
  rows?: number
  unmatched_rows?: number
  median_abs_rel_error?: number | null
  max_abs_rel_error?: number | null
}

/** A transcribed lab report that can be imported as measurement sets. */
export interface LabDataset {
  id: string
  experiment_id: string
  title_he: string
  source_he: string
  tables: { index: number; study_kind: string; label: string; n_rows: number; conditions: Record<string, unknown>; note: string }[]
}
