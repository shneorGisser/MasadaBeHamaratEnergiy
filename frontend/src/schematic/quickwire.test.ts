import { describe, expect, it } from 'vitest'
import { findTerminal, type Terminal } from './quickwire'

const T = (component: string, terminal: string): Terminal => ({ key: `${component}.${terminal}`, component, terminal, label: component })
const all = [T('M', 'U1'), T('M', 'U2'), T('M', 'V1'), T('W', 'Ip'), T('A', 'p'), T('V1', 'p')]

describe('quick-wire terminal lookup', () => {
  it('exact component.terminal, case and spaces ignored', () => {
    expect(findTerminal(all, ' m . u2 ')).toMatchObject({ key: 'M.U2' })
  })
  it('a terminal name alone when it is unique', () => {
    expect(findTerminal(all, 'Ip')).toMatchObject({ key: 'W.Ip' })
  })
  it('an ambiguous bare name is an error that lists the candidates', () => {
    const r = findTerminal(all, 'p')
    expect('error' in r && r.error).toContain('A.p')
  })
  it('unknown and empty are errors, never a guess', () => {
    expect(findTerminal(all, 'X9')).toHaveProperty('error')
    expect(findTerminal(all, '')).toHaveProperty('error')
  })
})
