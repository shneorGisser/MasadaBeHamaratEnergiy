import { describe, expect, it } from 'vitest'
import { substitute } from './substitute'

describe('formula substitution', () => {
  it('replaces whole symbols, longest first', () => {
    expect(substitute('100·U_k(I_n) / U_1n', { U_k: 20, 'U_k(I_n)': 20.27, U_1n: 380 })).toBe('100·20.27 / 380.0')
    expect(substitute('P0 / (√3·U_L·I0)', { P0: 60, U_L: 380, I0: 0.36 })).toBe('60.00 / (√3·380.0·0.3600)')
  })
  it('does not touch a symbol inside a longer name', () => {
    expect(substitute('√(Y_m² − g_m²)', { Y_m: 0.001641, g_m: 0.0004155 })).toBe('√(0.001641² − (4.155e-4)²)')
    expect(substitute('Y0 + Y01', { Y0: 2 })).toBe('2.000 + Y01')
  })
  it('wraps negative values', () => {
    expect(substitute('3·x²', { x: -2 })).toBe('3·(-2.000)²')
  })
  it('nothing recorded → null', () => {
    expect(substitute('a / b', {})).toBeNull()
    expect(substitute('a / b', undefined)).toBeNull()
    expect(substitute('a / b', { c: 1 })).toBeNull()
  })
})
