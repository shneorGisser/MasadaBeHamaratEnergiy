/**
 * Orthogonal wire router for the schematic: every cable is routed around the component
 * outlines (and the id label above each), and cables of different nets are kept off each
 * other's runs, bends and ends — so a drawn line never suggests a connection that does not
 * exist. Pure function of the circuit (node sizes and terminal slots are deterministic), so the
 * screen, the DXF export and the tests all see the same drawing.
 *
 * Method: A* over a grid (10 px lanes plus every terminal's coordinates), state = (point,
 * heading). Cost = length + a bend penalty + penalties for crossing, touching or running along
 * another net. Wires are routed short-first; each routed wire is reserved for the next ones.
 * Terminals leave their node perpendicular to its side by a short stub.
 */
import { nodeSize, slotPoint, terminalSlots, titleInside } from './slots'
import type { CircuitModel, ComponentType } from './model'

export type Pt = [number, number]
type Side = 'left' | 'right' | 'top' | 'bottom'

const LANE = 10
const MARGIN = 12 // clearance from an outline
const TITLE = 20 // the id label above every node
const STUB = 16
const BEND = 30
const CROSS = 25
const TOUCH = 2000 // passing through another net's bend or end (reads as a junction)
const ALONG = 4000 // running along another net (reads as one conductor)
const NEAR = 3 // per px, running beside another net closer than one lane (hard to read)
const DIR: Record<Side, Pt> = { left: [-1, 0], right: [1, 0], top: [0, -1], bottom: [0, 1] }

