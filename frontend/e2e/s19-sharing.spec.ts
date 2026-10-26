import { expect, test, type Browser, type Page } from '@playwright/test'

async function newProject(page: Page, name: string): Promise<string> {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill(name)
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText(name)
  return page.url().split('/projects/')[1]!.split(/[/?]/)[0]!
}

async function freshBrowser(browser: Browser): Promise<Page> {
  const ctx = await browser.newContext({ locale: 'he-IL' })
  return ctx.newPage()
}

test('W1: each browser has its own projects; a share link copies, the workspace link continues', async ({
  page,
  browser,
}) => {
  // Alice creates a project and a share link
  await newProject(page, 'W1 של אליס')
  await page.getByTestId('share-box').locator('summary').click()
  await page.getByTestId('share-create').click()
  const link = await page.getByTestId('share-link').inputValue()
  expect(link).toMatch(/\/s\/[A-Za-z0-9_-]{22,}$/)

  // Bob, another browser, sees none of Alice's projects
  const bob = await freshBrowser(browser)
  await bob.goto('/')
  await expect(bob.getByText('W1 של אליס')).toHaveCount(0)

  // …opens the share link and copies the project into his own space
  await bob.goto(link)
  await expect(bob.getByTestId('shared-page')).toContainText('W1 של אליס')
  await bob.getByTestId('shared-copy').click()
  await expect(bob.getByTestId('project-title')).toHaveText('W1 של אליס (עותק)')
  await bob.goto('/')
  await expect(bob.getByRole('link', { name: 'W1 של אליס (עותק)' })).toBeVisible()

  // Alice does not see Bob's copy; revoking the link stops it
  await page.goto('/')
  await expect(page.getByText('(עותק)')).toHaveCount(0)
  await page.getByRole('link', { name: 'W1 של אליס' }).click()
  await page.getByTestId('share-box').locator('summary').click()
  await page.getByTestId('share-create').click() // the same, stable link
  await expect(page.getByTestId('share-link')).toHaveValue(link)
  await page.getByTestId('share-revoke').click()
  await bob.goto(link)
  await expect(bob.getByTestId('shared-missing')).toBeVisible()

  // Alice's workspace link opens her projects in a third browser
  await page.goto('/')
  await page.getByTestId('workspace-box').locator('summary').click()
  const wsLink = await page.getByTestId('workspace-link').inputValue()
  const tablet = await freshBrowser(browser)
  await tablet.goto(wsLink)
  await expect(tablet.getByRole('link', { name: 'W1 של אליס' })).toBeVisible()
  await expect(tablet).toHaveURL(/\/$/) // the token does not stay in the address bar
  await page.screenshot({ path: 'test-results/w1-projects.png', fullPage: true })
})

test('W2: feedback from any page reaches the operator list, and only with the key', async ({ page, browser }) => {
  await newProject(page, 'W2 משוב')
  await page.getByTestId('feedback-open').click()
  await page.getByText('רעיון לשיפור').click()
  await expect(page.getByRole('radio', { name: 'רעיון לשיפור' })).toBeChecked()
  await page.locator('textarea[name="feedback-message"]').fill('אפשר להוסיף ניסוי של ממירים?')
  await page.locator('input[name="feedback-contact"]').fill('דני')
  await page.screenshot({ path: 'test-results/w2-feedback.png', fullPage: false })
  await page.getByTestId('feedback-send').click()
  await expect(page.getByTestId('feedback-sent')).toBeVisible()

  const admin = await freshBrowser(browser)
  await admin.goto('/feedback')
  await admin.locator('input[name="admin-key"]').fill('wrong key')
  await admin.getByRole('button', { name: 'הצגת המשוב' }).click()
  await expect(admin.getByText(/המפתח שגוי/)).toBeVisible()
  await admin.locator('input[name="admin-key"]').fill('e2e-admin-key-not-secret')
  await admin.getByRole('button', { name: 'הצגת המשוב' }).click()
  const table = admin.getByRole('table', { name: 'משוב' })
  await expect(table).toContainText('אפשר להוסיף ניסוי של ממירים?')
  await expect(table).toContainText('רעיון')
  await expect(table).toContainText('/projects/')
  await admin.screenshot({ path: 'test-results/w2-admin.png', fullPage: true })
})
