import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

test('W1: wiring guide walks the cables from the supply and highlights each one on the schematic', async ({ page }) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('W1 מדריך חיבור')
  await page.locator('select[name="experiment"]').selectOption('dc_motor')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await openTab(page, /^מנוע מקבילי בעומס$/)

  const guide = page.getByTestId('wiring-guide')
  await guide.locator('summary').click()
  await expect(guide.locator('summary')).toContainText('10 כבלים')
  const text = page.getByTestId('wiring-step-text')
  await expect(text).toContainText('ספק DC')
  await expect(text).toContainText('ריאוסטט עירור')
  await expect(page.getByTestId('wiring-step')).toContainText('אדום')
  // exactly one cable is highlighted on the schematic
  await expect(page.locator('.react-flow__edge.animated')).toHaveCount(1)
  await page.screenshot({ path: 'test-results/w1-guide-step1.png', fullPage: true })

  await page.getByTestId('wiring-next').click()
  await expect(text).toContainText('A2 (עירור)')
  await expect(page.getByTestId('wiring-step')).toContainText('בטור')
  await expect(page.getByTestId('wiring-step')).toContainText('1/10 חוברו')
  await expect(page.locator('.react-flow__edge.animated')).toHaveCount(1)
  await page.getByTestId('wiring-step').screenshot({ path: 'test-results/w1-guide-step2.png' })

  await guide.locator('summary').click() // closing the guide removes the highlight
  await expect(page.locator('.react-flow__edge.animated')).toHaveCount(0)
})
