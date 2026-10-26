/**
 * Layout optimiser for the template schematics (a dev tool, not part of the test suite).
 *
 *   LAYOUT_DIR=/some/dir npx vitest run --dir tools tools/layout-optimize.test.ts
 *
 * reads $LAYOUT_DIR/opt.json — {"templates": [...names], "shared": [ids placed the same in all],
 * "fixed": [ids that stay], "iters": N} — and writes $LAYOUT_DIR/opt-out.json with the best
 * positions found by a seeded random local search (moves on a 20–160 px grid and left↔right
 * flips) minimising: audit findings ≫ box overlaps ≫ 150·crossings + 60·bends + wire length.
 * The positions are then written into the backend templates by hand and checked visually —
 * the metric is a guide, not a judge (an early weighting gave fewer crossings and a worse
 * drawing).
 */
import { it } from 'vitest'
import { readFileSync, writeFileSync } from 'node:fs'
import fixture from '../src/schematic/__fixtures__/templates.json'
import { auditDrawing } from '../src/schematic/drawingAudit'
import { drawingMetrics } from '../src/schematic/drawingMetrics'
import type { CircuitModel, ComponentType } from '../src/schematic/model'
import { route, routeInput } from '../src/schematic/router'
import { nodeSize } from '../src/schematic/slots'

const S = process.env.LAYOUT_DIR ?? '.'
const cfg = JSON.parse(readFileSync(`${S}/opt.json`, 'utf8')) as {
  templates: string[]
  shared: string[] // component ids shared by all templates (same position everywhere)
  fixed: string[]
  iters: number
}
const cat = fixture.catalog as unknown as ComponentType[]
const tpls = (fixture.templates as unknown as { name: string; circuit: CircuitModel }[]).filter((t) => cfg.templates.includes(t.name))
type V = { x: number; y: number; flip: boolean }
const fn = (t: string) => t.split('/').slice(0, 2).join('/') // variants share one template function
const key = (t: string, id: string) => (cfg.shared.includes(id) ? id : `${fn(t)}:${id}`)
const vars = new Map<string, V>()
for (const t of tpls) for (const c of t.circuit.components) {
  const l = t.circuit.layout[c.id]!
  vars.set(key(t.name, c.id), { x: l.x, y: l.y, flip: Boolean((l as { flip?: boolean }).flip) })
}
function overlap(c: CircuitModel): number {
  const bs = c.components.map((k) => {
    const l = c.layout[k.id]!
    const { w, h } = nodeSize(k.type)
    return [l.x - 30, l.y - 40, l.x + w + 30, l.y + h + 30]
  })
  let n = 0
  for (let i = 0; i < bs.length; i++) for (let j = i + 1; j < bs.length; j++) {
    const a = bs[i]!, b = bs[j]!
    if (a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]) n++
  }
  return n
}
function apply(): CircuitModel[] {
  return tpls.map((t) => {
    const layout = { ...t.circuit.layout }
    for (const c of t.circuit.components) {
      const v = vars.get(key(t.name, c.id))!
      layout[c.id] = { x: v.x, y: v.y, rot: 0, flip: v.flip } as never
    }
    return { ...t.circuit, layout }
  })
}
function cost(): number {
  let s = 0
  for (const c of apply()) {
    const inp = routeInput(c, cat)
    const r = route(inp)
    const f = auditDrawing(inp, r).length
    const m = drawingMetrics(inp, r)
    s += 1e6 * f + 1e5 * overlap(c) + 150 * m.crossings + 60 * m.bends + m.length
  }
  return s
}
it('optimise', () => {
  let best = cost()
  const start = best
  const movable = [...vars.keys()].filter((k) => !cfg.fixed.some((f) => k === f || k.endsWith(`:${f}`)))
  let seed = 7
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
  for (let it = 0; it < cfg.iters; it++) {
    const k = movable[Math.floor(rnd() * movable.length)]!
    const v = vars.get(k)!
    const old = { ...v }
    const move = rnd()
    if (move < 0.15) v.flip = !v.flip
    else {
      const step = [20, 40, 80, 160][Math.floor(rnd() * 4)]!
      v.x += (rnd() < 0.5 ? -1 : 1) * (rnd() < 0.5 ? step : 0)
      v.y += (rnd() < 0.5 ? -1 : 1) * (rnd() < 0.5 ? step : 0)
      if (v.x < -200 || v.y < -100) Object.assign(v, old)
    }
    const c = cost()
    if (c <= best) best = c
    else Object.assign(v, old)
  }
  const out = Object.fromEntries([...vars].filter(([k]) => movable.includes(k)))
  writeFileSync(`${S}/opt-out.json`, JSON.stringify({ start, best, vars: out }, null, 1))
}, 600_000)
