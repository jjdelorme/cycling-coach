/**
 * Breadcrumbs — Campaign 18 Phase 5.
 *
 * Verifies that the breadcrumb nav renders on non-root pages, links to
 * ancestors, and is hidden on the dashboard.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 11-breadcrumbs
 */
import { test, expect } from '@playwright/test'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

test.describe('Breadcrumbs', () => {
  test('no breadcrumb is rendered on the dashboard ("/")', async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    const crumbs = page.locator('nav[aria-label="breadcrumb"]')
    await expect(crumbs).toHaveCount(0)
  })

  test('breadcrumb on /rides shows Dashboard > Rides', async ({ page }) => {
    await page.goto(`${BASE}/rides`)
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible({ timeout: 12_000 })
    const crumb = page.locator('nav[aria-label="breadcrumb"]').first()
    await expect(crumb).toBeVisible()
    await expect(crumb.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    // The leaf is plain text (aria-current="page"), not a link.
    await expect(crumb.locator('[aria-current="page"]')).toContainText('Rides')
  })

  test('clicking the parent crumb on /rides navigates back to /', async ({ page }) => {
    await page.goto(`${BASE}/rides`)
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible({ timeout: 12_000 })
    await page.locator('nav[aria-label="breadcrumb"]').first().getByRole('link', { name: 'Dashboard' }).click()
    await expect(page).toHaveURL(/\/$/)
  })

  test('breadcrumb on a ride detail page shows three levels', async ({ page }) => {
    // Navigate to /rides first to find an actual ride id.
    await page.goto(`${BASE}/rides`)
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible({ timeout: 12_000 })

    // Click the first ride row (or skip the test if none exist in this DB).
    const firstRideLink = page.locator('a[href^="/rides/"]').first()
    const count = await firstRideLink.count()
    if (count === 0) {
      test.skip(true, 'No rides in the dev DB; cannot exercise /rides/:id breadcrumb')
      return
    }
    await firstRideLink.click()
    await expect(page).toHaveURL(/\/rides\/\d+$/, { timeout: 8_000 })

    const crumb = page.locator('nav[aria-label="breadcrumb"]').first()
    await expect(crumb).toBeVisible()
    // Dashboard and Rides are links, leaf is the ride.
    await expect(crumb.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    await expect(crumb.getByRole('link', { name: 'Rides' })).toBeVisible()
    // The leaf is the dynamic crumb (ride title) or `#<id>` while loading.
    await expect(crumb.locator('[aria-current="page"]')).toBeVisible()
  })
})
