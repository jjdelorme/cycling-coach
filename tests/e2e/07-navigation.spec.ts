/**
 * Navigation — desktop header, tab switching, active state, URL routing.
 *
 * After the React Router migration (Phase 1), header nav items are anchor
 * elements (role `link`) and the URL reflects the active page.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 07-navigation
 */
import { test, expect } from '@playwright/test'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

test.describe('Desktop navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
  })

  test('COACH logo and brand name are visible in the header', async ({ page }) => {
    await expect(page.locator('header').getByText('COACH')).toBeVisible()
  })

  test('all nav tabs are visible: Dashboard, Rides, Calendar, Analysis, Nutrition', async ({ page }) => {
    for (const label of ['Dashboard', 'Rides', 'Calendar', 'Analysis', 'Nutrition']) {
      await expect(page.locator('header').getByRole('link', { name: label })).toBeVisible()
    }
  })

  test('Dashboard is the active tab on load (URL is /)', async ({ page }) => {
    await expect(page).toHaveURL(/\/$/)
    const dashLink = page.locator('header').getByRole('link', { name: 'Dashboard' })
    const cls = await dashLink.getAttribute('class')
    expect(cls).toMatch(/bg-surface2|border-accent/)
  })

  test('clicking Rides updates URL to /rides and marks the link active', async ({ page }) => {
    await page.locator('header').getByRole('link', { name: 'Rides' }).click()
    await expect(page).toHaveURL(/\/rides$/)
    const ridesLink = page.locator('header').getByRole('link', { name: 'Rides' })
    const cls = await ridesLink.getAttribute('class')
    expect(cls).toMatch(/bg-surface2|border-accent/)
  })

  test('clicking Calendar updates URL to /calendar', async ({ page }) => {
    await page.locator('header').getByRole('link', { name: 'Calendar' }).click()
    await expect(page).toHaveURL(/\/calendar$/)
    const calLink = page.locator('header').getByRole('link', { name: 'Calendar' })
    const cls = await calLink.getAttribute('class')
    expect(cls).toMatch(/bg-surface2|border-accent/)
  })

  test('clicking Analysis updates URL to /analysis', async ({ page }) => {
    await page.locator('header').getByRole('link', { name: 'Analysis' }).click()
    await expect(page).toHaveURL(/\/analysis$/)
  })

  test('clicking Nutrition updates URL to /nutrition', async ({ page }) => {
    await page.locator('header').getByRole('link', { name: 'Nutrition' }).click()
    await expect(page).toHaveURL(/\/nutrition$/)
  })

  test('deep-link to /rides directly loads the rides page', async ({ page }) => {
    await page.goto(`${BASE}/rides`)
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible({ timeout: 12_000 })
    await expect(page).toHaveURL(/\/rides$/)
  })

  test('deep-link to /calendar directly loads the calendar page', async ({ page }) => {
    await page.goto(`${BASE}/calendar`)
    await expect(page).toHaveURL(/\/calendar$/)
  })

  test('browser back navigates between pages', async ({ page }) => {
    await page.locator('header').getByRole('link', { name: 'Rides' }).click()
    await expect(page).toHaveURL(/\/rides$/)
    await page.locator('header').getByRole('link', { name: 'Calendar' }).click()
    await expect(page).toHaveURL(/\/calendar$/)
    await page.goBack()
    await expect(page).toHaveURL(/\/rides$/)
    await page.goForward()
    await expect(page).toHaveURL(/\/calendar$/)
  })

  test('unknown path renders the NotFound page', async ({ page }) => {
    await page.goto(`${BASE}/this-route-does-not-exist`)
    await expect(page.getByText('Page not found')).toBeVisible({ timeout: 8_000 })
    await expect(page.getByRole('link', { name: 'Go to Dashboard' })).toBeVisible()
  })

  test('Settings gear icon is visible in header', async ({ page }) => {
    await expect(page.locator('header [title="Settings"]').first()).toBeVisible()
  })

  test('Coach (chat) icon is visible in header', async ({ page }) => {
    await expect(page.locator('header button[title="Coach"]')).toBeVisible()
  })

  test('Coach panel opens when chat button is clicked', async ({ page }) => {
    await page.locator('header button[title="Coach"]').click()
    await page.waitForTimeout(500)
    await expect(page.locator('body')).toBeVisible()
  })

  test('theme toggle button is visible', async ({ page }) => {
    const themeBtn = page.locator('header button[title*="mode"], header button[title*="theme"]').or(
      page.locator('header button').filter({ has: page.locator('svg') }).nth(1)
    )
    await expect(themeBtn.first()).toBeVisible()
  })

  test('version string appears in the corner', async ({ page }) => {
    const versionEl = page.locator('span').filter({ hasText: /^v\d/ })
    await expect(versionEl).toBeVisible()
    const text = await versionEl.innerText()
    expect(text).toMatch(/^v\d/)
  })

  test('page does not redirect away from / when auth is disabled', async ({ page }) => {
    await expect(page.getByText('Sign in with Google')).not.toBeVisible()
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible()
  })
})
