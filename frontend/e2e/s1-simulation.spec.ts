import { openTab } from './helpers'
import { expect, test, type Page } from '@playwright/test'

async function newProject(page: Page, name: string) {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill(name)
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText(name)
}

test('S1: no-load simulation → results → reload → reproduce → spec change keeps old run', async ({ page }) => {
  await newProject(page, 'S1 ריקם')
  await expect(page.getByRole('tab', { name: 'ניסוי ריקם' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText('אין עדיין ריצות לניסוי זה.')).toBeVisible()

  await page.locator('input[name="run-label"]').fill('ריצה ראשונה')
  await page.getByTestId('run-button').click()

  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', 'success_with_warnings')
  const table = view.getByRole('table', { name: /טבלה 1.3/ })
  await expect(table.locator('tbody tr')).toHaveCount(8)
  // rated point row: U1L = 380 V, I0 ≈ 0.3623 A (from the assumed parameter set)
  await expect(table.locator('tbody tr').nth(5)).toContainText('380.0')
  await expect(table.locator('tbody tr').nth(5)).toContainText('0.3623')
  await expect(view.locator('[data-param="R_fe"]')).toContainText('2397.6')
  await expect(view.getByTestId('run-warnings')).toContainText('1.1·Un')
  await expect(view.locator('.chart canvas').first()).toBeVisible()
  await page.screenshot({ path: 'test-results/s1-no-load.png', fullPage: true })

  const runId = await view.getAttribute('data-run-id')
  expect(runId).toBeTruthy()

  // reload: the run comes back from SQLite
  await page.reload()
  await expect(page.getByTestId('run-view')).toHaveAttribute('data-run-id', runId!)
  await expect(page.getByTestId('run-history').getByText('ריצה ראשונה')).toBeVisible()

  await page.getByRole('button', { name: 'בדוק שחזור' }).click()
  await expect(page.getByTestId('reproduce-result')).toHaveText('שוחזר: תוצאה זהה לחלוטין')

  // change the transformer (R_Fe halved) — the stored run must not change
  await page.getByRole('link', { name: 'מפרט השנאי' }).click()
  await page.locator('input[name="ecm.R_fe"]').fill('1200')
  await page.getByRole('button', { name: 'שמור מפרט' }).click()
  await expect(page.getByText('המפרט נשמר')).toBeVisible()
  await page.getByRole('link', { name: 'ניסויים וסימולציה' }).click()
  await expect(page.getByTestId('run-view')).toHaveAttribute('data-run-id', runId!)
  await expect(page.getByTestId('run-view').locator('[data-param="R_fe"]')).toContainText('2397.6')

  await page.getByTestId('run-button').click()
  await expect(page.getByTestId('run-view')).not.toHaveAttribute('data-run-id', runId!)
  await expect(page.getByTestId('run-view').locator('[data-param="R_fe"]')).toContainText('1201.8')
})

test('S1: short circuit shows the manual-formula failure; invalid input is a failed run', async ({ page }) => {
  await newProject(page, 'S1 קצר')
  await openTab(page, 'ניסוי קצר')
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', 'success')
  await expect(view.locator('[data-param="x_k"]')).toContainText('1.9238')
  await expect(view.locator('[data-param="x_k_manual"]')).toContainText('לא מוגדר')
  await expect(view.locator('[data-param="u_k_pct"]')).toContainText('4.9864')
  await page.screenshot({ path: 'test-results/s1-short-circuit.png', fullPage: true })

  // invalid case → explicit failure, never shown as success
  await openTab(page, 'ניסוי ריקם')
  await page.locator('input[name="case-U_line_values"]').fill('380, abc')
  await page.getByTestId('run-button').click()
  await expect(page.getByTestId('run-view').getByTestId('run-status')).toHaveAttribute('data-status', 'invalid_input')
  await expect(page.getByTestId('run-error')).toBeVisible()
  await expect(page.getByTestId('run-view').locator('table')).toHaveCount(0)
})

test('S1: DC resistance and insulation run', async ({ page }) => {
  await newProject(page, 'S1 DC')
  await openTab(page, 'התנגדות ליפופים בזרם ישר')
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByRole('table', { name: 'התנגדות ממוצעת לליפוף' }).locator('tbody tr')).toHaveCount(6)
  await expect(view.getByRole('table', { name: 'התנגדות ממוצעת לליפוף' })).toContainText('0.7200')
  await openTab(page, 'בדיקת בידוד (מגר)')
  await page.getByTestId('run-button').click()
  await expect(page.getByTestId('run-view').getByTestId('run-warnings')).toContainText('אינה סימולציה פיזיקלית')
})

test('S6: load the preset fitted to last year\'s report and simulate its short-circuit point', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('S6 נתוני מעבדה')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await page.getByRole('link', { name: 'מפרט השנאי' }).click()
  await page.getByTestId('preset').selectOption('report_2025')
  await expect(page.locator('input[name="ecm.R1"]')).toHaveValue('13.47')
  await page.getByRole('button', { name: 'שמור מפרט' }).click()
  await expect(page.getByText('המפרט נשמר')).toBeVisible()
  await expect(page.locator('span.badge', { hasText: 'חולץ ממדידות' })).toBeVisible()
  await page.getByRole('link', { name: 'ניסויים וסימולציה' }).click()
  await openTab(page, 'ניסוי קצר')
  // wait for the study switch to render before using its controls (fast CI runners raced here)
  await expect(page.getByRole('tab', { name: 'ניסוי קצר' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('heading', { level: 2, name: 'ניסוי קצר' })).toBeVisible()
  await page.getByRole('button', { name: /טען מעגל לפי החוברת/ }).click()
  await page.locator('input[name="case-I_targets_pu"]').fill('1')
  await page.getByTestId('run-button').click()
  const row = page.getByTestId('run-view').getByRole('table', { name: /טבלה 1.5/ }).locator('tbody tr').first()
  await expect(row).toContainText('0.3500') // I1k = 0.35 A rated (report)
  await expect(row).toContainText('0.6984') // I2k ≈ 0.7 A (magnetizing current reduces it slightly)
})

test('TH1: hot windings — T_op in the spec scales the copper and the run says so', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('TH1 חם')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toBeVisible()
  await page.getByRole('link', { name: 'מפרט השנאי' }).click()
  await expect(page.locator('input[name="thermal.T_ref"]')).toHaveValue('20')
  await page.locator('input[name="thermal.T_op"]').fill('75')
  await page.getByRole('button', { name: 'שמור מפרט' }).click()
  await expect(page.getByText('המפרט נשמר')).toBeVisible()
  await page.getByRole('link', { name: 'ניסויים וסימולציה' }).click()
  await page.getByRole('tab', { name: 'ניסוי קצר' }).click()
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-warnings')).toContainText('תוקנו מ-20 °C ל-75 °C')
})
