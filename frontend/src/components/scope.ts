/**
 * Oscilloscope measurements on a sampled trace (x = time): cursor values, statistics over a
 * window, and harmonics by Fourier correlation over an integer number of periods. Works on
 * non-uniform samples (trapezoidal integration), so a decimated trace is handled exactly as
 * sampled — no resampling, no invented points.
 */
export type XY = [number, number][]

export function valueAt(pts: XY, x: number): number | null {
  if (pts.length === 0 || x < pts[0]![0] || x > pts[pts.length - 1]![0]) return null
  let lo = 0
  let hi = pts.length - 1
  while (hi - lo > 1) {
    const m = (lo + hi) >> 1
    if (pts[m]![0] <= x) lo = m
    else hi = m
  }
  const [x0, y0] = pts[lo]!
  const [x1, y1] = pts[hi]!
  return x1 === x0 ? y0 : y0 + ((y1 - y0) * (x - x0)) / (x1 - x0)
}

/** The samples inside [a, b] with interpolated end points. */
function window(pts: XY, a: number, b: number): XY {
  const lo = Math.min(a, b)
  const hi = Math.max(a, b)
  const ya = valueAt(pts, lo)
  const yb = valueAt(pts, hi)
  if (ya === null || yb === null) return []
  return [[lo, ya], ...pts.filter((p) => p[0] > lo && p[0] < hi), [hi, yb]]
}

function integrate(w: XY, f: (x: number, y: number) => number): number {
  let s = 0
  for (let i = 1; i < w.length; i++) {
    const [x0, y0] = w[i - 1]!
    const [x1, y1] = w[i]!
    s += 0.5 * (f(x0, y0) + f(x1, y1)) * (x1 - x0)
  }
  return s
}

export interface Stats {
  mean: number
  rms: number
  min: number
  max: number
  pp: number
}

export function stats(pts: XY, a: number, b: number): Stats | null {
  const w = window(pts, a, b)
  const T = Math.abs(b - a)
  if (w.length < 2 || T <= 0) return null
  const ys = w.map((p) => p[1])
  const mean = integrate(w, (_x, y) => y) / T
  const rms = Math.sqrt(Math.max(0, integrate(w, (_x, y) => y * y) / T))
  const min = Math.min(...ys)
  const max = Math.max(...ys)
  return { mean, rms, min, max, pp: max - min }
}

export interface Harmonics {
  /** the window actually used: an integer number of periods, starting at the first cursor */
  t0: number
  t1: number
  periods: number
  dc: number
  /** RMS of harmonic n at index n−1, and its phase [deg] */
  rms: number[]
  phase: number[]
  thd: number | null
}

/**
 * Harmonics 1…nMax of f0 over the largest integer number of periods in [a, b].
 * THD = √(Σ_{n≥2} Hn²) / H1 (IEC 61000 definition, relative to the fundamental).
 * Samples must resolve the highest harmonic: n_max is cut to a quarter of the samples per period.
 */
export function harmonics(pts: XY, a: number, b: number, f0: number, nMax = 15): Harmonics | null {
  const lo = Math.min(a, b)
  const period = 1 / f0
  const periods = Math.floor((Math.abs(b - a) + 1e-12) / period)
  if (periods < 1) return null
  const t1 = lo + periods * period
  const w = window(pts, lo, t1)
  if (w.length < 8) return null
  const T = t1 - lo
  const perPeriod = (w.length - 1) / periods
  const n = Math.max(1, Math.min(nMax, Math.floor(perPeriod / 4)))
  const dc = integrate(w, (_x, y) => y) / T
  const rms: number[] = []
  const phase: number[] = []
  for (let k = 1; k <= n; k++) {
    const om = 2 * Math.PI * f0 * k
    const c = (2 / T) * integrate(w, (x, y) => y * Math.cos(om * (x - lo)))
    const s = (2 / T) * integrate(w, (x, y) => y * Math.sin(om * (x - lo)))
    rms.push(Math.hypot(c, s) / Math.SQRT2)
    phase.push((Math.atan2(c, s) * 180) / Math.PI) // y = √2·H·sin(ωt + φ)
  }
  const h1 = rms[0] ?? 0
  const thd = h1 > 1e-12 && n > 1 ? Math.sqrt(rms.slice(1).reduce((q, v) => q + v * v, 0)) / h1 : null
  return { t0: lo, t1, periods, dc, rms, phase, thd }
}
