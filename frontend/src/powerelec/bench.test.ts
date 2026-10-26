// @vitest-environment node
/** Every converter of the bench against its textbook theory, in ngspice (eecircuit-engine).
 * The "ideal" component models are what the formulas assume, so the checks must pass. */
import { describe, expect, it } from 'vitest'
import { TOPOLOGIES, defaults, type P } from './circuits'
import { runTopology } from './run'

const cases: [string, P][] = [
  ['b2', {}],
  ['b2', { alpha: 60 }],
  ['b2', { alpha: 60, L: 500, R: 20 }],
  ['b6', {}],
  ['b6', { alpha: 45 }],
  ['b6', { alpha: 90, L: 0 }],
  ['b6', { alpha: 30, Ls: 5 }],
  ['buck', {}],
  ['buck', { R: 200, L: 50 }],
  ['boost', {}],
  ['hbridge', {}],
]

describe('power-electronics bench vs theory (ideal components)', () => {
  for (const [id, over] of cases) {
    it(`${id} ${JSON.stringify(over)}`, async () => {
      const t = TOPOLOGIES.find((x) => x.id === id)!
      const r = await runTopology(t, { ...defaults(t), ...over }, 'ideal')
      for (const c of r.checks) {
        if (c.tol === null || c.theory === null) continue
        const rel = Math.abs(c.sim - c.theory) / Math.max(Math.abs(c.theory), 1e-9)
        expect(rel, `${id} ${c.key}: sim ${c.sim} theory ${c.theory}`).toBeLessThan(c.tol)
      }
    }, 120_000)
  }
})

describe('real components: every topology completes, and the drops show', () => {
  for (const t of TOPOLOGIES) {
    it(`${t.id} real`, async () => {
      const p = defaults(t)
      const ideal = await runTopology(t, p, 'ideal')
      const real = await runTopology(t, p, 'real')
      const k = ideal.checks[0]!
      const r = real.checks.find((c) => c.key === k.key)!
      // diode drops and switch resistance only ever lower the converted voltage
      expect(Math.abs(r.sim)).toBeLessThan(Math.abs(k.sim))
      expect(Math.abs(r.sim)).toBeGreaterThan(0.75 * Math.abs(k.sim))
    }, 120_000)
  }
  it('B6C at α = 120° with R-L: finishes; with no DC source the mean voltage cannot stay positive', async () => {
    const t = TOPOLOGIES.find((x) => x.id === 'b6')!
    const r = await runTopology(t, { ...defaults(t), alpha: 120, L: 500, R: 5 }, 'ideal')
    expect(r.checks[0]!.sim).toBeLessThan(5)
  }, 120_000)
})

it('B6 with a large L: line-current THD approaches the 120°-block value 31.1 %', async () => {
  const t = TOPOLOGIES.find((x) => x.id === 'b6')!
  const r = await runTopology(t, { ...defaults(t), L: 500, R: 20 }, 'ideal')
  const thd = r.checks.find((c) => c.key === 'THD')!.sim
  expect(thd).toBeGreaterThan(28)
  expect(thd).toBeLessThan(32)
}, 120_000)
