import { expect, test } from '@playwright/test'

test('M1: explanation videos — every video loads, the transcript seeks, the experiment links to its videos', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('nav-videos').click()
  for (const id of ['RotatingField', 'TorqueSpeed', 'TransformerTests', 'SyncOccScc', 'VCurves']) {
    const card = page.getByTestId(`video-${id}`)
    await expect(card).toBeVisible()
    const dur = await card.locator('video').evaluate(
      (v: HTMLVideoElement) =>
        new Promise<number>((res) => (v.readyState >= 1 ? res(v.duration) : v.addEventListener('loadedmetadata', () => res(v.duration)))),
    )
    expect(dur).toBeGreaterThan(20)
  }
  const card = page.getByTestId('video-TorqueSpeed')
  await card.locator('summary').click()
  const cues = card.locator('.cue')
  expect(await cues.count()).toBeGreaterThan(5)
  await cues.nth(3).click()
  const t = await card.locator('video').evaluate((v: HTMLVideoElement) => v.currentTime)
  expect(t).toBeGreaterThan(5)
  await page.screenshot({ path: 'test-results/m1-videos.png', fullPage: false })

  // a transformer project links to its video
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('M1 שנאי')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await page.getByTestId('project-videos').getByRole('link', { name: /ריקם וקצר בשנאי/ }).click()
  await expect(page).toHaveURL(/\/videos#TransformerTests$/)
})
