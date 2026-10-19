import { expect, test } from '@playwright/test'

test('S3: enter lab measurements, correct one, reload, simulate at measured points, compare', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('S3 מדידות')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText('S3 מדידות')

  await page.getByRole('tab', { name: 'מדידות מעבדה והשוואה' }).click()
  await page.locator('input[name="set-label"]').fill('מעבדה 12.10 שולחן 4')
  await page.locator('input[name="set-instruments"]').fill('Fluke 87V, מד הספק אנלוגי')
  await page.getByTestId('create-set').click()
  await expect(page.getByTestId('missing-count')).toContainText('42 ערכים חסרים')

  const put = async (row: number, q: string, v: string, unit?: string) => {
    const cell = page.getByTestId(`cell-${row}-${q}`)
    if (unit) await cell.getByLabel('יחידה').selectOption(unit)
    const input = cell.locator('input')
    await input.fill(v)
    await input.press('Enter')
    await expect(input).toBeEnabled()
  }
  // rated point (row 0) — realistic numbers that differ from the assumed model
  await put(0, 'U1L', '380')
  await put(0, 'U1ph', '219.5')
  await put(0, 'U2L', '221')
  await put(0, 'U2ph', '127.4')
  await put(0, 'I0', '350', 'mA')
  await put(0, 'P_W', '21.5')
  await put(0, 'pf', '0.26')
  // second operating point, incomplete on purpose
  await put(1, 'U1L', '304')
  await put(1, 'I0', '0.19')

  // correction of a typo: 350 mA → 380 mA, original kept in history
  await put(0, 'I0', '380', 'mA')
  await expect(page.getByTestId('cell-0-I0').getByTestId('corrected')).toHaveText('תוקן ×1')
  await expect(page.getByTestId('missing-count')).toContainText('33 ערכים חסרים')

  await page.reload()
  await expect(page.getByTestId('cell-0-I0').locator('input')).toHaveValue('380')
  await expect(page.getByTestId('cell-0-I0').getByTestId('corrected')).toBeVisible()

  // measured-data analysis uses the same equations
  await expect(page.getByRole('table', { name: 'גדלים נגזרים מהמדידה' })).toContainText('64.50')

  await page.getByTestId('simulate-matching').click()
  const cmp = page.getByTestId('comparison')
  await expect(cmp.getByTestId('cmp-summary')).toContainText('ללא התאמה: 0')
  const rel = await cmp.locator('[data-q="0:I0"] td[data-rel]').getAttribute('data-rel')
  // measured 0.380 A vs simulated 0.36229 A at exactly 380 V
  expect(Number(rel)).toBeCloseTo(0.380 / 0.362287 - 1, 4)
  await expect(cmp.locator('[data-q="1:U2L"]')).toContainText('חסר')
  await expect(cmp.getByTestId('param-triad').locator('[data-param="R_fe"]')).toContainText('2400')
  await page.screenshot({ path: 'test-results/s3-comparison.png', fullPage: true })

  // switch reference to the measurement
  await page.locator('select[name="cmp-ref"]').selectOption('measurement')
  const rel2 = await cmp.locator('[data-q="0:I0"] td[data-rel]').getAttribute('data-rel')
  expect(Number(rel2)).toBeCloseTo((0.380 - 0.362287) / 0.380, 4)
})

test('S3: incompatible unit is rejected', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('S3 יחידות')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await page.getByRole('tab', { name: 'מדידות מעבדה והשוואה' }).click()
  await page.getByTestId('create-set').click()
  const input = page.getByTestId('cell-0-U1L').locator('input')
  await input.fill('abc')
  await input.press('Enter')
  await expect(page.getByTestId('cell-0-U1L')).toContainText('מספר לא תקין')
})
