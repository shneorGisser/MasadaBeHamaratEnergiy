import { describe, expect, it } from 'vitest'
import fixture from './__fixtures__/templates.json'
import { circuitDiagram, wrap } from './diagram'
import type { CircuitModel, ComponentType } from './model'

const catalog = fixture.catalog as unknown as ComponentType[]
const templates = fixture.templates as unknown as { name: string; circuit: CircuitModel }[]

describe('report circuit diagram', () => {
  it.each(templates.map((t) => [t.name, t.circuit] as const))('%s: every component, terminal and cable is drawn', (_name, c) => {
    const d = circuitDiagram(c, catalog)
    const doc = new DOMParser().parseFromString(d.svg, 'image/svg+xml')
    expect(doc.querySelector('parsererror')).toBeNull()
    const texts = [...doc.querySelectorAll('text')].map((t) => t.textContent)
    for (const comp of c.components) expect(texts).toContain(comp.id)
    expect(doc.querySelectorAll('polyline').length).toBe(c.wires.length)
    expect(d.width).toBeGreaterThan(100)
  })
})

describe('wrap', () => {
  it('breaks at spaces within the width and keeps every word', () => {
    expect(wrap('מנוע השראה תלת-פזי + בלם אבקה מגנטית', 16)).toEqual(['מנוע השראה', 'תלת-פזי + בלם', 'אבקה מגנטית'])
    expect(wrap('מד זרם', 16)).toEqual(['מד זרם'])
  })
  it('drops whole words beyond the line limit, never part of one', () => {
    expect(wrap('a b c d e f g h', 3)).toEqual(['a b', 'c d', 'e f…'])
    expect(wrap('מד הספק חד-פאזי (כולל cos φ)', 8, 2)).toEqual(['מד הספק', 'חד-פאזי…'])
  })
})