interface Box {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface RouteInput {
  boxes: Box[]
  /** every terminal (connected or not), on the outline: for drawings */
  terminals: { name: string; p: Pt }[]
  /** the component outlines without the label room, with the component id and type */
  outlines: { id: string; type: string; x: number; y: number; w: number; h: number }[]
  wires: { id: string; net: number; a: Pt; b: Pt; aSide: Side; bSide: Side }[]
}

/** Geometry of a saved circuit: obstacles and the terminal points of each wire. */
export function routeInput(c: CircuitModel, catalog: ComponentType[]): RouteInput {
  const byType = new Map(catalog.map((t) => [t.type, t]))
  const pins = new Map<string, { p: Pt; side: Side }>()
  const boxes: Box[] = []
  const terminals: RouteInput['terminals'] = []
  const outlines: RouteInput['outlines'] = []
  c.components.forEach((comp, i) => {
    const pos = c.layout[comp.id] ?? { x: 160 * (i % 6), y: 160 * Math.floor(i / 6) }
    const { w, h } = nodeSize(comp.type)
    boxes.push({ x0: pos.x, y0: pos.y - (titleInside(comp.type) ? 0 : TITLE), x1: pos.x + w, y1: pos.y + h })
    outlines.push({ id: comp.id, type: comp.type, x: pos.x, y: pos.y, w, h })
    const terms = byType.get(comp.type)?.terminals ?? []
    const slots = terminalSlots(comp.type, terms, Boolean(c.layout[comp.id]?.flip))
    for (const t of terms) {
      const sl = slots[t] ?? { side: 'left' as const, at: 0.5 }
      const q = slotPoint(sl, w, h)
      pins.set(`${comp.id}.${t}`, { p: [pos.x + q.x, pos.y + q.y], side: sl.side })
      terminals.push({ name: t, p: [pos.x + q.x, pos.y + q.y] })
    }
  })
  // nets: union of wire ends
  const parent = new Map<string, string>()
  const find = (k: string): string => {
    if (!parent.has(k)) parent.set(k, k)
    const p = parent.get(k)!
    if (p === k) return k
    const r = find(p)
    parent.set(k, r)
    return r
  }
  for (const w of c.wires) parent.set(find(`${w.a.component}.${w.a.terminal}`), find(`${w.b.component}.${w.b.terminal}`))
  const netIds = new Map<string, number>()
  const wires: RouteInput['wires'] = []
  for (const w of c.wires) {
    const a = pins.get(`${w.a.component}.${w.a.terminal}`)
    const b = pins.get(`${w.b.component}.${w.b.terminal}`)
    if (!a || !b) continue
    const root = find(`${w.a.component}.${w.a.terminal}`)
    if (!netIds.has(root)) netIds.set(root, netIds.size)
    wires.push({ id: w.id, net: netIds.get(root)!, a: a.p, b: b.p, aSide: a.side, bSide: b.side })
  }
  return { boxes, wires, terminals, outlines }
}

class Heap {
  private k: number[] = []
  private v: number[] = []
  get size() {
    return this.k.length
  }
  push(key: number, val: number) {
    const k = this.k
    const v = this.v
    let i = k.length
    k.push(key)
    v.push(val)
    while (i > 0) {
      const p = (i - 1) >> 1
      if (k[p]! <= key) break
      k[i] = k[p]!
      v[i] = v[p]!
      i = p
    }
    k[i] = key
    v[i] = val
  }
  pop(): number {
    const k = this.k
    const v = this.v
    const top = v[0]!
    const lk = k.pop()!
    const lv = v.pop()!
    if (k.length) {
      let i = 0
      for (;;) {
        const l = 2 * i + 1
        if (l >= k.length) break
        const r = l + 1
        const c = r < k.length && k[r]! < k[l]! ? r : l
        if (k[c]! >= lk) break
        k[i] = k[c]!
        v[i] = v[c]!
        i = c
      }
      k[i] = lk
      v[i] = lv
    }
    return top
  }
}

export function route(input: RouteInput): Map<string, Pt[]> {
  const { boxes, wires } = input
  const out = new Map<string, Pt[]>()
  if (!wires.length) return out
  const insideAny = (x: number, y: number) =>
    boxes.some((b) => x > b.x0 - MARGIN && x < b.x1 + MARGIN && y > b.y0 - MARGIN && y < b.y1 + MARGIN)
  // a stub leaves the terminal perpendicular to its side until it is clear of every outline
  // (the id label above a node, a neighbour's margin), so the search always starts in free space
  const stubEnd = (p: Pt, side: Side): Pt => {
    const d = DIR[side]
    let len = STUB
    while (len < 120 && insideAny(p[0] + d[0] * len, p[1] + d[1] * len)) len += 2
    return [p[0] + d[0] * len, p[1] + d[1] * len]
  }
  const stubs = wires.map((w) => ({ a: stubEnd(w.a, w.aSide), b: stubEnd(w.b, w.bSide) }))
  // grid lines: lanes over the bounding area plus every stub coordinate
  const allX = [...boxes.flatMap((b) => [b.x0, b.x1]), ...stubs.flatMap((s) => [s.a[0], s.b[0]])]
  const allY = [...boxes.flatMap((b) => [b.y0, b.y1]), ...stubs.flatMap((s) => [s.a[1], s.b[1]])]
  const pad = 4 * LANE
  const lo: Pt = [Math.min(...allX) - pad, Math.min(...allY) - pad]
  const hi: Pt = [Math.max(...allX) + pad, Math.max(...allY) + pad]
  const lanes = (a: number, b: number, extra: number[]) => {
    const set = new Set<number>()
    for (let v = Math.floor(a / LANE) * LANE; v <= b; v += LANE) set.add(v)
    for (const e of extra) set.add(e)
    return [...set].sort((p, q) => p - q)
  }
  const xs = lanes(lo[0], hi[0], stubs.flatMap((s) => [s.a[0], s.b[0]]))
  const ys = lanes(lo[1], hi[1], stubs.flatMap((s) => [s.a[1], s.b[1]]))
  const nx = xs.length
  const ny = ys.length
  const idx = (i: number, j: number) => j * nx + i
  const blocked = new Uint8Array(nx * ny)
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) blocked[idx(i, j)] = insideAny(xs[i]!, ys[j]!) ? 1 : 0
  const find = (arr: number[], v: number) => {
    const r = v
    let best = 0
    for (let k = 1; k < arr.length; k++) if (Math.abs(arr[k]! - r) < Math.abs(arr[best]! - r)) best = k
    return best
  }
  // occupancy: per grid edge (h/v) and per grid point, the net using it (−1 free, −2 several)
  const hEdge = new Int32Array(nx * ny).fill(-1) // edge from (i,j) to (i+1,j)
  const vEdge = new Int32Array(nx * ny).fill(-1) // edge from (i,j) to (i,j+1)
  const pointNet = new Int32Array(nx * ny).fill(-1) // a bend or an end of a wire
  const passNet = new Int32Array(nx * ny).fill(-1) // straight pass-through
  const mark = (arr: Int32Array, k: number, net: number) => {
    arr[k] = arr[k] === -1 || arr[k] === net ? net : -2
  }
  // terminals and stubs are reserved for their net from the start
  wires.forEach((w, n) => {
    for (const [p, s] of [
      [w.a, stubs[n]!.a],
      [w.b, stubs[n]!.b],
    ] as [Pt, Pt][]) {
      mark(pointNet, idx(find(xs, s[0]), find(ys, s[1])), w.net)
      void p
    }
  })
  const order = wires
    .map((_w, n) => ({ n, d: Math.abs(stubs[n]!.a[0] - stubs[n]!.b[0]) + Math.abs(stubs[n]!.a[1] - stubs[n]!.b[1]) }))
    .sort((p, q) => p.d - q.d)

