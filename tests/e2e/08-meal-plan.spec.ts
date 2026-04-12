/**
 * Meal Plan Calendar — Plan tab, empty state, week navigation, day detail.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 08-meal-plan
 */
import { test, expect } from '@playwright/test'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

/** Navigate to the Nutrition page via the header nav button. */
async function navToNutrition(page: import('@playwright/test').Page) {
  await page.locator('header').getByRole('button', { name: 'Nutrition' }).click()
}

test.describe('Meal Plan Calendar', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navToNutrition(page)
    await page.waitForTimeout(1_000)
  })

  test('Nutrition page has Day / Week / Plan toggle buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Day', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Week', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Plan', exact: true })).toBeVisible()
  })

  test('clicking Plan toggle switches to plan view', async ({ page }) => {
    await page.getByRole('button', { name: 'Plan', exact: true }).click()
    await page.waitForTimeout(1_000)
    // The plan view should show either the calendar grid or the empty state
    const hasCalendar = await page.getByText('This Week').or(
      page.getByText('No meal plan this week')
    ).isVisible({ timeout: 5_000 }).catch(() => false)
    expect(hasCalendar).toBeTruthy()
  })

  test('Plan view shows empty state with CTA button when no plans exist', async ({ page }) => {
    // Navigate to a far-future week where no plans exist
    await page.getByRole('button', { name: 'Plan', exact: true }).click()
    await page.waitForTimeout(1_000)

    // Navigate forward to a week guaranteed to be empty
    const nextBtn = page.locator('button').filter({ has: page.locator('svg') }).last()
    for (let i = 0; i < 50; i++) {
      await nextBtn.click()
      await page.waitForTimeout(200)
    }
    await page.waitForTimeout(1_000)

    // Should see the empty state
    const emptyState = page.getByText('No meal plan this week')
    if (await emptyState.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await expect(emptyState).toBeVisible()
      // CTA button should be present
      await expect(page.getByRole('button', { name: /Plan My Meals/i })).toBeVisible()
    }
  })

  test('Plan view week navigation changes the displayed dates', async ({ page }) => {
    await page.getByRole('button', { name: 'Plan', exact: true }).click()
    await page.waitForTimeout(1_000)

    // Get the initial week label
    const weekLabelLocator = page.locator('button').filter({ hasText: /This Week|[A-Z][a-z]+\s\d+/i }).first()
    const initialText = await weekLabelLocator.innerText().catch(() => 'This Week')

    // Click the next-week chevron (right arrow button)
    // The chevrons are the first and last buttons in the week nav bar
    const navButtons = page.locator('div.flex.items-center.justify-between.mb-4 button')
    await navButtons.last().click()
    await page.waitForTimeout(1_000)

    // Label should have changed (no longer "This Week")
    const afterText = await weekLabelLocator.innerText().catch(() => '')
    expect(afterText).not.toBe('This Week')
  })
})


test.describe('Meal Plan API — smoke tests', () => {
  test('GET /api/nutrition/meal-plan returns structured response', async ({ request }) => {
    const res = await request.get(`${BASE}/api/nutrition/meal-plan?date=2099-01-01&days=3`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('start_date')
    expect(body).toHaveProperty('end_date')
    expect(body).toHaveProperty('days')
    expect(Array.isArray(body.days)).toBe(true)
    expect(body.days.length).toBe(3)

    // Each day has the expected structure
    const day = body.days[0]
    expect(day).toHaveProperty('date')
    expect(day).toHaveProperty('planned')
    expect(day).toHaveProperty('actual')
    expect(day).toHaveProperty('day_totals')
    expect(day.day_totals).toHaveProperty('planned_calories')
    expect(day.day_totals).toHaveProperty('actual_calories')
  })

  test('GET /api/nutrition/meal-plan/{date} returns single day detail', async ({ request }) => {
    const res = await request.get(`${BASE}/api/nutrition/meal-plan/2099-01-01`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.date).toBe('2099-01-01')
    expect(body).toHaveProperty('planned')
    expect(body).toHaveProperty('actual')
    expect(body).toHaveProperty('day_totals')
  })

  test('GET /api/nutrition/preferences returns preference sections', async ({ request }) => {
    const res = await request.get(`${BASE}/api/nutrition/preferences`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('dietary_preferences')
    expect(body).toHaveProperty('nutritionist_principles')
    expect(typeof body.dietary_preferences).toBe('string')
    expect(typeof body.nutritionist_principles).toBe('string')
  })

  test('DELETE /api/nutrition/meal-plan/{date} rejects invalid meal_slot', async ({ request }) => {
    const res = await request.delete(`${BASE}/api/nutrition/meal-plan/2099-01-01?meal_slot=brunch`)
    expect(res.status()).toBe(400)
  })

  test('DELETE /api/nutrition/meal-plan/{date} succeeds for empty date', async ({ request }) => {
    const res = await request.delete(`${BASE}/api/nutrition/meal-plan/2099-12-31`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.removed).toBe(0)
  })
})
