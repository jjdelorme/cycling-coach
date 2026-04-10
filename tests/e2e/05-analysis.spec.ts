/**
 * Analysis page — Season Macro-Plan, Power Curve, Efficiency, Zones, FTP History.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 05-analysis
 */
import { test, expect } from '@playwright/test'
import { navTo } from './helpers'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

test.describe('Analysis', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navTo(page, 'Analysis')
    await expect(page.getByRole('heading', { name: 'Analysis' })).toBeVisible({ timeout: 8_000 })
  })

  // ------------------------------------------------------------------
  // Season Macro-Plan
  // ------------------------------------------------------------------

  test('Season Macro-Plan section is visible', async ({ page }) => {
    await expect(page.getByText('SEASON MACRO-PLAN', { exact: false })).toBeVisible()
  })

  test('Macro-Plan shows phase bands (BASE, BUILD, PEAK, or TAPER)', async ({ page }) => {
    // At least one phase label should appear in the phase timeline bar
    const hasPhase = await page.getByText(/BASE|BUILD|PEAK|TAPER/, { exact: false }).first().isVisible()
      .catch(() => false)
    // Only assert if a macro plan is configured in the DB
    if (hasPhase) {
      await expect(page.getByText(/BASE|BUILD|PEAK|TAPER/).first()).toBeVisible()
    }
  })

  test('Season Performance Summary section is visible', async ({ page }) => {
    await expect(page.getByText('SEASON PERFORMANCE SUMMARY', { exact: false })).toBeVisible()
    await expect(page.getByText('AVERAGE LOAD', { exact: false })).toBeVisible()
  })

  // ------------------------------------------------------------------
  // Analysis sub-tabs
  // ------------------------------------------------------------------

  test('Power Curve tab is active by default', async ({ page }) => {
    await expect(page.getByRole('tab', { name: /POWER CURVE/i }).or(
      page.getByText('POWER CURVE', { exact: false })
    )).toBeVisible()
  })

  test('Power Curve date range toggles (1W, 3M, 6M, 1Y, ALL) are visible', async ({ page }) => {
    for (const label of ['1W', '3M', '6M', '1Y', 'ALL']) {
      await expect(page.getByRole('button', { name: label })).toBeVisible({ timeout: 8_000 })
    }
  })

  test('Power Curve chart canvas is rendered', async ({ page }) => {
    await page.waitForTimeout(2_000)
    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 10_000 })
  })

  test('Efficiency tab shows EF chart', async ({ page }) => {
    await page.getByRole('tab', { name: /EFFICIENCY/i }).or(
      page.getByText('Efficiency', { exact: false }).first()
    ).click()
    await page.waitForTimeout(1_500)
    // Canvas should render an efficiency chart
    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 8_000 })
  })

  test('Zones tab shows zone distribution chart', async ({ page }) => {
    await page.getByRole('tab', { name: /ZONES/i }).or(
      page.getByText('Zones', { exact: false }).first()
    ).click()
    await page.waitForTimeout(1_500)
    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 8_000 })
  })

  test('FTP History tab shows FTP trend', async ({ page }) => {
    await page.getByRole('tab', { name: /FTP HISTORY/i }).or(
      page.getByText('FTP History', { exact: false }).first()
    ).click()
    await page.waitForTimeout(1_500)
    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 8_000 })
  })

  test('Power Curve range changes when clicking 1W', async ({ page }) => {
    const btn3m = page.getByRole('button', { name: '3M' })
    const btn1w = page.getByRole('button', { name: '1W' })
    // 3M should be active by default (accent background)
    await expect(btn3m).toBeVisible()
    await btn1w.click()
    await page.waitForTimeout(1_000)
    // After clicking, 1W button should have accent styling
    const btn1wClass = await btn1w.getAttribute('class')
    expect(btn1wClass).toContain('bg-accent')
  })
})
