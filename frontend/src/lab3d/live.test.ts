import { describe, expect, it } from 'vitest'
import type { CComponent } from '../schematic/model'
import { readingText, type LivePoint } from './live'

const comp = (type: string, id = 'X'): CComponent => ({ id, type, label: '', params: {} })
const live = (r: Record<string, Record<string, number | null>>): LivePoint =>
  ({ status: 'success', persisted: false, source: 'simulation', readings: r }) as LivePoint

describe('3D bench read-outs', () => {
  it('formats each instrument from the solved readings', () => {
    expect(readingText(comp('ammeter'), live({ X: { I: 1.234 } }))).toContain('A')
    expect(readingText(comp('voltmeter'), live({ X: { U: null } }))).toBe('לא מוגדר')
    expect(readingText(comp('wattmeter'), live({ X: { P: 120, pf: 0.8 } }))).toContain('cos φ')
  })
  it('shows nothing without a solution or for passive parts', () => {
    expect(readingText(comp('ammeter'), null)).toBeNull()
    expect(readingText(comp('resistor'), live({ X: { I: 1 } }))).toBeNull()
  })
})
