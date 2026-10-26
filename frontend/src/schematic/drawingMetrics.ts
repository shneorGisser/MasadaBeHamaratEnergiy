/**
 * How readable a routed drawing is, beyond the hard rules of drawingAudit: the detour (routed
 * length over the straight Manhattan distance between the terminals), the bends and the
 * crossings between different nets. Used to compare template layouts and to guard them.
 */
import type { Pt, RouteInput } from './router'

export interface Metrics {
  detour: number // Σ routed length / Σ Manhattan distance of the terminals
  worstDetour: number // the worst single wire
  bends: number
  crossings: number
  length: number
}

const E = 0.01
type Seg = [Pt, Pt]

function segs(p: Pt[]): Seg[] {
  const s: Seg[] = []
  for (let i = 1; i < p.length; i++) s.push([p[i - 1]!, p[i]!])
  return s
}

function crosses([a, b]: Seg, [c, d]: Seg): boolean {
  const v1 = Math.abs(a[0] - b[0]) < E
  const v2 = Math.abs(c[0] - d[0]) < E
  if (v1 === v2) return false
  const [vs, hs] = v1 ? [[a, b], [c, d]] : [[c, d], [a, b]]
  const x = vs[0]![0]
  const y = hs[0]![1]
  const inV = (y - vs[0]![1]) * (y - vs[1]![1]) < -E
  const inH = (x - hs[0]![0]) * (x - hs[1]![0]) < -E
  return inV && inH
}

export function drawingMetrics(input: RouteInput, routes: Map<string, Pt[]>): Metrics {
  let length = 0
  let direct = 0
  let worst = 1
  let bends = 0
  const all: { net: number; s: Seg[] }[] = []
  for (const w of input.wires) {
    const p = routes.get(w.id) ?? []
    let l = 0
    for (const [a, b] of segs(p)) l += Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1])
    const d = Math.abs(w.a[0] - w.b[0]) + Math.abs(w.a[1] - w.b[1])
    length += l
    direct += d
    if (d > 40) worst = Math.max(worst, l / d)
    bends += Math.max(0, p.length - 2)
    all.push({ net: w.net, s: segs(p) })
  }
  let crossings = 0
  for (let i = 0; i < all.length; i++)
    for (let j = i + 1; j < all.length; j++) {
      if (all[i]!.net === all[j]!.net) continue
      for (const s of all[i]!.s) for (const t of all[j]!.s) if (crosses(s, t)) crossings++
    }
  return { detour: direct > 0 ? length / direct : 1, worstDetour: worst, bends, crossings, length }
}
