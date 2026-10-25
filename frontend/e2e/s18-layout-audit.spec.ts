import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { audit } from './layout'

interface Study {
  kind: string
  title_he: string
  editable_circuit: boolean
}

const EXPERIMENTS = ['transformer3ph', 'induction_motor', 'synchronous', 'wound_rotor', 'dc_motor', 'dc_generator']

for (const exp of EXPERIMENTS) {
  test(`L1 ${exp}: every template schematic is drawn without wires through components or merged nets`, async ({ page }) => {
    test.setTimeout(180_000)
    const p = await page.request.post('/api/projects', { data: { name: `L1 ${exp}`, experiment_id: exp } })
    const pid = (await p.json()).id as string
    const studies = (await (await page.request.get(`/api/projects/${pid}/studies`)).json()) as Study[]
    await page.goto(`/projects/${pid}`)
    const report: string[] = []
    for (const s of studies.filter((x) => x.editable_circuit)) {
      const tab = page.getByRole('tab', { name: s.title_he, exact: true })
      await tab.click()
      await expect(tab).toHaveAttribute('aria-selected', 'true')
      await expect(page.getByTestId('export-dxf')).toBeVisible()
      await page.waitForTimeout(300) // let React Flow measure the handles
      const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('export-dxf').click()])
      const text = readFileSync((await dl.path())!, 'utf8')
      for (const v of audit(text)) report.push(`${s.kind}: [${v.rule}] ${v.text}`)
    }
    expect(report, report.join('\n')).toEqual([])
  })
}
