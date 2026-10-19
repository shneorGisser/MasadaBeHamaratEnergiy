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

export interface Experiment {
  id: string
  version: number
  title_he: string
  summary_he: string
  manual_ref: string
}

export interface Project {
  id: string
  name: string
  experiment_id: string
  experiment_version: number
  transformer: TransformerSpec
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
    transformer: TransformerSpec
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
