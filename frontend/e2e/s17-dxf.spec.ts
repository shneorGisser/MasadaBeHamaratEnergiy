import { readFileSync } from 'node:fs'
import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

/** Entities of an R12 DXF as {type, codes}. */
function entities(text: string) {
  const l = text.split(/\r?\n/)
  const out: { type: string; codes: Map<number, string[]> }[] = []
  let cur: (typeof out)[number] | null = null
  let inEntities = false
  for (let i = 0; i + 1 < l.length; i += 2) {
    const code = Number(l[i]!.trim())
    const val = l[i + 1]!.trim()
    if (code === 2 && val === 'ENTITIES') inEntities = true
    if (!inEntities) continue
    if (code === 0) {
      if (val === 'ENDSEC') break
      cur = { type: val, codes: new Map() }
      out.push(cur)
    } else if (cur) cur.codes.set(code, [...(cur.codes.get(code) ?? []), val])
  }
  return out
}

test('D1: the schematic exports to DXF and every wire ends on a terminal', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('D1 DXF')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toBeVisible()
  await openTab(page, 'ניסוי עומס')
  await expect(page.getByTestId('node-T')).toBeVisible()
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId('export-dxf').click()])
  expect(download.suggestedFilename()).toBe('circuit-load.dxf')
  await download.saveAs('test-results/d1-load.dxf')
  const path = await download.path()
  const text = readFileSync(path!, 'utf8')
  const ents = entities(text)
  const pins = ents
    .filter((e) => e.type === 'CIRCLE' && e.codes.get(8)![0] === 'TERMINALS')
    .map((e) => [Number(e.codes.get(10)![0]), Number(e.codes.get(20)![0])] as const)
  const wires = ents.filter((e) => e.type === 'LINE' && e.codes.get(8)![0] === 'WIRES')
  expect(pins.length).toBeGreaterThan(10)
  expect(wires.length).toBeGreaterThan(10)
  // graph of wire endpoints: a point used by exactly one segment is a wire end → must be a pin
  const key = (x: string, y: string) => `${Number(x).toFixed(2)},${Number(y).toFixed(2)}`
  const deg = new Map<string, number>()
  for (const w of wires) {
    for (const k of [key(w.codes.get(10)![0]!, w.codes.get(20)![0]!), key(w.codes.get(11)![0]!, w.codes.get(21)![0]!)])
      deg.set(k, (deg.get(k) ?? 0) + 1)
  }
  const pinKeys = new Set(pins.map(([x, y]) => key(String(x), String(y))))
  const ends = [...deg].filter(([, d]) => d === 1).map(([k]) => k)
  expect(ends.length).toBeGreaterThan(0)
  expect(ends.filter((k) => !pinKeys.has(k))).toEqual([])
  expect(text).toContain('AC1009')
})
