import { useCallback } from 'react'
import { toDxf, type Geometry } from './dxf'
import type { CircuitModel, ComponentType } from './model'
import { route, routeInput, type Pt } from './router'

/**
 * The schematic as a drawing — the component outlines, every terminal and the routed cables —
 * from the circuit itself (node sizes and terminal slots are deterministic, router.ts routes
 * the cables), so the DXF is exactly the drawing on screen and needs no DOM measurement.
 */
export function circuitGeometry(c: CircuitModel, catalog: ComponentType[], routes?: Map<string, Pt[]> | null): Geometry {
  const input = routeInput(c, catalog)
  const r = routes ?? route(input)
  return {
    boxes: input.outlines.map((o) => ({ label: o.id, sub: o.type, x: o.x, y: o.y, w: o.w, h: o.h })),
    pins: input.terminals.map((t) => ({ name: t.name, x: t.p[0], y: t.p[1] })),
    wires: input.wires.map((w) => r.get(w.id) ?? [w.a, w.b]),
  }
}

export function useDxfExport() {
  return useCallback((fileName: string, c: CircuitModel, catalog: ComponentType[], routes?: Map<string, Pt[]> | null) => {
    const geo = circuitGeometry(c, catalog, routes)
    const blob = new Blob([toDxf(geo)], { type: 'application/dxf' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = fileName
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
    return geo
  }, [])
}
