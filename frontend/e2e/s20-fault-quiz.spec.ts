import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

test('Q1: fault challenge — readings of the hidden fault next to the correct circuit, then the answer', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('Q1 תקלות')
  await page.locator('select[name="experiment"]').selectOption('induction_motor')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText('Q1 תקלות')
  await openTab(page, 'ניסוי עומס (בלם)')
  const fq = page.getByTestId('fault-quiz')
  await fq.locator('summary').click()
  await fq.getByTestId('fq-new').click()
  const table = fq.getByRole('table', { name: 'קריאות המכשירים' })
  await expect(table.locator('tbody tr')).not.toHaveCount(0)
  await expect(table).toContainText('rpm')
  // every option is offered, including "no fault"
  await expect(fq.getByRole('radio')).toHaveCount(5)
  await fq.getByRole('radio').first().check()
  await fq.getByTestId('fq-check').click()
  await expect(fq.getByTestId('fq-result')).toBeVisible()
  await expect(fq.getByTestId('fq-score')).toContainText('/1')
  await fq.screenshot({ path: 'test-results/q1-fault-quiz.png' })
})
