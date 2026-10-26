import { describe, expect, it } from 'vitest'
import type { Column, Curve } from '../api/types'
import { axisLabel, curveSeries, curveTable } from './curves'

const cols: Column[] = [
  { key: 'f', label_he: 'תדר', unit: 'Hz' },
  { key: 'n', label_he: 'מהירות', unit: 'rpm' },
  { key: 'M', label_he: 'מומנט', unit: 'N·m' },
  { key: 'K', label_he: 'קלוס', unit: 'N·m' },
] as Column[]
const rows = [
  { f: 20, n: 500, M: 1.0, K: 1.1 },
  { f: 20, n: 550, M: 0.5, K: null },
  { f: 50, n: 1400, M: 1.2, K: 1.2 },
]

describe('curves', () => {
  it('labels an axis with its unit', () => {
    expect(axisLabel(cols, 'n')).toBe('מהירות [rpm]')
    expect(axisLabel(cols, 'nope')).toBe('nope')
  })

  it('splits a grouped curve into one coloured series per group and drops non-numeric points', () => {
    const c = { id: 'c', title_he: '', x: 'n', y: 'M', group: 'f' } as Curve
    const s = curveSeries(c, [{ label: 'סימולציה', kind: 'sim', rows }], cols)
    expect(s.map((x) => x.points.length)).toEqual([2, 1])
    expect(s[0]!.label).toContain('תדר = 20')
    expect(s[0]!.color).not.toBe(s[1]!.color)
  })

  it('draws a single y2 as a reference (theory) series, skipping missing cells', () => {
    const c = { id: 'c', title_he: '', x: 'n', y: 'M', y2: 'K' } as Curve
    const s = curveSeries(c, [{ label: 'סימולציה', kind: 'sim', rows }], cols)
    expect(s).toHaveLength(2)
    expect(s[1]!.kind).toBe('theory')
    expect(s[1]!.points).toEqual([
      [500, 1.1],
      [1400, 1.2],
    ])
  })

  it('finds the curve table by id, or the first table', () => {
    const tables = [
      { id: 'a', title_he: '', columns: [], rows: [] },
      { id: 'b', title_he: '', columns: [], rows: [] },
    ]
    expect(curveTable({ table: 'b' } as Curve, tables)!.id).toBe('b')
    expect(curveTable({} as Curve, tables)!.id).toBe('a')
  })
})
