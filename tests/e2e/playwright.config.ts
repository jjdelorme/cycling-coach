import { defineConfig, devices } from '@playwright/test'

/**
 * E2E test configuration for cycling-coach.
 *
 * Assumes the application is already running at BASE_URL.
 * Start the app with:
 *   source venv/bin/activate && uvicorn server.main:app --host 0.0.0.0 --port 8080
 *
 * Run tests:
 *   npx playwright test --config tests/e2e/playwright.config.ts
 */

const BASE_URL = process.env.BASE_URL || 'http://localhost:8080'

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  retries: 1,
  workers: 1,
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: BASE_URL,
    screenshot: 'only-on-failure',
    video: 'off',
    trace: 'off',
    // Auth is disabled (GOOGLE_AUTH_ENABLED=false), so no login needed
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Do not start a local server — app must already be running
  // webServer: undefined,
})
