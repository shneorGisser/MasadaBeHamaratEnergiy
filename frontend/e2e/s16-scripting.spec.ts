import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

test('P1: a Python script sweeps a study through the run API and plots the result', async ({ page }) => {
  test.setTimeout(120_000)
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('P1 סקריפט')
  await page.locator('select[name="experiment"]').selectOption('network')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-experiment')).toBeVisible()
  await page.getByRole('link', { name: 'סקריפט' }).click()
  const panel = page.getByTestId('script-panel')
  await expect(panel.locator('textarea[name="script-code"]')).toHaveValue(/vlab\.run\("load_flow"/)
  await page.getByTestId('script-run').click()
  const out = page.getByTestId('script-output')
  await expect(out).toContainText('Z_loop at the bench', { timeout: 90_000 })
  await expect(out).toContainText('הסתיים')
  await expect(panel.locator('.chart canvas')).toHaveCount(1)
  await page.screenshot({ path: 'test-results/p1-script.png', fullPage: true })

  // a failing run is an exception in the script, not an empty result
  await panel.locator('textarea[name="script-code"]').fill(
    'import vlab\nawait vlab.run("load_flow", scales=[-1])\n',
  )
  await page.getByTestId('script-run').click()
  await expect(out).toContainText('RunFailed', { timeout: 30_000 })

  // the script's runs are ordinary runs of the project
  await page.getByRole('link', { name: 'ניסויים וסימולציה' }).click()
  await openTab(page, /זרימת עומסים/)
  await expect(page.getByText('script: sweep').first()).toBeVisible()
})
