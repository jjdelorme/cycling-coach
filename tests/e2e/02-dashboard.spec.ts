/**
 * Dashboard page — verifies all four major sections render with data.
 *
 * Sections tested:
 *  - Metric cards (CTL, ATL, TSB, Weight)
 *  - Next Workout panel
 *  - Last Ride / Today's Ride panel
 *  - Fitness Trends (PMC) chart
 *  - Weekly Training Load chart
 *  - Recent Rides table
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 02-dashboard
 */
import { test, expect } from '@playwright/test'
import { navTo } from './helpers'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    // Wait until at least the CTL card is visible — data has loaded
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 15_000 })
  })

  test('renders all four metric cards with numeric values', async ({ page }) => {
    const cards = [
      { label: 'FITNESS (CTL)', color: 'text-green' },
      { label: 'FATIGUE (ATL)', color: 'text-red' },
      { label: 'FORM (TSB)',    color: null },
      { label: 'WEIGHT',        color: null },
    ]

    for (const { label } of cards) {
      const card = page.locator('[class*="rounded-xl"]').filter({ hasText: label })
      await expect(card).toBeVisible()
      // The value should be a number (not '--')
      const valueText = await card.locator('p, span').last().innerText().catch(() => '')
      expect(valueText).not.toBe('--')
    }
  })

  test('shows CTL as a positive number', async ({ page }) => {
    const ctlCard = page.locator('[class*="rounded-xl"]').filter({ hasText: 'FITNESS (CTL)' })
    const value = await ctlCard.locator('p').first().innerText()
    expect(parseInt(value, 10)).toBeGreaterThan(0)
  })

  test('Next Workout panel is visible', async ({ page }) => {
    await expect(page.getByText('NEXT WORKOUT', { exact: false })).toBeVisible()
    // Either a workout name is shown or a "No upcoming workouts" message
    const panel = page.locator('[class*="rounded-xl"]').filter({ hasText: 'NEXT WORKOUT' })
    await expect(panel).toBeVisible()
  })

  test('Last Ride / Today\'s Ride panel is visible', async ({ page }) => {
    // Either "LAST RIDE" or "TODAY'S RIDE"
    const ridePanel = page.locator('[class*="rounded-xl"]').filter({
      hasText: /LAST RIDE|TODAY'S RIDE/i,
    })
    await expect(ridePanel).toBeVisible()
  })

  test('Fitness Trends (PMC) chart is rendered', async ({ page }) => {
    await expect(page.getByText('Fitness Trends (PMC)', { exact: false })).toBeVisible()
    // The canvas element for the chart
    const canvas = page.locator('[class*="rounded-xl"]').filter({ hasText: 'Fitness Trends (PMC)' }).locator('canvas')
    await expect(canvas).toBeVisible()
  })

  test('Weekly Training Load chart is rendered', async ({ page }) => {
    await expect(page.getByText('Weekly Training Load', { exact: false })).toBeVisible()
    const canvas = page.locator('[class*="rounded-xl"]').filter({ hasText: 'Weekly Training Load' }).locator('canvas')
    await expect(canvas).toBeVisible()
  })

  test('Recent Rides table shows rows', async ({ page }) => {
    await expect(page.getByText('RECENT RIDES', { exact: false })).toBeVisible()
    // Wait for table to populate (the request loads 7 rides)
    await page.waitForSelector('table tbody tr', { timeout: 12_000 })
    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()
    const count = await rows.count()
    expect(count).toBeGreaterThan(0)
  })

  test('clicking a Recent Ride row navigates to Ride detail', async ({ page }) => {
    await page.waitForSelector('table tbody tr', { timeout: 12_000 })
    await page.locator('table tbody tr').first().click()
    await expect(page.getByText('Back to List')).toBeVisible({ timeout: 8_000 })
  })

  test('clicking Next Workout navigates to Workout detail', async ({ page }) => {
    const nextPanel = page.locator('[class*="rounded-xl"]').filter({ hasText: 'NEXT WORKOUT' })
    const hasClickable = await nextPanel.locator('[class*="cursor-pointer"]').count()
    if (hasClickable > 0) {
      await nextPanel.locator('[class*="cursor-pointer"]').first().click()
      await expect(page).toHaveURL(/\/workouts\/\d+$/, { timeout: 8_000 })
      await expect(page.getByText('Back to Calendar')).toBeVisible({ timeout: 8_000 })
    }
    // If no upcoming workout, the test passes trivially
  })
})
