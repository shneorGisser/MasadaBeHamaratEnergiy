import { expect, test } from '@playwright/test'

test('S0: create, open, rename, reload and delete a project (real backend + SQLite)', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByText('אין עדיין פרויקטים')).toBeVisible()

  await page.getByPlaceholder(/קבוצה 3/).fill('קבוצה 3 — בדיקת E2E')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()

  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}/)
  await expect(page.getByTestId('project-title')).toHaveText('קבוצה 3 — בדיקת E2E')
  await expect(page.getByText('ערכים מוערכים — לא נתוני שלט')).toBeVisible()

  await page.locator('input[name="notes"]').fill('שולחן 4, וריאק ישן')
  await page.locator('input[name="rename"]').fill('קבוצה 3')
  await page.getByRole('button', { name: 'שמור' }).click()
  await expect(page.getByText('נשמר')).toBeVisible()

  // Full reload: state must come back from the database, not from client memory.
  await page.reload()
  await expect(page.getByTestId('project-title')).toHaveText('קבוצה 3')
  await expect(page.locator('input[name="notes"]')).toHaveValue('שולחן 4, וריאק ישן')

  await page.getByText('חזרה לפרויקטים').click()
  await expect(page.getByRole('link', { name: 'קבוצה 3' })).toBeVisible()
  page.once('dialog', (d) => void d.accept())
  await page.getByRole('button', { name: 'מחק' }).click()
  await expect(page.getByText('אין עדיין פרויקטים')).toBeVisible()
})

test('S0: unknown project shows an error, not a blank page', async ({ page }) => {
  await page.goto('/projects/00000000-0000-0000-0000-000000000000')
  await expect(page.getByRole('alert')).toContainText('not found')
})
