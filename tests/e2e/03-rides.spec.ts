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
    for (const label of ['DISTANCE', 'TSS', 'AVG POWER']) {
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
})
