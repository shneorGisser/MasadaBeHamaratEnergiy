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
    case 'motor3':
      // Terminal-board convention: winding starts U1/V1/W1 face the supply, ends U2/V2/W2 on
      // the bottom edge where the star (or delta bridges) is made.
      spread(['U1', 'V1', 'W1'], 'left', s)
      ;(['U2', 'V2', 'W2'] as const).forEach((t, i) => (s[t] = { side: 'bottom', at: 0.25 + 0.25 * i }))
      break
    case 'woundmotor3':
      // stator like the cage motor; the slip rings on the right (to the starter)
      spread(['U1', 'V1', 'W1'], 'left', s)
      ;(['U2', 'V2', 'W2'] as const).forEach((t, i) => (s[t] = { side: 'bottom', at: 0.25 + 0.25 * i }))
      spread(['R1', 'R2', 'R3'], 'right', s)
      break
    case 'syncmachine3':
      // stator starts toward the external circuit, winding ends (star) below, field on top
      spread(['U1', 'V1', 'W1'], 'left', s)
      ;(['U2', 'V2', 'W2'] as const).forEach((t, i) => (s[t] = { side: 'bottom', at: 0.25 + 0.25 * i }))
      spread(['F1', 'F2'], 'top', s)
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
