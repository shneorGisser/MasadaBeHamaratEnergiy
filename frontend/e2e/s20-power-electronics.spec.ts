import { expect, test } from '@playwright/test'

test('P2: power-electronics bench — B6C in ngspice (WASM) agrees with 1.35·V_LL·cos α', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('nav-pe').click()
  await expect(page.getByTestId('pe-bench')).toBeVisible()
  await page.getByTestId('pe-tab-b6').click()
  await expect(page.locator('img.pe-schematic')).toHaveAttribute('src', '/pe/b6.svg')
  await page.locator('input[name="pe-alpha"]').fill('30')
  await page.getByTestId('pe-run').click()
  const res = page.getByTestId('pe-results')
  await expect(res).toBeVisible({ timeout: 90_000 })
  const vd = res.locator('tr[data-check="Vd"]')
  await expect(vd).toContainText('תואם')
  // 1.35·√3·45·cos 30° = 91.2 V (ideal components, no source inductance)
  await expect(vd).toContainText(/9[01]\.\d+ V/)
  await expect(res.locator('.chart canvas').first()).toBeVisible()
  await page.screenshot({ path: 'test-results/p2-pe-bench.png', fullPage: true })

  // switching converter in the same worker
  await page.getByTestId('pe-tab-buck').click()
  await page.getByTestId('pe-run').click()
  await expect(res.locator('tr[data-check="Vo"]')).toContainText('תואם', { timeout: 60_000 })
})
