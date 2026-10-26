import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

test('D4: wound rotor — turns ratio, rotor resistance lowers the speed, induction regulator on the 3D bench', async ({ page }) => {
  const request = page.request // shares the browser's cookies (its workspace)
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('D4 רוטור מלופף')
  await page.locator('select[name="experiment"]').selectOption('wound_rotor')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-experiment')).toContainText('רוטור מלופף')
  const pid = page.url().split('/projects/')[1]!.split(/[/?]/)[0]!

  // turns ratio: the open-rotor voltage from the nameplate fit is 107 V → k = 400/107
  await openTab(page, 'מקדם השנאה (רוטור פתוח)')
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  const ratio = view.getByRole('table', { name: /טבלה 4.3/ })
  await expect(ratio.locator('tbody tr').first()).toContainText('107.0')
  await expect(view.locator('[data-param="k"]')).toContainText('3.738')

  // load with and without the starter resistance at the same torque
  await openTab(page, 'ניסוי עומס (מתנע באפס)')
  await page.locator('input[name="case-M_targets"]').fill('1.5')
  await page.getByTestId('run-button').click()
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', /success/)
  const n0 = Number((await view.getByRole('table', { name: /טבלה 4.6/ }).locator('tbody tr td').nth(5).textContent()) ?? '0')
  await openTab(page, 'עומס עם נגד נוסף ברוטור')
  await page.locator('input[name="case-M_targets"]').fill('1.5')
  await page.locator('input[name="case-R_ext"]').fill('5')
  await page.getByTestId('run-button').click()
  const t7 = view.getByRole('table', { name: /טבלה 4.7/ })
  await expect(t7).toBeVisible()
  const n5 = Number((await t7.locator('tbody tr td').nth(5).textContent()) ?? '0')
  expect(n0).toBeGreaterThan(1300)
  expect(n5).toBeLessThan(n0 - 100)
  await page.screenshot({ path: 'test-results/d4-rext.png', fullPage: true })

  // induction regulator: the rotor-angle slider on the 3D bench drives U2
  await openTab(page, 'מכונת השראה כווסת מתח')
  await page.getByTestId('lab3d-section').locator('summary').click()
  await expect(page.getByTestId('lab3d').locator('canvas')).toBeVisible()
  const ref = await (
    await request.post(`/api/projects/${pid}/circuits/regulator/operating-point`, { data: { overrides: { M: { angle: 90, locked: true, M_load: 0 } } } })
  ).json()
  await page.getByTestId('angle').focus()
  for (let i = 0; i < 18; i++) await page.keyboard.press('ArrowUp') // 0 → 90° in 5° steps (ArrowRight decreases in RTL)
  await expect(page.getByTestId('angle-value')).toHaveText('90.00°')
  await expect(page.getByTestId('reading-V2')).toHaveText(`${ref.readings.V2.U.toFixed(1)} V`)
  await page.screenshot({ path: 'test-results/d4-regulator-3d.png' })

  await page.getByRole('link', { name: 'מפרט המכונה' }).click()
  await expect(page.locator('input[name="ecm.k"]')).toHaveValue('3.3027')
})
