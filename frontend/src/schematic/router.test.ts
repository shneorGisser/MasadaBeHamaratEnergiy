import { describe, expect, it } from 'vitest'
import fixture from './__fixtures__/templates.json'
import { auditDrawing } from './drawingAudit'
import type { CircuitModel, ComponentType } from './model'
import { route, routeInput } from './router'

const catalog = fixture.catalog as unknown as ComponentType[]
const templates = fixture.templates as unknown as { name: string; circuit: CircuitModel }[]

describe('router', () => {
  it.each(templates.map((t) => [t.name, t.circuit] as const))('%s is drawn cleanly', (_name, circuit) => {
    const input = routeInput(circuit, catalog)
    const t0 = performance.now()
    const routes = route(input)
    const ms = performance.now() - t0
    expect(routes.size).toBe(input.wires.length)
    const findings = auditDrawing(input, routes, circuit.components.map((c) => c.id))
    expect(findings.map((f) => `[${f.rule}] ${f.text}`)).toEqual([])
    expect(ms).toBeLessThan(1500)
  })
})
