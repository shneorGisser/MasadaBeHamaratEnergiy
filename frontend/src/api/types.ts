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
