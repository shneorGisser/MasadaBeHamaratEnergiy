/**
 * Rules a publication-quality schematic keeps, checked on the routed drawing:
 *
 *  A. no wire runs through a component outline or its id label;
 *  B. no two wires of different nets run along each other (one line, two potentials);
 *  C. no wire of one net ends or bends on another net's wire (reads as a junction);
 *  D. no wire passes over a terminal of another net.
 *
 * Plain crossings are allowed: they carry no junction dot, which is the drawing convention.
 */
import type { Pt, RouteInput } from './router'

export interface Finding {
  rule: 'A' | 'B' | 'C' | 'D'
  text: string
}

const E = 0.01
type Seg = [Pt, Pt]

function segs(p: Pt[]): Seg[] {
  const s: Seg[] = []
  for (let i = 1; i < p.length; i++) s.push([p[i - 1]!, p[i]!])
  return s
}
const vertical = ([a, b]: Seg) => Math.abs(a[0] - b[0]) < E
function strictlyOn(p: Pt, s: Seg): boolean {
  const [a, b] = s
  if (vertical(s)) return Math.abs(p[0] - a[0]) < E && (p[1] - a[1]) * (p[1] - b[1]) < -E
  return Math.abs(p[1] - a[1]) < E && (p[0] - a[0]) * (p[0] - b[0]) < -E
}
function overlap(s: Seg, t: Seg): number {
  if (vertical(s) !== vertical(t)) return 0
  const k = vertical(s) ? 1 : 0
  const o = vertical(s) ? 0 : 1
  if (Math.abs(s[0][o] - t[0][o]) > E) return 0
  const lo = Math.max(Math.min(s[0][k], s[1][k]), Math.min(t[0][k], t[1][k]))
  const hi = Math.min(Math.max(s[0][k], s[1][k]), Math.max(t[0][k], t[1][k]))
  return Math.max(0, hi - lo)
}

export function auditDrawing(input: RouteInput, routes: Map<string, Pt[]>, names: string[] = []): Finding[] {
  const out: Finding[] = []
  const w = input.wires.map((x) => ({ ...x, pts: routes.get(x.id) ?? [] }))
  const label = (i: number) => names[i] ?? `#${i}`
  for (const x of w) {
    for (const [a, b] of segs(x.pts)) {
      input.boxes.forEach((bx, i) => {
        const xIn = (v: number) => v > bx.x0 + 1 && v < bx.x1 - 1
        const yIn = (v: number) => v > bx.y0 + 1 && v < bx.y1 - 1
        const hit = vertical([a, b])
          ? xIn(a[0]) && Math.max(a[1], b[1]) > bx.y0 + 1 && Math.min(a[1], b[1]) < bx.y1 - 1
          : yIn(a[1]) && Math.max(a[0], b[0]) > bx.x0 + 1 && Math.min(a[0], b[0]) < bx.x1 - 1
        if (hit) out.push({ rule: 'A', text: `wire ${x.id} runs through ${label(i)}` })
      })
    }
  }
  for (let i = 0; i < w.length; i++)
    for (let j = i + 1; j < w.length; j++) {
      const p = w[i]!
      const q = w[j]!
      if (p.net === q.net) continue
      for (const s of segs(p.pts)) for (const t of segs(q.pts)) if (overlap(s, t) > 0.5) out.push({ rule: 'B', text: `wires ${p.id} and ${q.id} run along each other` })
      for (const [u, v] of [
        [p, q],
        [q, p],
      ] as const) {
        for (const pt of u.pts) for (const s of segs(v.pts)) if (strictlyOn(pt, s)) out.push({ rule: 'C', text: `wire ${u.id} ends or bends on wire ${v.id}` })
        for (const pin of [v.a, v.b]) for (const s of segs(u.pts)) if (strictlyOn(pin, s)) out.push({ rule: 'D', text: `wire ${u.id} passes over a terminal of wire ${v.id}` })
      }
    }
  return out
}
