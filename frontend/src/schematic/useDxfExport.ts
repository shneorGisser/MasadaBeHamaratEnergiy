import { getSmoothStepPath, Position, useReactFlow } from '@xyflow/react'
import { useCallback } from 'react'
import { pathPoints, toDxf, type Geometry } from './dxf'
import type { CompNode } from './model'

/** Where React Flow attaches an edge to a handle: the middle of the handle's outer side. */
function anchor(h: { x: number; y: number; width: number; height: number; position: Position }, ox: number, oy: number) {
  const x = ox + h.x
  const y = oy + h.y
  switch (h.position) {
    case Position.Left:
      return { x, y: y + h.height / 2 }
    case Position.Right:
      return { x: x + h.width, y: y + h.height / 2 }
    case Position.Top:
      return { x: x + h.width / 2, y }
    default:
      return { x: x + h.width / 2, y: y + h.height }
  }
}

/**
 * The schematic as drawn — measured node boxes, the handles' real positions and the same
 * smooth-step routing as on screen (with square corners) — written as an R12 DXF file.
 */
export function useDxfExport() {
  const rf = useReactFlow()
  return useCallback(
    (fileName: string) => {
      const geo: Geometry = { boxes: [], pins: [], wires: [] }
      const handles = new Map<string, { x: number; y: number; position: Position }>()
      for (const n of rf.getNodes() as CompNode[]) {
        const inode = rf.getInternalNode(n.id)
        if (!inode) continue
        const { x: ox, y: oy } = inode.internals.positionAbsolute
        const w = inode.measured.width ?? 0
        const h = inode.measured.height ?? 0
        geo.boxes.push({ label: n.data.comp.id, sub: n.data.comp.type, x: ox, y: oy, w, h })
        const hb = inode.internals.handleBounds
        for (const b of [...(hb?.source ?? []), ...(hb?.target ?? [])]) {
          if (!b.id || handles.has(`${n.id}.${b.id}`)) continue
          const p = anchor(b, ox, oy)
          handles.set(`${n.id}.${b.id}`, { ...p, position: b.position })
          geo.pins.push({ name: b.id, ...p })
        }
      }
      for (const e of rf.getEdges()) {
        const s = handles.get(`${e.source}.${e.sourceHandle}`)
        const t = handles.get(`${e.target}.${e.targetHandle}`)
        if (!s || !t) continue
        const [d] = getSmoothStepPath({
          sourceX: s.x,
          sourceY: s.y,
          sourcePosition: s.position,
          targetX: t.x,
          targetY: t.y,
          targetPosition: t.position,
          borderRadius: 0,
        })
        geo.wires.push(pathPoints(d))
      }
      const blob = new Blob([toDxf(geo)], { type: 'application/dxf' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = fileName
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(a.href), 1000)
      return geo
    },
    [rf],
  )
}
