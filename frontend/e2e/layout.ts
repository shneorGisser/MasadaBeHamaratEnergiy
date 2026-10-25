/**
 * Drawing-quality audit of an exported schematic (DXF R12 from the circuit editor): the drawing
 * the student sees, as geometry. Two rules a publication-quality schematic must keep:
 *
 *  A. no wire runs through a component outline (it reads as a connection that does not exist);
 *  B. no two wires of different nets run along each other (one line, two potentials).
 *
 * Wire crossings are allowed — they carry no junction dot, which is the drawing convention.
 */
type P = [number, number]
type Seg = [P, P]

interface Ent {
  type: string
  codes: Map<number, string[]>
}

function entities(text: string): Ent[] {
  const l = text.split(/\r?\n/)
  const out: Ent[] = []
  let cur: Ent | null = null
  let inEntities = false
  for (let i = 0; i + 1 < l.length; i += 2) {
    const code = Number(l[i]!.trim())
    const val = l[i + 1]!.trim()
    if (code === 2 && val === 'ENTITIES') inEntities = true
    if (!inEntities) continue
    if (code === 0) {
      if (val === 'ENDSEC') break
      cur = { type: val, codes: new Map() }
      out.push(cur)
    } else if (cur) cur.codes.set(code, [...(cur.codes.get(code) ?? []), val])
  }
  return out
}

const g = (e: Ent, c: number) => Number(e.codes.get(c)![0])
const layer = (e: Ent) => e.codes.get(8)![0]
const EPS = 0.05 // mm: coincidence
const close = (a: P, b: P) => Math.abs(a[0] - b[0]) < EPS && Math.abs(a[1] - b[1]) < EPS

function onSeg(p: P, [a, b]: Seg): boolean {
  if (Math.abs(a[0] - b[0]) < EPS) return Math.abs(p[0] - a[0]) < EPS && (p[1] - a[1]) * (p[1] - b[1]) <= EPS
  if (Math.abs(a[1] - b[1]) < EPS) return Math.abs(p[1] - a[1]) < EPS && (p[0] - a[0]) * (p[0] - b[0]) <= EPS
  return false
}

/** Length of the collinear overlap of two axis-parallel segments (0 if none). */
function overlap([a, b]: Seg, [c, d]: Seg): number {
  const vert = (s: P, t: P) => Math.abs(s[0] - t[0]) < EPS
  const horiz = (s: P, t: P) => Math.abs(s[1] - t[1]) < EPS
  if (vert(a, b) && vert(c, d) && Math.abs(a[0] - c[0]) < EPS) {
    const lo = Math.max(Math.min(a[1], b[1]), Math.min(c[1], d[1]))
    const hi = Math.min(Math.max(a[1], b[1]), Math.max(c[1], d[1]))
    return Math.max(0, hi - lo)
  }
  if (horiz(a, b) && horiz(c, d) && Math.abs(a[1] - c[1]) < EPS) {
    const lo = Math.max(Math.min(a[0], b[0]), Math.min(c[0], d[0]))
    const hi = Math.min(Math.max(a[0], b[0]), Math.max(c[0], d[0]))
    return Math.max(0, hi - lo)
  }
  return 0
}

export interface Violation {
  rule: 'A' | 'B'
  text: string
}

export function audit(dxf: string): Violation[] {
  const ents = entities(dxf)
  // component outlines: four COMPONENTS lines each, followed by the id text
  const boxes: { id: string; x0: number; x1: number; y0: number; y1: number }[] = []
  for (let i = 0; i < ents.length; i++) {
    const e = ents[i]!
    if (e.type !== 'LINE' || layer(e) !== 'COMPONENTS') continue
    const four = ents.slice(i, i + 4)
    const xs = four.flatMap((f) => [g(f, 10), g(f, 11)])
    const ys = four.flatMap((f) => [g(f, 20), g(f, 21)])
    const id = ents[i + 4]?.type === 'TEXT' ? ents[i + 4]!.codes.get(1)![0]! : '?'
    boxes.push({ id, x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) })
    i += 3
  }
  // wires: consecutive WIRES lines that chain end-to-start form one polyline (one cable)
  const cables: Seg[][] = []
  for (const e of ents) {
    if (e.type !== 'LINE' || layer(e) !== 'WIRES') continue
    const s: Seg = [
      [g(e, 10), g(e, 20)],
      [g(e, 11), g(e, 21)],
    ]
    const last = cables[cables.length - 1]
    if (last && close(last[last.length - 1]![1], s[0])) last.push(s)
    else cables.push([s])
  }
  const v: Violation[] = []
  const m = 0.3 // mm inside the outline
  cables.forEach((c, ci) => {
    for (const [a, b] of c) {
      if (Math.hypot(a[0] - b[0], a[1] - b[1]) < EPS) continue
      for (const bx of boxes) {
        const xIn = (x: number) => x > bx.x0 + m && x < bx.x1 - m
        const yIn = (y: number) => y > bx.y0 + m && y < bx.y1 - m
        const crosses =
          Math.abs(a[0] - b[0]) < EPS
            ? xIn(a[0]) && Math.max(a[1], b[1]) > bx.y0 + m && Math.min(a[1], b[1]) < bx.y1 - m
            : yIn(a[1]) && Math.max(a[0], b[0]) > bx.x0 + m && Math.min(a[0], b[0]) < bx.x1 - m
        if (crosses) v.push({ rule: 'A', text: `cable ${ci} runs through ${bx.id}` })
      }
    }
  })
  // nets: cables joined where an end of one touches the other (end-to-end or a T)
  const parent = cables.map((_, i) => i)
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i]!)))
  const ends = (c: Seg[]) => [c[0]![0], c[c.length - 1]![1]]
  for (let i = 0; i < cables.length; i++)
    for (let j = i + 1; j < cables.length; j++) {
      const touch =
        ends(cables[i]!).some((p) => cables[j]!.some((s) => onSeg(p, s))) ||
        ends(cables[j]!).some((p) => cables[i]!.some((s) => onSeg(p, s)))
      if (touch) parent[find(i)] = find(j)
    }
  for (let i = 0; i < cables.length; i++)
    for (let j = i + 1; j < cables.length; j++) {
      if (find(i) === find(j)) continue
      for (const s of cables[i]!)
        for (const t of cables[j]!) {
          const o = overlap(s, t)
          if (o > 0.5) v.push({ rule: 'B', text: `cables ${i} and ${j} (different nets) share ${o.toFixed(1)} mm at ${JSON.stringify(s)} / ${JSON.stringify(t)}; ${JSON.stringify(cables[i])} | ${JSON.stringify(cables[j])}` })
        }
    }
  return v
}
