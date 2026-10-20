import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

async function newProject(page: import('@playwright/test').Page, name: string, exp: string): Promise<void> {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill(name)
  await page.locator('select[name="experiment"]').selectOption(exp)
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-experiment')).toBeVisible()
}

test('R1: import a real report table, simulate at its points, explain the differences, probe parameter sets', async ({ page }) => {
  await newProject(page, 'R1 סינכרונית 2025', 'synchronous')
  await openTab(page, /אופייני קצר/)
  await openTab(page, 'מדידות מעבדה והשוואה')

  await page.getByTestId('import-report').locator('summary').click()
  await page.getByTestId('import-synchronous_2025-2').click()
  await expect(page.getByTestId('set-notes')).toContainText('דוח 2025')
  await expect(page.getByTestId('missing-count')).toBeVisible()

  await page.getByTestId('simulate-matching').click()
  const diag = page.getByTestId('diagnosis')
  await expect(diag.locator('[data-code="common_factor"]')).toContainText('Ik3')
  await page.screenshot({ path: 'test-results/r1-diagnosis.png', fullPage: true })

  await page.getByTestId('probe').click()
  const first = page.getByTestId('probe-table').locator('tbody tr').first()
  await expect(first).toHaveAttribute('data-candidate', 'report_2025')
  await expect(first).toContainText('הכי מתאימה')
  await page.getByTestId('probe-section').screenshot({ path: 'test-results/r1-probe.png' })
})

test('R2: DC motor table with its conditions; conditions are editable', async ({ page }) => {
  await newProject(page, 'R2 מנוע DC 2025', 'dc_motor')
  await openTab(page, /^מנוע מקבילי בעומס$/)
  await openTab(page, 'מדידות מעבדה והשוואה')
  await page.getByTestId('import-report').locator('summary').click()
  await page.getByTestId('import-dc_motor_2025-3').click()
  await expect(page.locator('input[name="cond-U"]')).toHaveValue('174.3')
  await page.locator('input[name="cond-If"]').fill('0.47')
  await page.getByTestId('save-conditions').click()
  await expect(page.getByTestId('save-conditions')).toBeDisabled()
  await page.getByTestId('simulate-matching').click()
  await expect(page.getByTestId('comparison')).toBeVisible()
  await expect(page.getByTestId('cmp-summary')).toContainText('ללא התאמה: 0')
})
