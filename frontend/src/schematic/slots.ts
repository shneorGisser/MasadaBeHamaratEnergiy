import { Position } from '@xyflow/react'

type Side = 'left' | 'right' | 'top' | 'bottom'
export interface Slot {
  side: Side
  at: number // 0..1 along the side
}

export const POS: Record<Side, Position> = {
  left: Position.Left,
  right: Position.Right,
  top: Position.Top,
  bottom: Position.Bottom,
}

function spread(list: string[], side: Side, out: Record<string, Slot>) {
  list.forEach((t, i) => (out[t] = { side, at: (i + 1) / (list.length + 1) }))
}

export function terminalSlots(type: string, terminals: string[]): Record<string, Slot> {
  const s: Record<string, Slot> = {}
  switch (type) {
    case 'transformer3':
      // Winding starts on the outer sides, winding ends on the bottom edge (star point closes
      // underneath) — the usual drawing convention; keeps line and star wiring from crossing.
      spread(['A1', 'B1', 'C1'], 'left', s)
      spread(['a1', 'b1', 'c1'], 'right', s)
      ;(['A2', 'B2', 'C2'] as const).forEach((t, i) => (s[t] = { side: 'bottom', at: 0.12 + 0.13 * i }))
      ;(['a2', 'b2', 'c2'] as const).forEach((t, i) => (s[t] = { side: 'bottom', at: 0.62 + 0.13 * i }))
      break
    case 'source3':
      spread(['L1', 'L2', 'L3'], 'right', s)
      spread(['N'], 'bottom', s)
      break
    case 'source_dc':
      spread(['P'], 'right', s)
      spread(['N'], 'bottom', s)
      break
    case 'switch3':
      spread(['i1', 'i2', 'i3'], 'left', s)
      spread(['o1', 'o2', 'o3'], 'right', s)
      break
    case 'load3':
      spread(['1', '2', '3'], 'left', s)
      break
    case 'wattmeter':
      spread(['Ip'], 'left', s)
      spread(['In'], 'right', s)
      spread(['Vp', 'Vn'], 'bottom', s)
      break
    default:
      spread(terminals.slice(0, 1), 'left', s)
      spread(terminals.slice(1), 'right', s)
  }
  return s
}
