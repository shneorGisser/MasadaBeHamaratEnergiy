import type { Column, Curve, ResultTable } from '../api/types'
import type { Series } from './Chart'

/** Distinguishable hues for grouped series (e.g. one per inverter frequency). */
const GROUP_COLORS = ['#1f6fb2', '#b07a1f', '#4b6b2f', '#7a3e8f', '#a2462e', '#2f7f7a']

type Rows = Record<string, unknown>[]

function points(rows: Rows, x: string, y: string): [number, number][] {
  return rows
    .map((r) => [r[x], r[y]] as [unknown, unknown])
    .filter((p): p is [number, number] => typeof p[0] === 'number' && typeof p[1] === 'number')
}

/** Rows split by the value of `group` (or one group with every row). */
function groups(rows: Rows, group: string | undefined): { key: string; rows: Rows }[] {
  if (!group) return [{ key: '', rows }]
  const m = new Map<string, Rows>()
  for (const r of rows) {
    const k = typeof r[group] === 'number' ? String(r[group]) : '—'
    m.set(k, [...(m.get(k) ?? []), r])
  }
  return [...m.entries()].map(([key, rs]) => ({ key, rows: rs }))
}

export function curveTable(c: Curve, tables: ResultTable[]): ResultTable | undefined {
  return c.table ? tables.find((t) => t.id === c.table) : tables[0]
}

export function axisLabel(cols: Column[], key: string): string {
  const col = cols.find((k) => k.key === key)
  return `${col?.label_he ?? key}${col?.unit ? ` [${col.unit}]` : ''}`
}

/**
 * Series for one curve. `sources` are the row sets to draw (simulation, measurement, …), each
 * with its own visual kind; grouped curves get one series per group and source.
 */
export function curveSeries(c: Curve, sources: { label: string; kind: Series['kind']; rows: Rows }[], cols: Column[]): Series[] {
  const out: Series[] = []
  const groupLabel = (k: string) => (c.group ? ` · ${axisLabel(cols, c.group).replace(/ \[.*\]$/, '')} = ${k}` : '')
  for (const src of sources) {
    groups(src.rows, c.group).forEach((g, i) => {
      out.push({
        label: `${src.label}${groupLabel(g.key)}`,
        kind: src.kind,
        points: points(g.rows, c.x, c.y),
        color: c.group ? GROUP_COLORS[i % GROUP_COLORS.length] : undefined,
      })
    })
    if (c.y2 && src.kind === 'sim') {
      out.push({ label: axisLabel(cols, c.y2).replace(/ \[.*\]$/, ''), kind: 'theory', points: points(src.rows, c.x, c.y2) })
    }
  }
  return out
}
