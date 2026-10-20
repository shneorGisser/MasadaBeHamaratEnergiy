import { describe, expect, it } from 'vitest'
import { meterRange } from './meter'

describe('meterRange', () => {
  it('picks the next standard range with 5 % headroom', () => {
    expect(meterRange(0.3166)).toBe(0.5)
    expect(meterRange(0.47)).toBe(0.5)
    expect(meterRange(0.48)).toBe(0.6)
    expect(meterRange(174)).toBe(250)
    expect(meterRange(-2.2)).toBe(2.5)
    expect(meterRange(380)).toBe(500)
    expect(meterRange(0)).toBe(1)
  })
})
