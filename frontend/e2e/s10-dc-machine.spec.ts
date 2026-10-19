import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

async function newProject(page: import('@playwright/test').Page, name: string, exp: string): Promise<string> {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill(name)
  await page.locator('select[name="experiment"]').selectOption(exp)
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-experiment')).toContainText('זרם ישר')
  return page.url().split('/projects/')[1]!.split(/[/?]/)[0]!
}

test('D5: DC motor — load table, brake on the 3D bench, compound connection', async ({ page, request }) => {
  const pid = await newProject(page, 'D5 מנוע DC', 'dc_motor')

  await openTab(page, /^מנוע מקבילי בעומס$/)
  await expect(page.getByTestId('node-M')).toBeVisible()
  await page.screenshot({ path: 'test-results/d5-load-schematic.png', fullPage: true })
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', /success/)
  const t24 = view.getByRole('table', { name: /טבלה 2.4/ })
  await expect(t24.locator('tbody tr')).toHaveCount(6)

  // the brake slider on the 3D bench moves the speed exactly as the solver says
  await page.getByTestId('lab3d-section').locator('summary').click()
  await expect(page.getByTestId('lab3d').locator('canvas')).toBeVisible()
  await page.getByTestId('brake').focus()
  for (let i = 0; i < 50; i++) await page.keyboard.press('ArrowUp') // 0 → 0.50 N·m
  await expect(page.getByTestId('brake-value')).toHaveText('0.500 N·m')
  const ref = await (
    await request.post(`/api/projects/${pid}/circuits/load/operating-point`, { data: { overrides: { M: { M_load: 0.5 } } } })
  ).json()
  await expect(page.getByTestId('reading-M')).toContainText(`${Math.round(ref.readings.M.n)} rpm`)
  await page.screenshot({ path: 'test-results/d5-3d.png' })

  // compound: the series-field selector exists and the run succeeds
  await openTab(page, 'מנוע בעירור מעורב')
  await expect(page.locator('select[name="case-series"]')).toHaveValue('cumulative')
  await page.screenshot({ path: 'test-results/d5-compound-schematic.png', fullPage: true })
  await page.getByTestId('run-button').click()
  await expect(view.getByRole('table', { name: /טבלה 2.8/ })).toBeVisible()
})

test('D6: DC generator — shunt build-up to 220 V, compound polarities, spec form', async ({ page }) => {
  await newProject(page, 'D6 מחולל DC', 'dc_generator')

  await openTab(page, 'אופיין ריקם בעירור זר')
  await page.screenshot({ path: 'test-results/d6-occ-schematic.png', fullPage: true })
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-warnings')).toContainText('היסטרזיס')

  await openTab(page, 'אופיין חיצוני בעירור מקבילי')
  await page.getByTestId('run-button').click()
  const t26 = view.getByRole('table', { name: /טבלה 2.6/ })
  await expect(t26.locator('tbody tr').first()).toContainText('220.0')

  await openTab(page, /עירור מעורב/)
  await page.getByTestId('run-button').click()
  await expect(view.getByRole('table', { name: /טבלה 2.7/ })).toContainText('S2-S1')
  await page.screenshot({ path: 'test-results/d6-compound.png', fullPage: true })

  await openTab(page, /בזרם עומס קבוע/)
  await page.screenshot({ path: 'test-results/d6-regulation-schematic.png', fullPage: true })

  await openTab(page, 'מחולל במקביל לרשת DC')
  await page.screenshot({ path: 'test-results/d6-grid-schematic.png', fullPage: true })

  await page.getByRole('link', { name: 'מפרט המכונה' }).click()
  await expect(page.locator('input[name="ecm.R_f"]')).toHaveValue('368')
})
