import { expect, test } from '@playwright/test'

test('S4: 3D bench shows solver readings, variac and switch drive the model, selection syncs with the schematic', async ({ page }) => {
  const request = page.request // shares the browser's cookies (its workspace)
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('S4 שולחן')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText('S4 שולחן')
  const pid = page.url().split('/projects/')[1]!.split(/[/?]/)[0]!

  await page.getByTestId('lab3d-section').locator('summary').click()
  await expect(page.getByTestId('lab3d').locator('canvas')).toBeVisible()

  // readings come from the solver: compare with the API at the same operating point
  const ref = await (
    await request.post(`/api/projects/${pid}/circuits/no_load/operating-point`, { data: { overrides: { G: { U_line: 380 } } } })
  ).json()
  await expect(page.getByTestId('reading-A')).toHaveText(`${ref.readings.A.I.toFixed(4)} A`)
  await expect(page.getByTestId('reading-V1')).toHaveText('380.0 V')
  await expect(page.getByTestId('eq-G')).toBeVisible() // first component's label (regression)
  await page.screenshot({ path: 'test-results/s4-lab3d.png', fullPage: false })

  // variac to the top of its range (1.25·Un = 475 V) → saturation shows in I0
  await page.getByTestId('variac').focus()
  await page.keyboard.press('End')
  await expect(page.getByTestId('variac-value')).toHaveText('475.0 V')
  const hi = await (
    await request.post(`/api/projects/${pid}/circuits/no_load/operating-point`, { data: { overrides: { G: { U_line: 475 } } } })
  ).json()
  await expect(page.getByTestId('reading-A')).toHaveText(`${hi.readings.A.I.toPrecision(4)} A`)
  expect(hi.readings.A.I).toBeGreaterThan(3 * ref.readings.A.I)

  // open the main switch → no current, no secondary voltage
  await page.getByTestId('switch-S').uncheck()
  await expect(page.getByTestId('reading-A')).toHaveText('0 A')
  await expect(page.getByTestId('reading-V2')).toHaveText('0 V')

  // selection: 3D → schematic
  await page.getByTestId('eq-T').click()
  await expect(page.getByTestId('node-T')).toHaveClass(/selected/)
  await expect(page.getByTestId('param-panel')).toContainText('T')
  // schematic → 3D
  await page.getByTestId('node-V2').click()
  await expect(page.getByTestId('eq-V2')).toHaveAttribute('data-selected', 'true')
  await expect(page.getByTestId('eq-T')).toHaveAttribute('data-selected', 'false')

  // the 3D view must not persist anything: no runs were created
  const runs = await (await request.get(`/api/projects/${pid}/runs`)).json()
  expect(runs).toHaveLength(0)
})
