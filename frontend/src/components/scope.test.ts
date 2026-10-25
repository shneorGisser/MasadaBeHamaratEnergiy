import { describe, expect, it } from 'vitest'
import { harmonics, stats, valueAt, type XY } from './scope'

const f0 = 50
function trace(f: (t: number) => number, t1: number, dt: number): XY {
  const out: XY = []
  for (let t = 0; t <= t1 + 1e-12; t += dt) out.push([t, f(t)])
  return out
}

describe('scope', () => {
  const A = 10
  const sine = trace((t) => A * Math.sin(2 * Math.PI * f0 * t), 0.1, 1e-4)

  it('interpolates cursor values and refuses points outside the trace', () => {
    expect(valueAt(sine, 0.005)).toBeCloseTo(A, 3)
    expect(valueAt(sine, -1)).toBeNull()
  })

  it('RMS of a sine over whole periods is A/√2, its mean 0', () => {
    const s = stats(sine, 0.0, 0.06)!
    expect(s.rms).toBeCloseTo(A / Math.SQRT2, 3)
    expect(s.mean).toBeCloseTo(0, 3)
    expect(s.pp).toBeCloseTo(2 * A, 2)
  })

  it('finds a 5 % third harmonic and its THD, on a decimated, non-uniform trace', () => {
    const y = (t: number) => A * Math.sin(2 * Math.PI * f0 * t) + 0.05 * A * Math.sin(3 * 2 * Math.PI * f0 * t + 0.7) + 2
    const fine = trace(y, 0.1, 1e-4)
    const thinned = fine.filter((_p, i) => i % 3 === 0 || i % 7 === 0) // irregular spacing
    const h = harmonics(thinned, 0.013, 0.095, f0)!
    expect(h.periods).toBe(4)
    expect(h.rms[0]!).toBeCloseTo(A / Math.SQRT2, 2)
    expect(h.rms[2]! / h.rms[0]!).toBeCloseTo(0.05, 3)
    expect(h.thd!).toBeCloseTo(0.05, 3)
    expect(h.dc).toBeCloseTo(2, 3)
  })

  it('needs at least one period', () => {
    expect(harmonics(sine, 0, 0.015, f0)).toBeNull()
  })
})
