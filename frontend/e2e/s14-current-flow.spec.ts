import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

test('F1: current flow on the schematic matches the solver, AC and DC', async ({ page, request }) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('F1 זרימת זרם')
  await page.locator('select[name="experiment"]').selectOption('dc_motor')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-experiment')).toBeVisible()
  const pid = page.url().split('/projects/')[1]!.split(/[/?]/)[0]!

  await openTab(page, /^מנוע מקבילי בעומס$/)
  await expect(page.getByTestId('node-M')).toBeVisible()
  await page.getByTestId('show-current').check()
  await page.getByTestId('show-current-values').check()

  const ref = await (await request.post(`/api/projects/${pid}/circuits/load/operating-point`, { data: { overrides: {}, wire_currents: true } })).json()
  const currents = Object.entries(ref.wire_currents as Record<string, { I: number } | null>).filter(([, v]) => v && Math.abs(v.I) > 1e-6)
  expect(currents.length).toBeGreaterThan(3)
  const [wid, val] = currents[0]!
  await expect(page.getByTestId(`current-${wid}`)).toHaveAttribute('data-current', String(val!.I))
  // dots are drawn on the live cables
  await expect(page.getByTestId(`current-${wid}`).locator('circle[visibility="visible"]').first()).toBeAttached()
  await page.waitForTimeout(400)
  await page.getByTestId('schematic').screenshot({ path: 'test-results/f1-dc-flow.png' })

  // AC: the transformer's no-load circuit
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('F1 שנאי')
  await page.locator('select[name="experiment"]').selectOption('transformer3ph')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-experiment')).toBeVisible()
  await openTab(page, /ריקם/)
  await page.getByTestId('show-current').check()
  await page.getByTestId('show-current-values').check()
  await expect(page.locator('[data-testid^="current-"] circle[visibility="visible"]').first()).toBeAttached()
  await page.waitForTimeout(400)
  await page.getByTestId('schematic').screenshot({ path: 'test-results/f1-ac-flow.png' })
})
