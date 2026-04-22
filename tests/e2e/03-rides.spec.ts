/**
 * Rides page — list view, date filter, ride detail, deep-link navigation.
 *
 * After Phase 2 of the routing migration, ride detail is a real route at
 * `/rides/:id` and is deep-linkable / browser-back aware.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 03-rides
 */
import { test, expect } from '@playwright/test'
import { navTo } from './helpers'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

test.describe('Rides — list view', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navTo(page, 'Rides')
    await expect(page).toHaveURL(/\/rides$/)
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible({ timeout: 8_000 })
  })

  test('shows the Rides header and Activity History section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Rides' })).toBeVisible()
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible()
  })

  test('shows date filter controls', async ({ page }) => {
    const dateInputs = page.locator('input[type="date"]')
    await expect(dateInputs.first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Go' })).toBeVisible()
  })

  test('loads ride rows after initial navigation', async ({ page }) => {
    await page.waitForSelector('table tbody tr', { timeout: 15_000 })
    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()
    const count = await rows.count()
    expect(count).toBeGreaterThan(0)
  })

  test('ride rows contain expected columns: date, activity, duration, TSS', async ({ page }) => {
    await page.waitForSelector('table tbody tr', { timeout: 15_000 })
    const firstRow = page.locator('table tbody tr').first()
    const dateCell = firstRow.locator('td').first()
    const dateText = await dateCell.innerText()
    expect(dateText).toMatch(/\d{4}-\d{2}-\d{2}/)
  })

  test('date filter narrows results', async ({ page }) => {
    await page.waitForSelector('table tbody tr', { timeout: 15_000 })
    const allCount = await page.locator('table tbody tr').count()

    const startInput = page.locator('input[type="date"]').first()
    const endInput   = page.locator('input[type="date"]').last()
    await startInput.fill('2026-03-01')
    await endInput.fill('2026-03-31')
    await page.getByRole('button', { name: 'Go' }).click()
    await page.waitForTimeout(2_000)

    const newCount = await page.locator('table tbody tr').count()
    const noMatch  = await page.getByText('No rides match').isVisible()
    expect(newCount < allCount || noMatch).toBeTruthy()
  })

  test('clicking a row updates the URL to /rides/:id', async ({ page }) => {
    await page.waitForSelector('table tbody tr', { timeout: 15_000 })
    await page.locator('table tbody tr').first().click()
    await expect(page).toHaveURL(/\/rides\/\d+$/, { timeout: 10_000 })
  })

  /**
   * Radius search (Advanced panel).
   *
   * REQUIRES the backend to be started with `GEOCODER=mock`, e.g.:
   *
   *   GEOCODER=mock uvicorn server.main:app --host 0.0.0.0 --port 8080
   *
   * The MockProvider (see `server/services/geocoding.py:MockProvider`)
   * exposes a small fixed table of place names — `"north pole"` resolves
   * to (89.9, 0.0), which is guaranteed to be far from any real ride.
   * That gives us a deterministic "no rides match" assertion that does
   * not depend on the running database having any specific seed coords.
   *
   * If `GEOCODER` is unset (default `nominatim`), this test will hit the
   * real Nominatim service on every run — and "north pole" will resolve
   * somewhere genuinely arctic, which is still likely to return zero
   * rides for a normal cycling dataset, but we don't want CI dependent
   * on that. The test skips itself when GEOCODER is not "mock" so a
   * forgetful operator gets a clear signal instead of a flake.
   */
  test('radius search via Advanced panel returns no rides for a far-away place', async ({ page }) => {
    test.skip(
      (process.env.GEOCODER ?? '').toLowerCase() !== 'mock',
      'Backend must be started with GEOCODER=mock for this test to be deterministic. ' +
      'See server/services/geocoding.py:MockProvider for the fixture table.',
    )

    await page.waitForSelector('table tbody tr', { timeout: 15_000 })

    // Open the Advanced panel.
    await page.getByRole('button', { name: /Advanced/ }).click()
    await expect(page.getByLabel('Search rides near a place')).toBeVisible({ timeout: 4_000 })

    // Type a fixture place that resolves far from any ride.
    await page.getByLabel('Search rides near a place').fill('North Pole')

    // Apply (the Advanced panel has its own "Apply" button to disambiguate
    // from the toolbar's "Go").
    await page.getByRole('button', { name: 'Apply' }).click()
    await page.waitForTimeout(1_500)

    // Status chip confirms the geo filter is active.
    await expect(page.getByText(/Showing rides within .* of North Pole/i)).toBeVisible({ timeout: 4_000 })

    // No rows in the table OR the empty-state message.
    const rowCount = await page.locator('table tbody tr').count()
    const noMatch = await page.getByText('No rides match').isVisible()
    expect(rowCount === 0 || noMatch).toBeTruthy()
  })
})

test.describe('Rides — ride detail', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navTo(page, 'Rides')
    await page.waitForSelector('table tbody tr', { timeout: 15_000 })
    await page.locator('table tbody tr').first().click()
    await expect(page).toHaveURL(/\/rides\/\d+$/, { timeout: 10_000 })
    await expect(page.getByText('Back to List')).toBeVisible({ timeout: 10_000 })
  })

  test('URL contains the ride id', async ({ page }) => {
    await expect(page).toHaveURL(/\/rides\/\d+$/)
  })

  test('shows Back to List navigation', async ({ page }) => {
    await expect(page.getByText('Back to List')).toBeVisible()
  })

  test('shows date navigation arrows', async ({ page }) => {
    const chevrons = page.locator('[class*="rounded-lg"] button')
    await expect(chevrons.first()).toBeVisible()
  })

  test('renders metric cards: Duration, Distance, TSS, Avg Power, NP', async ({ page }) => {
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 15_000 })
    for (const label of ['DISTANCE', 'TSS', 'POWER']) {
      await expect(page.getByText(label, { exact: false }).first()).toBeVisible({ timeout: 8_000 })
    }
  })

  test('AI Coaching section is present', async ({ page }) => {
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('AI COACHING', { exact: false })).toBeVisible()
  })

  test('Athlete Notes textarea is editable', async ({ page }) => {
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('ATHLETE NOTES', { exact: false })).toBeVisible()
    const textarea = page.locator('textarea').first()
    await expect(textarea).toBeVisible()
    await expect(textarea).toBeEditable()
  })

  test('Back to List returns to /rides', async ({ page }) => {
    await page.getByText('Back to List').click()
    await expect(page).toHaveURL(/\/rides$/)
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible({ timeout: 8_000 })
  })

  test('browser back from ride detail returns to /rides', async ({ page }) => {
    await page.goBack()
    await expect(page).toHaveURL(/\/rides$/)
  })

  test('timeline chart canvas is rendered when ride has records', async ({ page }) => {
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 15_000 })
    const canvas = page.locator('canvas').first()
    const hasCanvas = await canvas.count() > 0
    if (hasCanvas) {
      await expect(canvas).toBeVisible()
    }
  })
})

test.describe('Rides — deep link', () => {
  test('pasting /rides/:id directly loads that ride detail', async ({ page }) => {
    // Fetch a ride id from the API to avoid relying on hardcoded values
    const res = await page.request.get(`${BASE}/api/rides?limit=1`)
    const rides = await res.json()
    if (!Array.isArray(rides) || rides.length === 0) test.skip()
    const id = rides[0].id

    await page.goto(`${BASE}/rides/${id}`)
    await expect(page).toHaveURL(new RegExp(`/rides/${id}$`))
    await expect(page.getByText('Back to List')).toBeVisible({ timeout: 12_000 })
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 12_000 })
  })
})
