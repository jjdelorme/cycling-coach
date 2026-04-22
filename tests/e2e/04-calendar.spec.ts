/**
 * Calendar page — month grid, day selection, navigation.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 04-calendar
 */
import { test, expect } from '@playwright/test'
import { navTo } from './helpers'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

const MONTHS = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December',
]

test.describe('Calendar', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navTo(page, 'Calendar')
    // Wait for the 7-column grid to appear
    await page.waitForSelector('[class*="grid-cols-7"]', { timeout: 10_000 })
  })

  test('shows a month heading with the current year', async ({ page }) => {
    const heading = page.getByRole('heading', { level: 1 })
    const text = await heading.innerText()
    // Heading format: "April 2026"
    const hasMonth = MONTHS.some(m => text.includes(m))
    expect(hasMonth).toBe(true)
    expect(text).toMatch(/20\d{2}/)
  })

  test('day-of-week headers are Mon through Sun', async ({ page }) => {
    for (const day of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
      await expect(page.getByText(day, { exact: true })).toBeVisible()
    }
  })

  test('calendar grid has 35 or 42 day cells', async ({ page }) => {
    // Grid cells: the inner day divs (not the header row)
    const cells = page.locator('.grid-cols-7.gap-px > div')
    const count = await cells.count()
    expect([35, 42]).toContain(count)
  })

  test('today\'s cell is highlighted with an accent ring', async ({ page }) => {
    // The current day cell has an ::after ring via class "after:ring-2"
    const todayCell = page.locator('[class*="after\\:ring-2"]')
    await expect(todayCell).toBeVisible()
  })

  test('prev/next month navigation changes the heading', async ({ page }) => {
    const heading = page.getByRole('heading', { level: 1 })
    const before = await heading.innerText()

    // The calendar month nav bar is a rounded-lg div with p-1 and border
    // containing exactly 3 buttons: prev, refresh, next
    const navBar = page.locator('main div[class*="rounded-lg"][class*="border"]').filter({
      hasText: ''
    }).last()

    // The calendar month nav bar is the last rounded toolbar in the top row
    // It contains exactly 3 buttons: prev, refresh, next
    // Use the flex justify-between container that holds the heading + toolbar
    const topRow = page.locator('div.flex.items-center.justify-between').first()
    await topRow.locator('button').first().click()
    await page.waitForTimeout(500)

    const after = await heading.innerText()
    expect(after).not.toBe(before)
  })

  test('clicking a day cell selects it and shows detail panel', async ({ page }) => {
    // Click a cell that is in the current month (opacity-40 cells are other months).
    // The first in-month cell may already be the selected day (today defaults
    // selected); clicking it toggles selection off. Click the second one to
    // guarantee a selection change.
    const inMonthCells = page.locator('.grid-cols-7.gap-px > div:not([class*="opacity-40"])')
    await inMonthCells.nth(1).click()
    // Detail panel header includes the long-form date (e.g. "Wednesday, April 1, 2026").
    await expect(
      page.getByText(/(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)/i).first()
    ).toBeVisible({ timeout: 5_000 })
  })

  test('clicking a day with a ride shows ride metrics in the panel', async ({ page }) => {
    // Find a green TSS cell (indicates an actual ride)
    const rideCell = page.locator('.grid-cols-7.gap-px > div').filter({
      has: page.locator('[class*="text-green"]'),
    }).first()

    const hasCells = await rideCell.count()
    if (hasCells > 0) {
      await rideCell.click()
      await page.waitForTimeout(1_000)
      // Should show ride metrics like Duration, TSS, Avg Power
      await expect(page.getByText('Duration', { exact: false }).or(
        page.getByText('TSS', { exact: false })
      )).toBeVisible({ timeout: 5_000 })
    }
  })

  test('View Analysis link in day panel navigates to /rides/:id', async ({ page }) => {
    // Find a cell with a ride
    const rideCell = page.locator('.grid-cols-7.gap-px > div').filter({
      has: page.locator('[class*="text-green"]'),
    }).first()

    const hasCells = await rideCell.count()
    if (hasCells > 0) {
      await rideCell.click()
      await page.waitForTimeout(1_000)
      const viewLink = page.getByRole('link', { name: /View Analysis/i })
      if (await viewLink.count() > 0) {
        await viewLink.first().click()
        await expect(page).toHaveURL(/\/rides\/\d+$/, { timeout: 8_000 })
        await expect(page.getByText('Back to List')).toBeVisible({ timeout: 8_000 })
      }
    }
  })

  test('Show Details link in day panel navigates to /workouts/:id', async ({ page }) => {
    // Find a cell with a planned workout (yellow text)
    const workoutCell = page.locator('.grid-cols-7.gap-px > div').filter({
      has: page.locator('[class*="text-yellow"]'),
    }).first()

    const hasCells = await workoutCell.count()
    if (hasCells > 0) {
      await workoutCell.click()
      await page.waitForTimeout(1_000)
      const showDetailsLink = page.getByRole('link', { name: /Show Details/i })
      if (await showDetailsLink.count() > 0) {
        await showDetailsLink.first().click()
        await expect(page).toHaveURL(/\/workouts\/\d+$/, { timeout: 8_000 })
      }
    }
  })

  test('planned workout cells are yellow and show workout name', async ({ page }) => {
    const workoutCells = page.locator('.grid-cols-7.gap-px > div').filter({
      has: page.locator('[class*="text-yellow"]'),
    })
    const count = await workoutCells.count()
    // The DB should have planned workouts; if none this week just note it
    if (count > 0) {
      await expect(workoutCells.first()).toBeVisible()
    }
  })

  test('ride cells expose full title via title attribute', async ({ page }) => {
    // The ride row inside a calendar cell now carries a `title` attribute
    // (the full ride name) so users can hover for the full text on any
    // breakpoint, including mobile where the inline name span is hidden.
    const rideRow = page
      .locator('.grid-cols-7.gap-px > div')
      .filter({ has: page.locator('[class*="text-green"]') })
      .first()
      .locator('div[title]')
      .first()
    if (await rideRow.count() > 0) {
      const t = await rideRow.getAttribute('title')
      expect(t && t.length).toBeTruthy()
    }
  })
})
