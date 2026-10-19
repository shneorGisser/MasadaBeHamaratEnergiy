import { existsSync } from 'node:fs'
import { defineConfig } from '@playwright/test'

/**
 * E2E runs against the real FastAPI backend serving the production build, with a throwaway
 * SQLite database. Build first: `npm run build`.
 */
const port = Number(process.env.VEL_E2E_PORT ?? 8765)
// Use a preinstalled Chromium when the pinned Playwright build is not downloaded (sandboxed CI).
const preinstalled = process.env.PW_CHROMIUM ?? '/opt/pw-browsers/chromium'
const executablePath = existsSync(preinstalled) ? preinstalled : undefined

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    locale: 'he-IL',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { executablePath },
  },
  webServer: {
    command: `bash ../scripts/serve-e2e.sh ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
