import { expect, type Page } from '@playwright/test'

/**
 * Click a tab and wait until the UI has actually switched to it. Acting right after the click
 * raced on fast CI runners (a control of the previous study was used).
 */
export async function openTab(page: Page, name: string | RegExp): Promise<void> {
  const tab = page.getByRole('tab', { name })
  await tab.click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
}
