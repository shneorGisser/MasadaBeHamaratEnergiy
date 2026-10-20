import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

async function newProject(page: import('@playwright/test').Page, name: string): Promise<void> {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill(name)
  await page.locator('select[name="experiment"]').selectOption('installation')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-experiment')).toContainText('מתקן חשמלי')
}

test('I1: installation tests — MCB time–current from the 2025 report, RCD principle, spec form', async ({ page }) => {
  await newProject(page, 'I1 בדיקות מתקן')

  // MCB: the report's table imported, simulated at its own points and compared on log axes
  await openTab(page, /בדיקת מא״ז/)
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', /success/)
  await expect(view.getByRole('table', { name: /זמן ניתוק בזרם קבוע/ }).locator('tbody tr')).toHaveCount(9)
  await expect(view.locator('.chart canvas').first()).toBeVisible()
  await page.screenshot({ path: 'test-results/i1-mcb-run.png', fullPage: true })

  await openTab(page, 'מדידות מעבדה והשוואה')
  await page.getByTestId('import-report').locator('summary').click()
  await page.getByTestId('import-installation_2025-2').click()
  await expect(page.getByTestId('set-notes')).toContainText('סוג מא״ז')
  await page.getByTestId('simulate-matching').click()
  await expect(page.getByTestId('cmp-summary')).toContainText('ללא התאמה: 0')
  await page.screenshot({ path: 'test-results/i1-mcb-compare.png', fullPage: true })

  // fault loop: the report's L-N zeros are flagged as physically impossible
  await openTab(page, 'עכבת לולאת התקלה')
  await openTab(page, 'מדידות מעבדה והשוואה')
  await page.getByTestId('import-report').locator('summary').click()
  await page.getByTestId('import-installation_2025-1').click()
  await expect(page.locator('[data-testid="analysis-warning"][data-code="loop_below_phase"]')).toHaveCount(3)
  await page.getByTestId('simulate-matching').click()
  await expect(page.getByTestId('cmp-summary')).toContainText('ללא התאמה: 0')
  await page.screenshot({ path: 'test-results/i1-loop-compare.png', fullPage: true })

  // RCD: a person between L and N is invisible to the toroid
  await openTab(page, /מפסק מגן/)
  await openTab(page, 'סימולציה')
  await page.getByTestId('run-button').click()
  const principle = view.getByRole('table', { name: /עקרון הטורואיד/ })
  await expect(principle.locator('tbody tr').nth(1)).toContainText('לא מנתק')
  await page.screenshot({ path: 'test-results/i1-rcd.png', fullPage: true })

  await page.getByRole('link', { name: 'מפרט המתקן' }).click()
  await expect(page.locator('input[name="mcb.tau"]')).toHaveValue('48.7')
  await expect(page.locator('select[name="network.curve_prot"]')).toHaveValue('C')
  await page.screenshot({ path: 'test-results/i1-spec.png', fullPage: true })
})
