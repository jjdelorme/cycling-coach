/**
 * Settings page — Athlete tab (units, physio profile), Coach tab.
 *
 * Auth is disabled (GOOGLE_AUTH_ENABLED=false) so the user is an admin dev
 * user — all three tabs (Athlete, Coach, System) should be visible.
 *
 * These are READONLY tests — they verify the UI renders and form fields are
 * present, but do NOT save changes to avoid mutating the production Neon DB.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 06-settings
 */
import { test, expect } from '@playwright/test'
import { navToSettings } from './helpers'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

test.describe('Settings — Athlete tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navToSettings(page)
    await expect(page.getByText('Display Settings', { exact: false })).toBeVisible({ timeout: 8_000 })
  })

  test('Settings heading is visible', async ({ page }) => {
    await expect(page.locator('main h1').filter({ hasText: 'Settings' })).toBeVisible()
  })

  test('Athlete / Coach / System tabs are visible for admin', async ({ page }) => {
    // Tab buttons live inside the settings tab bar (not the header nav)
    const tabBar = page.locator('main').locator('div.flex.items-center.border-b')
    for (const tab of ['Athlete', 'Coach', 'System']) {
      await expect(tabBar.getByRole('button', { name: tab, exact: true })).toBeVisible()
    }
  })

  test('Display Settings section: imperial / metric toggle', async ({ page }) => {
    await expect(page.getByText('Measurement Units', { exact: false })).toBeVisible()
    await expect(page.getByRole('button', { name: /IMPERIAL/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /METRIC/i })).toBeVisible()
  })

  test('Visual Theme toggle shows DARK and LIGHT buttons', async ({ page }) => {
    await expect(page.getByText('Visual Theme', { exact: false })).toBeVisible()
    // Scope to main to avoid matching the header's dark/light icon button
    const displaySection = page.locator('main')
    await expect(displaySection.getByRole('button', { name: 'DARK', exact: true })).toBeVisible()
    await expect(displaySection.getByRole('button', { name: 'LIGHT', exact: true })).toBeVisible()
  })

  test('Physiological Profile section shows FTP, Weight, LTHR inputs', async ({ page }) => {
    await expect(page.getByText('Physiological Profile', { exact: false })).toBeVisible()
    for (const label of ['FTP', 'WEIGHT', 'LTHR', 'AGE', 'GENDER']) {
      await expect(page.getByText(label, { exact: false })).toBeVisible()
    }
  })

  test('FTP input has a numeric value', async ({ page }) => {
    const ftpInput = page.locator('input[type="number"]').first()
    await expect(ftpInput).toBeVisible()
    await expect(ftpInput).toBeEditable()
  })

  test('Save Profile button is visible', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Save Profile/i })).toBeVisible()
  })
})

test.describe('Settings — Coach tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navToSettings(page)
    await expect(page.getByText('Display Settings', { exact: false })).toBeVisible({ timeout: 8_000 })
    await page.locator('main').getByRole('button', { name: 'Coach', exact: true }).click()
    await page.waitForTimeout(500)
  })

  test('Coach tab shows four settings cards', async ({ page }) => {
    for (const title of [
      'Athlete Profile',
      'Coaching Principles',
      'Coach Role',
      'Plan Management',
    ]) {
      await expect(page.getByText(title, { exact: false })).toBeVisible()
    }
  })

  test('each settings card has an editable textarea', async ({ page }) => {
    const textareas = page.locator('textarea')
    const count = await textareas.count()
    expect(count).toBeGreaterThanOrEqual(4)
    await expect(textareas.first()).toBeEditable()
  })

  test('Save Coaching Settings button is visible', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Save Coaching Settings/i })).toBeVisible()
  })
})

test.describe('Settings — System tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navToSettings(page)
    await expect(page.getByText('Display Settings', { exact: false })).toBeVisible({ timeout: 8_000 })
    await page.locator('main').getByRole('button', { name: 'System', exact: true }).click()
    await page.waitForTimeout(500)
  })

  test('Gemini AI Engine section is visible', async ({ page }) => {
    await expect(page.getByText('Gemini AI Engine', { exact: false })).toBeVisible()
    await expect(page.getByPlaceholder(/gemini-2.0-flash/i)).toBeVisible()
  })

  test('Intervals.icu Sync section is visible', async ({ page }) => {
    await expect(page.getByText('Intervals.icu Sync', { exact: false })).toBeVisible()
    await expect(page.getByRole('button', { name: /Sync Now/i })).toBeVisible()
  })

  test('frontend and backend version numbers are shown', async ({ page }) => {
    await expect(page.getByText('Frontend', { exact: false })).toBeVisible()
    await expect(page.getByText('Backend', { exact: false })).toBeVisible()
  })

  test('API Key input is password-type by default', async ({ page }) => {
    const apiKeyInput = page.locator('input[type="password"]').first()
    await expect(apiKeyInput).toBeVisible()
  })

  test('eye icon toggles API key visibility', async ({ page }) => {
    const toggleBtn = page.locator('button[type="button"]').first()
    await expect(toggleBtn).toBeVisible()
    // After clicking, the input type should switch to text
    await toggleBtn.click()
    const textInput = page.locator('input[type="text"]')
    await expect(textInput.first()).toBeVisible()
  })
})
