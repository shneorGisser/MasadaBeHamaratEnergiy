/** From an ngspice result to the bench's signals: probes, the analysis window, statistics. */
import { harmonics, stats, type XY } from '../components/scope'
import type { Signals, Topology } from './circuits'

export interface RawResult {
  variableNames: string[]
  data: { name: string; values: ArrayLike<number> }[]
}

export function probeTraces(t: Topology, r: RawResult): Record<string, XY> {
  // values may come as typed arrays: map() on those would coerce the [t, y] pairs to numbers
  const byName = new Map(r.data.map((d) => [d.name.toLowerCase(), Array.from(d.values)]))
  const time = byName.get('time')
  if (!time) throw new Error('ngspice returned no time axis')
  const vec = (n: string): number[] => {
    const v = byName.get(n.toLowerCase())
    if (!v) throw new Error(`ngspice returned no vector ${n} (have: ${[...byName.keys()].join(', ')})`)
    return v
  }
  const out: Record<string, XY> = {}
  for (const p of t.probes) {
    const ys = typeof p.expr === 'string' ? vec(p.expr) : (() => {
      const a = vec(p.expr[0])
      const b = vec(p.expr[1])
      return a.map((v, i) => v - b[i]!)
    })()
    // current probes are 0-V sources placed in the direction of flow (+ node upstream), so
    // ngspice's sign convention (positive from + to − through the source) is the flow
    out[p.key] = time.map((x, i) => [x, ys[i]!] as [number, number])
  }
  return out
}

export function signals(traces: Record<string, XY>, wanted: [number, number]): Signals {
  // ngspice's last sample can fall a rounding error short of t_stop: clamp to the data
  const any = Object.values(traces)[0] ?? []
  const last = any.length ? any[any.length - 1]![0] : wanted[1]
  const t1 = Math.min(wanted[1], last)
  const t0 = Math.min(wanted[0], t1)
  const window: [number, number] = [t0, t1]
  const cut = (k: string): XY => {
    const tr = traces[k]
    if (!tr) throw new Error(`no probe ${k}`)
    // keep one sample on each side, so the window's end points can be interpolated
    let i0 = tr.findIndex((p) => p[0] >= t0)
    if (i0 < 0) return []
    if (i0 > 0 && tr[i0]![0] > t0) i0 -= 1
    let i1 = i0
    while (i1 < tr.length - 1 && tr[i1]![0] < t1) i1 += 1
    return tr.slice(i0, i1 + 1)
  }
  const cache = new Map<string, XY>()
  const get = (k: string) => {
    if (!cache.has(k)) cache.set(k, cut(k))
    return cache.get(k)!
  }
  return {
    get,
    window,
    stats(k) {
      const s = stats(get(k), t0, t1)
      if (!s) throw new Error(`window too short for ${k}`)
      return s
    },
    harmonic(k, f0, n) {
      const h = harmonics(get(k), t0, t1, f0, Math.max(n, 15))
      return h?.rms[n - 1] ?? NaN
    },
    thd(k, f0) {
      return harmonics(get(k), t0, t1, f0, 49)?.thd ?? null
    },
  }
}

/** Keep the shape of a long trace for plotting: min and max of each bucket (≤ 2·n points). */
export function decimate(pts: XY, n = 1500): XY {
  if (pts.length <= 2 * n) return pts
  const out: XY = []
  const size = pts.length / n
  for (let b = 0; b < n; b++) {
    const lo = Math.floor(b * size)
    const hi = Math.min(pts.length, Math.floor((b + 1) * size))
    let mn = pts[lo]!
    let mx = pts[lo]!
    for (let i = lo; i < hi; i++) {
      if (pts[i]![1] < mn[1]) mn = pts[i]!
      if (pts[i]![1] > mx[1]) mx = pts[i]!
    }
    if (mn[0] <= mx[0]) out.push(mn, mx)
    else out.push(mx, mn)
  }
  return out
}
