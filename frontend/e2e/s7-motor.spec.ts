import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

test('D2: induction motor — load study with torque–speed curve, live brake on the 3D bench, measurements vs simulation', async ({ page }) => {
  const request = page.request // shares the browser's cookies (its workspace)
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('D2 מנוע')
  await page.locator('select[name="experiment"]').selectOption('induction_motor')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText('D2 מנוע')
  await expect(page.getByTestId('project-experiment')).toContainText('מנוע השראה')
  const pid = page.url().split('/projects/')[1]!.split(/[/?]/)[0]!

  // only the motor's studies are offered
  await expect(page.getByRole('tab', { name: 'ניסוי רוטור נעול (קצר)' })).toBeVisible()
  await expect(page.getByRole('tab', { name: /קבוצות חיבורים/ })).toHaveCount(0)

  // load study: brake torques → table 4.6, Kloss/torque–speed table, curves
  await openTab(page, 'ניסוי עומס (בלם)')
  await page.locator('input[name="case-M_targets"]').fill('0, 1, 2, 2.56')
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', 'success')
  const table = view.getByRole('table', { name: /טבלה 4.6/ })
  await expect(table.locator('tbody tr')).toHaveCount(4)
  // the solver's torque balance: M column equals the brake setting
  await expect(table.locator('tbody tr').nth(3)).toContainText('2.560')
  await expect(view.getByRole('table', { name: /מומנט–מהירות/ })).toBeVisible()
  await expect(view.locator('[data-param="M_max"]')).toBeVisible()
  await expect(view.locator('.chart canvas').first()).toBeVisible()
  await page.screenshot({ path: 'test-results/d2-motor-load.png', fullPage: true })

  // 3D bench: brake slider drives the solver; above pull-out the motor stalls
  await page.getByTestId('lab3d-section').locator('summary').click()
  await expect(page.getByTestId('lab3d').locator('canvas')).toBeVisible()
  const ref = await (
    await request.post(`/api/projects/${pid}/circuits/load/operating-point`, { data: { overrides: { M: { M_load: 0, locked: false } } } })
  ).json()
  await expect(page.getByTestId('reading-M')).toContainText(`${ref.readings.M.n.toPrecision(4)} rpm · 0 N·m`)
  await page.screenshot({ path: 'test-results/d2-motor-3d.png', fullPage: false })
  await page.getByTestId('brake').focus()
  await page.keyboard.press('End') // 3·M_n > pull-out torque
  await expect(page.getByTestId('live-warning-stalled')).toBeVisible()
  await expect(page.getByTestId('reading-M')).toHaveText(/^0 rpm/)
  await page.getByTestId('locked').check()
  await expect(page.getByTestId('reading-M')).toHaveText(/^0 rpm/)

  // spec tab speaks motor
  await page.getByRole('link', { name: 'מפרט המנוע' }).click()
  await expect(page.locator('input[name="nameplate.n_n"]')).toHaveValue('1380')
  await expect(page.locator('select[name="nameplate.poles"]')).toHaveValue('4')

  // measurements via the API (UI entry is covered by S3), compared in the UI
  const runs = await (await request.get(`/api/projects/${pid}/runs?study_kind=load`)).json()
  const run = await (await request.get(`/api/runs/${runs[0].id}`)).json()
  const set = await (
    await request.post(`/api/projects/${pid}/measurement-sets`, { data: { study_kind: 'load', label: 'מעבדה', n_rows: 4 } })
  ).json()
  const units: Record<string, string> = { U1L: 'V', I1: 'A', P_W: 'W', pf: '', n: 'rpm', M: 'N·m' }
  for (const [i, row] of (run.result.tables[0].rows as Record<string, number>[]).entries()) {
    for (const [q, unit] of Object.entries(units)) {
      const r = await request.post(`/api/measurement-sets/${set.set.id}/entries`, {
        data: { row_index: i, quantity: q, value: q === 'I1' ? row[q]! * 1.05 : row[q], unit },
      })
      expect(r.status()).toBe(201)
    }
  }
  const cmp = await (await request.get(`/api/comparison?run_id=${run.id}&set_id=${set.set.id}`)).json()
  expect(cmp.summary.unmatched_rows).toBe(0)
  expect(cmp.summary.max_abs_rel_error).toBeCloseTo(0.05, 9)
})
