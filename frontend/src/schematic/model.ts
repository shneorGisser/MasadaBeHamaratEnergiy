/**
 * Pure conversions between the canonical CircuitModel and the React Flow graph.
 * Connectivity lives only in wires (edges between named terminal handles).
 */
import type { Edge, Node } from '@xyflow/react'

export interface TerminalRef {
  component: string
  terminal: string
}
export interface CComponent {
  id: string
  type: string
  label: string
  params: Record<string, unknown>
}
export interface CWire {
  id: string
  a: TerminalRef
  b: TerminalRef
}
export interface Placement {
  x: number
  y: number
  rot: 0 | 90 | 180 | 270
}
export interface CircuitModel {
  schema_version: 1
  components: CComponent[]
  wires: CWire[]
  layout: Record<string, Placement>
}

export interface ParamDef {
  key: string
  label_he: string
  unit: string
  kind: 'float' | 'bool' | 'choice'
  default: unknown
  min: number | null
  max: number | null
  choices: string[]
}
export interface ComponentType {
  type: string
  label_he: string
  category: string
  terminals: string[]
  instrument: boolean
  params: ParamDef[]
}

export interface CompNodeData extends Record<string, unknown> {
  comp: CComponent
  ctype: ComponentType | undefined
  /** live reading shown on an instrument's dial (display only, never saved) */
  reading?: { value: number; unit: string; signed: boolean }
}
export type CompNode = Node<CompNodeData, 'component'>

export function toFlow(c: CircuitModel, catalog: ComponentType[]): { nodes: CompNode[]; edges: Edge[] } {
  const byType = new Map(catalog.map((t) => [t.type, t]))
  const nodes: CompNode[] = c.components.map((comp, i) => {
    const p = c.layout[comp.id] ?? { x: 160 * (i % 6), y: 160 * Math.floor(i / 6), rot: 0 }
    return {
      id: comp.id,
      type: 'component',
      position: { x: p.x, y: p.y },
      data: { comp, ctype: byType.get(comp.type) },
    }
  })
  const edges: Edge[] = c.wires.map((w) => ({
    id: w.id,
    source: w.a.component,
    sourceHandle: w.a.terminal,
    target: w.b.component,
    targetHandle: w.b.terminal,
    type: 'smoothstep',
  }))
  return { nodes, edges }
}

export function fromFlow(nodes: CompNode[], edges: Edge[]): CircuitModel {
  const layout: Record<string, Placement> = {}
  for (const n of nodes) layout[n.id] = { x: Math.round(n.position.x), y: Math.round(n.position.y), rot: 0 }
  return {
    schema_version: 1,
    components: nodes.map((n) => n.data.comp),
    wires: edges.map((e) => ({
      id: e.id,
      a: { component: e.source, terminal: e.sourceHandle ?? '' },
      b: { component: e.target, terminal: e.targetHandle ?? '' },
    })),
    layout,
  }
}

const PREFIX: Record<string, string> = {
  source3: 'G',
  source_dc: 'G',
  switch3: 'S',
  transformer3: 'T',
  motor3: 'M',
  woundmotor3: 'M',
  dcmachine: 'M',
  load3: 'L',
  resistor: 'R',
  inductor: 'Lx',
  capacitor: 'C',
  ammeter: 'A',
  voltmeter: 'V',
  wattmeter: 'W',
}

export function nextId(type: string, existing: Iterable<string>): string {
  const used = new Set(existing)
  const p = PREFIX[type] ?? 'X'
  for (let i = 1; ; i++) if (!used.has(`${p}${i}`)) return `${p}${i}`
}

export function newComponent(t: ComponentType, existing: Iterable<string>): CComponent {
  const params: Record<string, unknown> = {}
  for (const pd of t.params) params[pd.key] = pd.default
  return { id: nextId(t.type, existing), type: t.type, label: '', params }
}

/** Nets as sets of "component.terminal" keys — used to display connectivity, not to compute. */
export function nets(c: CircuitModel): string[][] {
  const parent = new Map<string, string>()
  const find = (k: string): string => {
    if (!parent.has(k)) parent.set(k, k)
    let r = k
    while (parent.get(r) !== r) r = parent.get(r)!
    parent.set(k, r)
    return r
  }
  for (const w of c.wires) {
    const a = find(`${w.a.component}.${w.a.terminal}`)
    const b = find(`${w.b.component}.${w.b.terminal}`)
    if (a !== b) parent.set(b, a)
  }
  const groups = new Map<string, string[]>()
  for (const k of parent.keys()) {
    const r = find(k)
    groups.set(r, [...(groups.get(r) ?? []), k])
  }
  return [...groups.values()].filter((g) => g.length > 1).map((g) => g.sort())
}
