import { describe, expect, it } from 'vitest'
import { fmt, parseList } from './format'

describe('fmt', () => {
  it('never renders undefined values as numbers', () => {
    expect(fmt(null)).toBe('—')
    expect(fmt(undefined)).toBe('—')
    expect(fmt(Number.NaN)).toBe('—')
  })
  it('uses significant digits', () => {
    expect(fmt(219.3931)).toBe('219.4')
    expect(fmt(0.36228)).toBe('0.3623')
    expect(fmt(0.000417)).toBe('4.170e-4')
    expect(fmt(2400)).toBe('2400')
  })
})

describe('parseList', () => {
  it('parses comma lists and rejects garbage', () => {
    expect(parseList('190, 228 ,380')).toEqual([190, 228, 380])
    expect(parseList('1;2 3')).toEqual([1, 2, 3])
    expect(parseList('1, x')).toBeNull()
    expect(parseList('  ')).toBeNull()
  })
})
