import { openTab } from './helpers'
import { expect, test, type Page } from '@playwright/test'

async function newProject(page: Page, name: string) {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill(name)
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-title')).toHaveText(name)
  return page.url().split('/projects/')[1]!.split(/[/?]/)[0]!
}

test('S2: load test on the template circuit, R and C loads', async ({ page }) => {
  await newProject(page, 'S2 עומס')
  await openTab(page, 'ניסוי עומס')
  await expect(page.getByTestId('node-T')).toBeVisible()
  await expect(page.getByTestId('node-L')).toBeVisible()
  await page.screenshot({ path: 'test-results/s2-load-schematic.png', fullPage: true })

  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', 'success')
  const rows = view.getByRole('table', { name: /עומס התנגדותי/ }).locator('tbody tr')
  await expect(rows).toHaveCount(5)
  await expect(rows.first()).toContainText('S2 פתוח')

  await page.locator('select[name="case-load_kind"]').selectOption('C')
  await page.getByTestId('run-button').click()
  await expect(page.getByTestId('run-view').getByRole('table', { name: /עומס קיבולי/ })).toBeVisible()
  await page.screenshot({ path: 'test-results/s2-load-run.png', fullPage: true })
})

test('S2: editing topology changes the simulation; removing an instrument fails explicitly', async ({ page, request }) => {
  const pid = await newProject(page, 'S2 עריכה')
  await openTab(page, 'ניסוי עומס')
  await expect(page.getByTestId('node-A2')).toBeVisible()

  // delete the load ammeter A2 (and its wires) → save → run → invalid circuit naming A2
  await page.getByTestId('node-A2').click()
  await expect(page.getByTestId('param-panel')).toContainText('A2')
  await page.getByTestId('delete-selected').click()
  await expect(page.getByTestId('dirty')).toBeVisible()
  await page.getByTestId('save-circuit').click()
  await expect(page.getByText('המעגל נשמר')).toBeVisible()

  const stored = await (await request.get(`/api/projects/${pid}/circuits/load`)).json()
  expect(stored.circuit.components.some((c: { id: string }) => c.id === 'A2')).toBe(false)

  await page.getByTestId('run-button').click()
  await expect(page.getByTestId('run-view').getByTestId('run-status')).toHaveAttribute('data-status', 'invalid_circuit')
  await expect(page.getByTestId('run-error')).toContainText('A2')

  // reload: the edited circuit persists
  await page.reload()
  await expect(page.getByTestId('node-W2')).toBeVisible()
  await expect(page.getByTestId('node-A2')).toHaveCount(0)

  // add a new ammeter and wire it by dragging between terminals
  await page.getByTestId('add-ammeter').click()
  await expect(page.getByTestId('node-A1')).toBeVisible()
  await page.getByTestId('h-A1-p').dragTo(page.getByTestId('h-W2-In'))
  await page.getByTestId('save-circuit').click()
  await expect(page.getByText('המעגל נשמר')).toBeVisible()
  const after = await (await request.get(`/api/projects/${pid}/circuits/load`)).json()
  const wired = after.circuit.wires.some(
    (w: { a: { component: string; terminal: string }; b: { component: string; terminal: string } }) =>
      [w.a, w.b].some((e) => e.component === 'A1' && e.terminal === 'p') &&
      [w.a, w.b].some((e) => e.component === 'W2' && e.terminal === 'In'),
  )
  expect(wired).toBe(true)

  // restore the manual's circuit and run successfully again
  await page.getByRole('button', { name: /טען מעגל לפי החוברת/ }).first().click()
  await expect(page.getByTestId('node-A2')).toBeVisible()
  await page.getByTestId('run-button').click()
  await expect(page.getByTestId('run-view').getByTestId('run-status')).toHaveAttribute('data-status', 'success')
})

test('S2: vector groups — clock number from topology', async ({ page }) => {
  await newProject(page, 'S2 שעון')
  await openTab(page, 'קבוצות חיבורים (שיטת השעון)')
  const expectations: [RegExp, string, string][] = [
    [/כוכב-כוכב, סדר a b c/, '0', '0'],
    [/כוכב-כוכב, סדר b c a/, '4', '4 או 8'],
    [/כוכב-משולש, סגירה x1→y2/, '11', '1 או 11'],
  ]
  for (const [btn, clock, cands] of expectations) {
    await page.getByRole('button', { name: btn }).click()
    await expect(page.getByTestId('node-VBb')).toBeVisible()
    await page.getByTestId('run-button').click()
    const view = page.getByTestId('run-view')
    await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', 'success')
    await expect(view.locator('[data-param="clock_true"] td[data-value]')).toHaveAttribute('data-value', clock)
    await expect(view.locator('[data-param="clock_candidates"]')).toContainText(cands)
  }
  await page.screenshot({ path: 'test-results/s2-vector-group.png', fullPage: true })
})

test('W1: the wiring check compares nets with the manual — a removed cable is reported', async ({ page }) => {
  await newProject(page, 'W1 בדיקת חיווט')
  await openTab(page, 'ניסוי עומס')
  await expect(page.getByTestId('node-T')).toBeVisible()
  await page.getByTestId('check-wiring').click()
  await expect(page.getByTestId('wiring-check')).toContainText('תואם לחוברת')
  // delete one cable and save
  await page.locator('.react-flow__edge').first().click()
  await page.getByTestId('delete-selected').click()
  await page.getByTestId('save-circuit').click()
  await expect(page.getByTestId('dirty')).toHaveCount(0)
  await page.getByTestId('check-wiring').click()
  await expect(page.getByTestId('wiring-check')).toContainText('חסר חיבור')
  await page.screenshot({ path: 'test-results/w1-wiring-check.png', fullPage: false })
})
