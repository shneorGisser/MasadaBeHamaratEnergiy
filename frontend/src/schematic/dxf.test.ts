import { describe, expect, it } from 'vitest'
import { dxfText, junctions, pathPoints, toDxf } from './dxf'

describe('dxf', () => {
  it('writes a well-formed R12 file with the four layers and flipped y in mm', () => {
    const s = toDxf({
      boxes: [{ label: 'W', sub: '', x: 0, y: 0, w: 40, h: 20 }],
      pins: [{ name: 'Ip', x: 0, y: 10 }],
      wires: [
        [
          [0, 10],
          [-40, 10],
          [-40, 100],
        ],
      ],
    })
    const lines = s.split('\r\n')
    // group codes and values alternate; the file ends with 0 / EOF
    expect(lines.slice(-3, -1)).toEqual(['0', 'EOF'])
    expect(s).toContain('AC1009')
    for (const l of ['COMPONENTS', 'TERMINALS', 'WIRES', 'TEXT']) expect(s).toContain(`\r\n2\r\n${l}\r\n`)
    expect(s.match(/\r\n0\r\nLINE\r\n/g)).toHaveLength(4 + 2) // box sides + two wire segments
    // y = 100 px → −25 mm
    expect(s).toContain('\r\n21\r\n-25.000\r\n')
  })

  it('keeps the text ASCII', () => {
    expect(dxfText('R = 5 Ω, 30°')).toBe('R = 5 Ohm, 30%%d')
    expect(dxfText('א1')).toBe('?1')
  })

  it('reads the corners of a smooth-step path', () => {
    expect(pathPoints('M10,20L30,20Q35,20 35,25L35,60')).toEqual([
      [10, 20],
      [30, 20],
      [35, 25],
      [35, 60],
    ])
  })

  it('puts junction dots where wires meet, not on terminals or plain corners', () => {
    const g = {
      boxes: [],
      pins: [{ name: 'a', x: 0, y: 0 }],
      wires: [
        [
          [0, 0],
          [100, 0],
          [100, 50],
        ] as [number, number][],
        [
          [50, 0],
          [50, 80],
        ] as [number, number][], // ends on the first wire's run: a T
      ],
    }
    expect(junctions(g)).toEqual([[50, 0]])
  })
})
