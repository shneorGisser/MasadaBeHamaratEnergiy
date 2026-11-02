import { expect, test } from '@playwright/test'
import { openTab } from './helpers'

test('C2: the measurement coach questions a reading in mA, and its suggestion is entered as a correction', async ({ page }) => {
  const request = page.request
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('C2 מאמן')
  await page.locator('select[name="experiment"]').selectOption('induction_motor')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText('C2 מאמן')
  const pid = page.url().split('/projects/')[1]!.split(/[/?]/)[0]!
  const spec = ((await (await request.get('/api/experiments/induction_motor/presets')).json()) as { id: string; spec: unknown }[]).find(
    (p) => p.id === 'ap3030_sheet_2026',
  )!.spec
  expect((await request.patch(`/api/projects/${pid}`, { data: { spec } })).ok()).toBeTruthy()
  expect((await request.post(`/api/projects/${pid}/datasets/induction_motor_2026/import`, { data: { study_kind: 'load' } })).ok()).toBeTruthy()
  await page.reload()
  await openTab(page, 'ניסוי עומס (בלם)')
  await openTab(page, 'מדידות מעבדה והשוואה')

  // the imported sheet raises no question
  await expect(page.getByTestId('cell-2-I1').locator('input')).toHaveValue('0.55')
  await expect(page.getByTestId('coach')).toHaveCount(0)

  // a reading typed in mA
  const cell = page.getByTestId('cell-2-I1').locator('input')
  await cell.fill('550')
  await cell.press('Enter')
  const q = page.getByTestId('coach-2-I1')
  await expect(q).toContainText('1000')
  await expect(page.getByTestId('cell-2-I1')).toHaveAttribute('data-coach', 'factor')
  await page.screenshot({ path: 'test-results/c2-coach.png', fullPage: false })
  await page.getByTestId('coach-apply-2-I1').click()
  await expect(page.getByTestId('cell-2-I1').locator('input')).toHaveValue('0.55')
  await expect(page.getByTestId('coach')).toHaveCount(0)
  await expect(page.getByTestId('cell-2-I1').getByTestId('corrected')).toContainText('×2')
})
