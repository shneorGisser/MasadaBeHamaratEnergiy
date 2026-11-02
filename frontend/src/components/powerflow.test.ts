import { describe, expect, it } from 'vitest'
import { balanceResidual, flowOf } from './powerflow'

describe('power balance from the solver internals', () => {
  it('sums close: P_in = P_cu1 + P_fe + P_cu2 + P_fw + P2', () => {
    const s = 0.05
    const P_ag = 300
    const f = flowOf(
      {
        'M.total': { P_cu1: 40, P_fe: 15, P_ag, P_cu2: s * P_ag },
        'M.mech': { s, P_mech: (1 - s) * P_ag, P_fw: 12, P2: (1 - s) * P_ag - 12 },
      },
      'M',
    )!
    expect(f.P_in).toBeCloseTo(355)
    expect(balanceResidual(f)).toBeCloseTo(0, 9)
  })
  it('no machine internals → no diagram', () => {
    expect(flowOf({}, 'M')).toBeNull()
    expect(flowOf(undefined, 'M')).toBeNull()
  })
})
