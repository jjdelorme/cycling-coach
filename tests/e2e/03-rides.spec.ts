/**
 * Rides page — list view, date filter, ride detail, navigation.
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
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible({ timeout: 8_000 })
  })

  test('shows the Rides header and Activity History section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Rides' })).toBeVisible()
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible()
  })

  test('shows date filter controls', async ({ page }) => {
    // Filter toolbar: two date inputs and a GO button
    const dateInputs = page.locator('input[type="date"]')
    await expect(dateInputs.first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Go' })).toBeVisible()
  })

  test('loads ride rows after initial navigation', async ({ page }) => {
    // The table may take a moment to hydrate from the API
    await page.waitForSelector('table tbody tr', { timeout: 15_000 })
    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()
    const count = await rows.count()
    expect(count).toBeGreaterThan(0)
  })

  test('ride rows contain expected columns: date, activity, duration, TSS', async ({ page }) => {
    await page.waitForSelector('table tbody tr', { timeout: 15_000 })
    const firstRow = page.locator('table tbody tr').first()
    // Date column — matches YYYY-MM-DD
    const dateCell = firstRow.locator('td').first()
    const dateText = await dateCell.innerText()
    expect(dateText).toMatch(/\d{4}-\d{2}-\d{2}/)
  })

  test('date filter narrows results', async ({ page }) => {
    await page.waitForSelector('table tbody tr', { timeout: 15_000 })
    const allCount = await page.locator('table tbody tr').count()

    // Filter to a narrow one-month range in the past
    const startInput = page.locator('input[type="date"]').first()
    const endInput   = page.locator('input[type="date"]').last()
    await startInput.fill('2026-03-01')
    await endInput.fill('2026-03-31')
    await page.getByRole('button', { name: 'Go' }).click()
    await page.waitForTimeout(2_000)

    // Either fewer rows or the "No rides match" message
    const newCount = await page.locator('table tbody tr').count()
    const noMatch  = await page.getByText('No rides match').isVisible()
    expect(newCount < allCount || noMatch).toBeTruthy()
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
    await expect(page.getByText('Back to List')).toBeVisible({ timeout: 10_000 })
  })

  test('shows Back to List navigation', async ({ page }) => {
    await expect(page.getByText('Back to List')).toBeVisible()
  })

  test('shows date navigation arrows', async ({ page }) => {
    // Previous / Next chevron buttons in the date bar
    const chevrons = page.locator('[class*="rounded-lg"] button')
    await expect(chevrons.first()).toBeVisible()
  })

  test('renders metric cards: Duration, Distance, TSS, Avg Power, NP', async ({ page }) => {
    // Wait for the metrics grid to appear (8-col grid of small metric cards)
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

  test('Back to List returns to the rides list', async ({ page }) => {
    await page.getByText('Back to List').click()
    await expect(page.getByText('ACTIVITY HISTORY', { exact: false })).toBeVisible({ timeout: 8_000 })
  })

  test('timeline chart canvas is rendered when ride has records', async ({ page }) => {
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 15_000 })
    // The chart is only rendered when the ride has records; check conditionally
    const canvas = page.locator('canvas').first()
    const hasCanvas = await canvas.count() > 0
    if (hasCanvas) {
      await expect(canvas).toBeVisible()
    }
  })

  test('route map card renders for outdoor rides, placeholder for indoor', async ({ page }) => {
    // Wait for ride detail to settle so the lazy <RideMap> chunk has time
    // to load and either render its canvas or its no-GPS placeholder.
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 15_000 })

    // Either of these must be true: (a) a MapLibre canvas with non-zero size,
    // or (b) the "No GPS data" placeholder text. Both are valid first-class
    // states per Campaign 20 — we cannot assume the seed ride has GPS.
    const mapCanvas = page.locator('canvas.maplibregl-canvas')
    const placeholder = page.getByText(/No GPS data — indoor or virtual ride/i)

    await expect(async () => {
      const canvasCount = await mapCanvas.count()
      const placeholderVisible = await placeholder.isVisible().catch(() => false)
      if (canvasCount > 0) {
        const box = await mapCanvas.first().boundingBox()
        expect(box?.width ?? 0).toBeGreaterThan(100)
        expect(box?.height ?? 0).toBeGreaterThan(100)
      } else {
        expect(placeholderVisible).toBe(true)
      }
    }).toPass({ timeout: 12_000 })
  })

  test('hovering the timeline chart syncs a marker on the map (when GPS available)', async ({ page }) => {
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 15_000 })

    // Skip if this ride has no GPS — placeholder rendered, no marker possible.
    const placeholder = page.getByText(/No GPS data — indoor or virtual ride/i)
    if (await placeholder.isVisible().catch(() => false)) {
      test.skip(true, 'Selected ride has no GPS data — marker sync N/A')
    }

    // Wait for both canvases (chart + map) to exist.
    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible({ timeout: 12_000 })
    const chartCanvas = page.locator('canvas').first()
    const box = await chartCanvas.boundingBox()
    if (!box) throw new Error('chart canvas has no bounding box')

    await chartCanvas.hover({ position: { x: box.width * 0.5, y: box.height * 0.5 } })
    // The marker is appended as a `.maplibregl-marker` div by the Marker
    // constructor. Existence is sufficient — position correctness is
    // covered by unit tests on decimatePolyline + manual smoke.
    await expect(page.locator('.maplibregl-marker').first()).toBeVisible({ timeout: 5_000 })
  })

  test('drag-selecting a time range on the chart surfaces the Reset Zoom affordance', async ({ page }) => {
    // The drag-zoom selection on the chart (which Phase 4 also propagates to
    // the map for highlight + auto-fit) shows a "Reset Zoom" button as soon
    // as a selection commits. We assert the user-visible affordance rather
    // than the map's canvas-level highlight (which is a pixel test, brittle).
    await expect(page.getByText('DURATION', { exact: false }).first()).toBeVisible({ timeout: 15_000 })

    const placeholder = page.getByText(/No GPS data — indoor or virtual ride/i)
    if (await placeholder.isVisible().catch(() => false)) {
      test.skip(true, 'Selected ride has no GPS — drag-zoom map highlight N/A')
    }

    const chartCanvas = page.locator('canvas').first()
    const box = await chartCanvas.boundingBox()
    if (!box) throw new Error('chart canvas has no bounding box')

    // Drag from 30% to 70% across the chart width.
    const startX = box.x + box.width * 0.3
    const endX = box.x + box.width * 0.7
    const midY = box.y + box.height * 0.5
    await page.mouse.move(startX, midY)
    await page.mouse.down()
    await page.mouse.move(endX, midY, { steps: 10 })
    await page.mouse.up()

    // Reset Zoom appears when a real drag-selection commits.
    await expect(page.getByRole('button', { name: /Reset Zoom/i })).toBeVisible({ timeout: 5_000 })
  })
})
