import { describe, expect, it } from 'vitest'
import { fromFlow, nets, nextId, toFlow, type CircuitModel, type ComponentType } from './model'

const catalog: ComponentType[] = [
  { type: 'ammeter', label_he: 'מד זרם', category: 'instrument', terminals: ['p', 'n'], instrument: true, params: [] },
  { type: 'resistor', label_he: 'נגד', category: 'passive', terminals: ['p', 'n'], instrument: false, params: [] },
]

const circuit: CircuitModel = {
  schema_version: 1,
  components: [
    { id: 'A', type: 'ammeter', label: '', params: {} },
    { id: 'R1', type: 'resistor', label: '', params: { R: 10 } },
  ],
  wires: [
    { id: 'w1', a: { component: 'A', terminal: 'n' }, b: { component: 'R1', terminal: 'p' } },
    { id: 'w2', a: { component: 'R1', terminal: 'p' }, b: { component: 'A', terminal: 'p' } },
  ],
  layout: { A: { x: 10, y: 20, rot: 0 } },
}

describe('schematic model', () => {
  it('round-trips CircuitModel ↔ flow without losing topology', () => {
    const { nodes, edges } = toFlow(circuit, catalog)
    const back = fromFlow(nodes, edges)
    expect(back.components).toEqual(circuit.components)
    expect(back.wires).toEqual(circuit.wires)
    expect(back.layout.A).toEqual({ x: 10, y: 20, rot: 0 })
    expect(back.layout.R1).toBeDefined()
  })

  it('computes nets from wires only', () => {
    expect(nets(circuit)).toEqual([['A.n', 'A.p', 'R1.p']])
  })

  it('generates unused ids', () => {
    expect(nextId('voltmeter', ['V1', 'V2', 'V4'])).toBe('V3')
    expect(nextId('ammeter', [])).toBe('A1')
  })
})