  for (const { n } of order) {
    const w = wires[n]!
    const s = stubs[n]!
    const direct = facing(w, boxes)
    if (direct) {
      out.set(w.id, direct)
      continue
    }
    const si = find(xs, s.a[0])
    const sj = find(ys, s.a[1])
    const ti = find(xs, s.b[0])
    const tj = find(ys, s.b[1])
    const start = idx(si, sj)
    const goal = idx(ti, tj)
    const N = nx * ny * 4
    const g = new Float64Array(N).fill(Infinity)
    const from = new Int32Array(N).fill(-1)
    const heap = new Heap()
    const h = (k: number) => Math.abs(xs[k % nx]! - xs[ti]!) + Math.abs(ys[Math.floor(k / nx)]! - ys[tj]!)
    // first heading = away from the terminal
    const d0 = ({ left: 0, right: 1, top: 2, bottom: 3 } as const)[w.aSide]
    const dGoal = ({ left: 1, right: 0, top: 3, bottom: 2 } as const)[w.bSide] // arrive moving into the stub
    g[start * 4 + d0] = 0
    heap.push(h(start), start * 4 + d0)
    const steps: [number, number][] = [
      [-1, 0],
      [1, 0],
      [0, -1],
      [0, 1],
    ]
    let found = -1
    while (heap.size) {
      const st = heap.pop()
      const k = st >> 2
      const d = st & 3
      const gk = g[st]!
      if (k === goal) {
        found = st
        break
      }
      const i = k % nx
      const j = Math.floor(k / nx)
      for (let nd = 0; nd < 4; nd++) {
        if ((nd ^ 1) === d && nd >> 1 === d >> 1) continue // no U-turn
        const [di, dj] = steps[nd]!
        const ni = i + di
        const nj = j + dj
        if (ni < 0 || nj < 0 || ni >= nx || nj >= ny) continue
        const nk = idx(ni, nj)
        if (blocked[nk] && nk !== goal) continue
        const len = Math.abs(xs[ni]! - xs[i]!) + Math.abs(ys[nj]! - ys[j]!)
        let c = len
        const turning = nd !== d
        if (turning) c += BEND
        const ek = nd < 2 ? idx(Math.min(i, ni), j) : idx(i, Math.min(j, nj))
        const used = nd < 2 ? hEdge[ek]! : vEdge[ek]!
        if (used !== -1 && used !== w.net) c += ALONG
        // a neighbouring lane closer than LANE that carries another net
        if (nd < 2) {
          for (const nj2 of [j - 1, j + 1]) {
            if (nj2 < 0 || nj2 >= ny || Math.abs(ys[nj2]! - ys[j]!) >= LANE - 0.5) continue
            const u = hEdge[idx(Math.min(i, ni), nj2)]!
            if (u !== -1 && u !== w.net) c += NEAR * len
          }
        } else {
          for (const ni2 of [i - 1, i + 1]) {
            if (ni2 < 0 || ni2 >= nx || Math.abs(xs[ni2]! - xs[i]!) >= LANE - 0.5) continue
            const u = vEdge[idx(ni2, Math.min(j, nj))]!
            if (u !== -1 && u !== w.net) c += NEAR * len
          }
        }
        // the point we leave from: bending on another net's line, or crossing it
        const pn = pointNet[nk]!
        if (pn !== -1 && pn !== w.net && nk !== goal) c += TOUCH
        const pp = passNet[nk]!
        if (pp !== -1 && pp !== w.net) c += CROSS
        if (turning && passNet[k] !== -1 && passNet[k] !== w.net) c += TOUCH // a bend on another run
        let arriveDir = nd
        if (nk === goal && nd !== dGoal) c += BEND
        if (nk === goal) arriveDir = nd
        const ns = nk * 4 + arriveDir
        const ng = gk + c
        if (ng < g[ns]!) {
          g[ns] = ng
          from[ns] = st
          heap.push(ng + h(nk), ns)
        }
      }
    }
    let pts: Pt[]
    if (found < 0) {
      pts = [s.a, [s.b[0], s.a[1]], s.b] // no route (should not happen): an L, flagged by the audit
    } else {
      const chain: number[] = []
      for (let st = found; st !== -1; st = from[st]!) chain.push(st)
      chain.reverse()
      pts = chain.map((st) => {
        const k = st >> 2
        return [xs[k % nx]!, ys[Math.floor(k / nx)]!] as Pt
      })
      // reserve: edges, bends/ends, pass-throughs
      for (let q = 1; q < chain.length; q++) {
        const a = chain[q - 1]! >> 2
        const b = chain[q]! >> 2
        const ai = a % nx
        const aj = Math.floor(a / nx)
        const bi = b % nx
        const bj = Math.floor(b / nx)
        if (aj === bj) mark(hEdge, idx(Math.min(ai, bi), aj), w.net)
        else mark(vEdge, idx(ai, Math.min(aj, bj)), w.net)
      }
      for (let q = 0; q < chain.length; q++) {
        const k = chain[q]! >> 2
        const bend = q === 0 || q === chain.length - 1 || (chain[q]! & 3) !== (chain[q + 1]! & 3)
        mark(bend ? pointNet : passNet, k, w.net)
      }
    }
    out.set(w.id, simplify([w.a, ...pts, w.b]))
  }
  return out
}

