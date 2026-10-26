import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

/** Master prompt §9 — the complete first-experiment journey, in a real browser, real backend. */
test('S5: full journey — guided mode, parameters, simulate, reload, measure, compare, report', async ({ page }) => {
  const request = page.request // shares the browser's cookies (its workspace)
  // 1. open the experiment
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('מסע מלא')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText('מסע מלא')
  const pid = page.url().split('/projects/')[1]!.split(/[/?]/)[0]!

  await page.getByRole('link', { name: 'מצב מודרך' }).click()
  await expect(page.getByTestId('guide-progress')).toHaveText('0 / 31')
  await page.getByTestId('ack-safety').click()
  await expect(page.getByTestId('guide-progress')).toHaveText('1 / 31')

  // 2. enter valid transformer parameters (as if from the nameplate)
  await page.getByTestId('go-nameplate').click()
  await page.locator('input[name="nameplate.S_n"]').fill('2500')
  await page.locator('select[name="provenance"]').selectOption('nameplate')
  await page.getByRole('button', { name: 'שמור מפרט' }).click()
  await expect(page.getByText('המפרט נשמר')).toBeVisible()

  // 3–5. configure the no-load conditions, execute, inspect
  await page.getByRole('link', { name: 'מצב מודרך' }).click()
  await expect(page.locator('[data-step="nameplate"]')).toHaveAttribute('data-done', 'true')
  await page.getByTestId('go-no_load.simulate').click()
  await page.locator('input[name="case-U_line_values"]').fill('190, 300, 380, 410')
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', 'success')
  await expect(view.getByRole('table', { name: /טבלה 1.3/ }).locator('tbody tr')).toHaveCount(4)
  const runId = await view.getAttribute('data-run-id')
  const i0 = await view.getByRole('table', { name: /טבלה 1.3/ }).locator('tbody tr').nth(2).locator('td').nth(5).textContent()

  // 6–8. the project is saved; reload and confirm results and model are consistent
  await page.reload()
  await expect(page.getByTestId('run-view')).toHaveAttribute('data-run-id', runId!)
  await expect(page.getByTestId('run-view').getByRole('table', { name: /טבלה 1.3/ }).locator('tbody tr').nth(2).locator('td').nth(5)).toHaveText(i0!)
  const run = await (await request.get(`/api/runs/${runId}`)).json()
  expect(run.input_snapshot.spec.nameplate.S_n).toBe(2500)
  await page.getByRole('button', { name: 'בדוק שחזור' }).click()
  await expect(page.getByTestId('reproduce-result')).toHaveText('שוחזר: תוצאה זהה לחלוטין')

  // 9. enter real laboratory measurements
  await openTab(page, 'מדידות מעבדה והשוואה')
  await page.locator('input[name="set-label"]').fill('מעבדה 12.10')
  await page.getByTestId('create-set').click()
  const vals: [string, string][] = [
    ['U1L', '380'], ['U1ph', '219.8'], ['U2L', '220.4'], ['U2ph', '127.1'], ['I0', '0.41'], ['P_W', '22.3'], ['pf', '0.25'],
  ]
  for (const [q, v] of vals) {
    const inp = page.getByTestId(`cell-0-${q}`).locator('input')
    await inp.fill(v)
    await inp.press('Enter')
    await expect(inp).toBeEnabled()
  }

  // 10. compare with a simulation at the measured operating point
  await page.getByTestId('simulate-matching').click()
  await expect(page.getByTestId('comparison').getByTestId('cmp-summary')).toContainText('ללא התאמה: 0')
  await expect(page.getByTestId('param-triad').locator('[data-param="R_fe"]')).toBeVisible()

  // 11. generate and reopen the report
  await page.getByRole('link', { name: 'דו״חות' }).click()
  await expect(page.getByTestId('rs-no_load').locator('input[type="checkbox"]')).toBeChecked()
  await page.locator('textarea[name="discussion"]').fill('I0 הנמדד גבוה ב-~13% מהמודל; פרמטרי ענף המגנוט מוערכים.')
  await page.getByTestId('create-report').click()
  const frame = page.frameLocator('[data-testid="report-frame"]')
  await expect(frame.locator('h1')).toHaveText('דו״ח ניסוי 1 — בדיקת שנאי תלת-פזי')
  await expect(frame.getByText('I0 הנמדד גבוה ב-~13% מהמודל')).toBeVisible()
  await expect(frame.locator('td', { hasText: '0.4100' }).first()).toBeVisible()

  // a later correction must not change the published report
  const reports = await (await request.get(`/api/projects/${pid}/reports`)).json()
  const before = await (await request.get(`/api/reports/${reports[0].id}/html`)).text()
  const inp = page
  await inp.getByRole('link', { name: 'ניסויים וסימולציה' }).click()
  await openTab(page, 'מדידות מעבדה והשוואה')
  const cell = page.getByTestId('cell-0-I0').locator('input')
  await cell.fill('0.39')
  await cell.press('Enter')
  await expect(page.getByTestId('cell-0-I0').getByTestId('corrected')).toBeVisible()
  const after = await (await request.get(`/api/reports/${reports[0].id}/html`)).text()
  expect(after).toBe(before)

  // reopen: after a full reload the report is still there
  await page.getByRole('link', { name: 'דו״חות' }).click()
  await page.reload()
  await expect(page.frameLocator('[data-testid="report-frame"]').locator('h1')).toBeVisible()
  const pdf = await request.get(`/api/reports/${reports[0].id}/pdf`)
  expect(pdf.status()).toBe(200)
  expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-')
  // Word export of the same snapshot: a zip (docx) offered from the reports list
  await expect(page.getByTestId('report-docx').first()).toBeVisible()
  const docx = await request.get(`/api/reports/${reports[0].id}/docx`)
  expect(docx.status()).toBe(200)
  expect((await docx.body()).subarray(0, 2).toString()).toBe('PK')

  await page.getByRole('link', { name: 'מצב מודרך' }).click()
  await expect(page.locator('[data-step="no_load.compare"]')).toHaveAttribute('data-done', 'true')
  await expect(page.locator('[data-step="report"]')).toHaveAttribute('data-done', 'true')
  await page.screenshot({ path: 'test-results/s5-guide.png', fullPage: true })
})
