/** Shared by the 3D bench: the live operating point, bench geometry and meter read-outs. */
import type { RunStatus } from '../api/types'
import { fmt } from '../format'
import type { CComponent } from '../schematic/model'

/** Live operating point returned by the solver (never a scripted animation). */
export interface LivePoint {
  status: RunStatus
  persisted: false
  source: 'simulation'
  readings?: Record<string, Record<string, number | null>>
  warnings?: { code: string; message: string }[]
  error?: { message: string }
}

export const SCALE = 0.01 // schematic units → metres on the bench
/** slider ranges of the DC-bench rheostats (field, extra armature resistance, load) */
export const RHEO_MAX: Record<string, number> = { Rf: 1000, Rx: 60, RL: 2000 }
/** machines drawn as a motor/generator coupled to a brake or drive on a common base */
export const ROTATING = new Set(['motor3', 'woundmotor3', 'syncmachine3', 'dcmachine'])
export const SIZE: Record<string, [number, number, number]> = {
  source3: [1.1, 0.7, 0.6],
  source_dc: [0.7, 0.4, 0.4],
  switch3: [0.6, 0.4, 0.5],
  transformer3: [1.2, 1.0, 0.8],
  motor3: [1.6, 0.7, 0.7],
  syncmachine3: [1.6, 0.7, 0.7],
  woundmotor3: [1.6, 0.7, 0.7],
  dcmachine: [1.6, 0.7, 0.7],
  load3: [1.0, 0.5, 0.7],
  resistor: [0.4, 0.2, 0.2],
  inductor: [0.4, 0.3, 0.3],
  capacitor: [0.3, 0.3, 0.3],
  ammeter: [0.5, 0.4, 0.3],
  voltmeter: [0.5, 0.4, 0.3],
  wattmeter: [0.6, 0.4, 0.35],
}

export function readingText(c: CComponent, live: LivePoint | null): string | null {
  const r = live?.readings?.[c.id]
  if (!r) return null
  if (c.type === 'ammeter') return `${fmt(r.I)} A`
  if (c.type === 'voltmeter') return r.U === null ? 'לא מוגדר' : `${fmt(r.U)} V`
  if (c.type === 'wattmeter') return r.P === null ? 'לא מוגדר' : `${fmt(r.P)} W · cos φ ${fmt(r.pf, 3)}`
  if (c.type === 'motor3') return `${fmt(r.n)} rpm · ${fmt(r.M, 3)} N·m`
  if (c.type === 'woundmotor3') return `${fmt(r.n)} rpm · ${fmt(r.M, 3)} N·m · f2 ${fmt(r.f_rotor, 3)} Hz`
  if (c.type === 'dcmachine') return `${fmt(r.n)} rpm · ${fmt(r.M, 3)} N·m`
  if (c.type === 'syncmachine3') return `${fmt(r.n)} rpm · ${fmt(r.f)} Hz · If ${fmt(r.If, 3)} A`
  return null
}