/**
 * Two terminals that face each other across a narrow gap (a meter beside a meter) are joined
 * straight across — a Z with its jog in the middle of the gap — when nothing lies between.
 */
function facing(w: RouteInput['wires'][number], boxes: Box[]): Pt[] | null {
  const [a, b] = [w.a, w.b]
  const horizontal =
    (w.aSide === 'right' && w.bSide === 'left' && b[0] > a[0]) || (w.aSide === 'left' && w.bSide === 'right' && a[0] > b[0])
  const vertical =
    (w.aSide === 'bottom' && w.bSide === 'top' && b[1] > a[1]) || (w.aSide === 'top' && w.bSide === 'bottom' && a[1] > b[1])
  if (horizontal && Math.abs(b[0] - a[0]) <= 2 * STUB + 8) {
    const m = (a[0] + b[0]) / 2
    const lo = Math.min(a[1], b[1])
    const hi = Math.max(a[1], b[1])
    const clear = !boxes.some((q) => m > q.x0 && m < q.x1 && hi > q.y0 && lo < q.y1)
    return clear ? simplify([a, [m, a[1]], [m, b[1]], b]) : null
  }
  if (vertical && Math.abs(b[1] - a[1]) <= 2 * STUB + 8) {
    const m = (a[1] + b[1]) / 2
    const lo = Math.min(a[0], b[0])
    const hi = Math.max(a[0], b[0])
    const clear = !boxes.some((q) => m > q.y0 && m < q.y1 && hi > q.x0 && lo < q.x1)
    return clear ? simplify([a, [a[0], m], [b[0], m], b]) : null
  }
  return null
}

/** Drop repeated and collinear points. */
export function simplify(p: Pt[]): Pt[] {
  const q: Pt[] = []
  for (const x of p) {
    const last = q[q.length - 1]
    if (last && Math.abs(last[0] - x[0]) < 1e-6 && Math.abs(last[1] - x[1]) < 1e-6) continue
    q.push(x)
  }
  const r: Pt[] = []
  for (const x of q) {
    while (r.length >= 2) {
      const a = r[r.length - 2]!
      const b = r[r.length - 1]!
      const col = (Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(b[0] - x[0]) < 1e-6) || (Math.abs(a[1] - b[1]) < 1e-6 && Math.abs(b[1] - x[1]) < 1e-6)
      if (!col) break
      r.pop()
    }
    r.push(x)
  }
  return r
}
