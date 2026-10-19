import { openTab } from './helpers'
import { expect, test } from '@playwright/test'

const IF = [0, 0.25, 0.5, 0.7, 0.97, 1.22, 1.47, 1.73, 1.96, 2.25, 2.5]
const EF = [5.4, 72.6, 138, 184, 237, 280, 308, 332, 348, 362, 371.5]

test('D3: synchronous machine — OCC vs the student table, three short circuits, field current on the 3D bench, V-curves', async ({
  page,
  request,
}) => {
  await page.goto('/')
  await page.getByPlaceholder(/קבוצה 3/).fill('D3 סינכרונית')
  await page.locator('select[name="experiment"]').selectOption('synchronous')
  await page.getByRole('button', { name: 'צור פרויקט' }).click()
  await expect(page.getByTestId('project-experiment')).toContainText('מכונה סינכרונית')
  const pid = page.url().split('/projects/')[1]!.split(/[/?]/)[0]!

  // open-circuit characteristic with the default (the student's) field currents
  await openTab(page, 'אופיין ריקם')
  await page.getByTestId('run-button').click()
  const view = page.getByTestId('run-view')
  await expect(view.getByTestId('run-status')).toHaveAttribute('data-status', 'success_with_warnings')
  await expect(view.getByTestId('run-warnings')).toContainText('ההיסטרזיס')
  await expect(view.getByRole('table', { name: /טבלה 6.3/ }).locator('tbody tr')).toHaveCount(11)
  await expect(view.locator('[data-param="E_res"]')).toContainText('5.44')

  // short circuits: three faults in one table, Xs extracted
  await openTab(page, /אופייני קצר/)
  await page.getByTestId('run-button').click()
  await expect(view.getByRole('table', { name: /טבלה 6.4/ })).toBeVisible()
  await expect(view.locator('[data-param="Xs"]')).toContainText('674.0')
  await page.screenshot({ path: 'test-results/d3-short-circuit.png', fullPage: true })

  // 3D bench on the open-circuit circuit: the field current drives the voltmeter
  await openTab(page, 'אופיין ריקם')
  await page.getByTestId('lab3d-section').locator('summary').click()
  await expect(page.getByTestId('lab3d').locator('canvas')).toBeVisible()
  await expect(page.getByTestId('reading-G')).toContainText('1500 rpm')
  const before = await page.getByTestId('reading-V1').textContent()
  await page.getByTestId('field').focus()
  await page.keyboard.press('End')
  await expect(page.getByTestId('reading-V1')).not.toHaveText(before ?? '')
  const ref = await (
    await request.post(`/api/projects/${pid}/circuits/open_circuit/operating-point`, { data: { overrides: { G: { I_f: 6 } } } })
  ).json()
  await expect(page.getByTestId('reading-V1')).toHaveText(`${ref.readings.V1.U.toFixed(1)} V`)
  await page.screenshot({ path: 'test-results/d3-3d.png' })

  // V-curves: grid-connected motor, out-of-step points are shown, not hidden
  await openTab(page, /אופייני V/)
  await page.locator('input[name="case-points"]').fill('0@2, 0@3, 0@4, 0@5, 135@0.4, 135@4')
  await page.getByTestId('run-button').click()
  const vt = view.getByRole('table', { name: /טבלה 6.7/ })
  await expect(vt.locator('tbody tr')).toHaveCount(6)
  await expect(vt.locator('tbody tr').nth(4)).toContainText('יצא מסנכרון')
  await expect(view.getByTestId('run-warnings')).toContainText('יוצאת מסנכרון')

  // the student's OCC entered as measured → simulate at those points → compare
  const set = await (
    await request.post(`/api/projects/${pid}/measurement-sets`, { data: { study_kind: 'open_circuit', label: 'טבלה 6.3', n_rows: 11 } })
  ).json()
  for (const [i, v] of IF.entries()) {
    await request.post(`/api/measurement-sets/${set.set.id}/entries`, { data: { row_index: i, quantity: 'If', value: v, unit: 'A' } })
    await request.post(`/api/measurement-sets/${set.set.id}/entries`, { data: { row_index: i, quantity: 'Ef_up', value: EF[i], unit: 'V' } })
  }
  const run = await (await request.post(`/api/measurement-sets/${set.set.id}/simulate`)).json()
  const cmp = await (await request.get(`/api/comparison?run_id=${run.id}&set_id=${set.set.id}`)).json()
  expect(cmp.summary.unmatched_rows).toBe(0)

  await openTab(page, 'אופיין ריקם')
  await openTab(page, 'מדידות מעבדה והשוואה')
  await expect(page.getByTestId('comparison')).toBeVisible()
  await expect(page.getByTestId('cmp-summary')).toContainText('ללא התאמה: 0')
  await page.screenshot({ path: 'test-results/d3-compare.png', fullPage: true })

  // spec form: OCC section
  await page.getByRole('link', { name: 'מפרט המכונה' }).click()
  await expect(page.locator('input[name="occ.a"]')).toHaveValue('156.36')
})
