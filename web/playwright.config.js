import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:18081',
    browserName: 'chromium',
    channel: 'chrome',
    headless: true,
    viewport: { width: 1440, height: 1000 }
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:18081',
    timeout: 30_000,
    reuseExistingServer: !process.env.CI
  }
})
