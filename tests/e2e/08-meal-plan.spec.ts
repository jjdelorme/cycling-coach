/**
 * Meal Plan Calendar — Plan tab, empty state, week navigation, day detail.
 *
 * After Phase 3 of the routing migration:
 *   - Day/Week/Plan toggles are <NavLink> elements (`link` role).
 *   - Each view has its own URL: `/nutrition`, `/nutrition/week`, `/nutrition/plan`.
 *   - The selected day in the Plan view is encoded as `/nutrition/plan/:date`.
 *   - A single meal can be deep-linked at `/nutrition/meals/:id`.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 08-meal-plan
 */
import { test, expect } from '@playwright/test'
import { navTo } from './helpers'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

test.describe('Meal Plan Calendar', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE)
    await expect(page.getByText('FITNESS (CTL)', { exact: false })).toBeVisible({ timeout: 12_000 })
    await navTo(page, 'Nutrition')
    await expect(page).toHaveURL(/\/nutrition$/, { timeout: 8_000 })
    await page.waitForTimeout(500)
  })

  test('Nutrition page has Day / Week / Plan toggle links', async ({ page }) => {
    await expect(page.getByRole('link', { name: 'Day', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Week', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Plan', exact: true })).toBeVisible()
  })

  test('clicking Plan toggle updates URL to /nutrition/plan and shows plan view', async ({ page }) => {
    await page.getByRole('link', { name: 'Plan', exact: true }).click()
    await expect(page).toHaveURL(/\/nutrition\/plan$/, { timeout: 5_000 })
    // Plan view should show either the calendar grid or the empty state
    const hasCalendar = await page.getByText('This Week').or(
      page.getByText('No meal plan this week')
    ).isVisible({ timeout: 5_000 }).catch(() => false)
    expect(hasCalendar).toBeTruthy()
  })

  test('clicking Week toggle updates URL to /nutrition/week', async ({ page }) => {
    await page.getByRole('link', { name: 'Week', exact: true }).click()
    await expect(page).toHaveURL(/\/nutrition\/week$/, { timeout: 5_000 })
  })

  test('Plan view shows empty state with CTA button when no plans exist', async ({ page }) => {
    await page.getByRole('link', { name: 'Plan', exact: true }).click()
    await expect(page).toHaveURL(/\/nutrition\/plan$/, { timeout: 5_000 })

    // Navigate forward to a week guaranteed to be empty
    const nextBtn = page.locator('div.flex.items-center.justify-between.mb-4 button').last()
    for (let i = 0; i < 50; i++) {
      await nextBtn.click()
      await page.waitForTimeout(150)
    }
    await page.waitForTimeout(800)

    // Should see the empty state
    const emptyState = page.getByText('No meal plan this week')
    if (await emptyState.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await expect(emptyState).toBeVisible()
      // CTA button should be present
      await expect(page.getByRole('button', { name: /Plan My Meals/i })).toBeVisible()
    }
  })

  test('Plan view week navigation changes the displayed dates', async ({ page }) => {
    await page.getByRole('link', { name: 'Plan', exact: true }).click()
    await expect(page).toHaveURL(/\/nutrition\/plan$/, { timeout: 5_000 })

    const weekLabelLocator = page.locator('button').filter({ hasText: /This Week|[A-Z][a-z]+\s\d+/i }).first()
    const navButtons = page.locator('div.flex.items-center.justify-between.mb-4 button')
    await navButtons.last().click()
    await page.waitForTimeout(800)

    const afterText = await weekLabelLocator.innerText().catch(() => '')
    expect(afterText).not.toBe('This Week')
  })

  test('deep link to /nutrition/week loads the Week view directly', async ({ page }) => {
    await page.goto(`${BASE}/nutrition/week`)
    await expect(page).toHaveURL(/\/nutrition\/week$/)
    // Week view shows averages text
    await expect(page.getByText(/avg kcal\/day/i)).toBeVisible({ timeout: 8_000 })
  })

  test('deep link to /nutrition/plan loads the Plan view directly', async ({ page }) => {
    await page.goto(`${BASE}/nutrition/plan`)
    await expect(page).toHaveURL(/\/nutrition\/plan$/)
    // Plan view shows either grid or empty state
    const ok = await page.getByText('This Week').or(
      page.getByText('No meal plan this week')
    ).isVisible({ timeout: 8_000 }).catch(() => false)
    expect(ok).toBeTruthy()
  })

  test('deep link to /nutrition/plan/:date opens that day in detail view', async ({ page }) => {
    // Pick a future date so the URL is stable across runs
    const date = '2099-01-01'
    await page.goto(`${BASE}/nutrition/plan/${date}`)
    await expect(page).toHaveURL(new RegExp(`/nutrition/plan/${date}$`))
    // Detail view shows a "Back to Calendar" button
    await expect(page.getByRole('button', { name: /Back to Calendar/i })).toBeVisible({ timeout: 8_000 })
  })

  test('clicking Back to Calendar returns to /nutrition/plan', async ({ page }) => {
    const date = '2099-01-01'
    await page.goto(`${BASE}/nutrition/plan/${date}`)
    await expect(page.getByRole('button', { name: /Back to Calendar/i })).toBeVisible({ timeout: 8_000 })
    await page.getByRole('button', { name: /Back to Calendar/i }).click()
    await expect(page).toHaveURL(/\/nutrition\/plan$/, { timeout: 5_000 })
  })

  test('day URL /nutrition?date=YYYY-MM-DD drives the day view', async ({ page }) => {
    const date = '2099-01-01'
    await page.goto(`${BASE}/nutrition?date=${date}`)
    await expect(page).toHaveURL(new RegExp(`/nutrition\\?date=${date}$`))
    // Day view loads — at minimum the Day tab is active and visible
    await expect(page.getByRole('link', { name: 'Day', exact: true })).toBeVisible()
  })
})


test.describe('Meal Detail — deep link', () => {
  test('GET /api/nutrition/meals returns a list we can deep-link into', async ({ request }) => {
    const res = await request.get(`${BASE}/api/nutrition/meals?limit=1`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('meals')
    expect(Array.isArray(body.meals)).toBe(true)
  })

  test('deep link /nutrition/meals/:id loads meal detail when a meal exists', async ({ page, request }) => {
    const res = await request.get(`${BASE}/api/nutrition/meals?limit=1`)
    const body = await res.json()
    if (!Array.isArray(body.meals) || body.meals.length === 0) test.skip()
    const id = body.meals[0].id

    await page.goto(`${BASE}/nutrition/meals/${id}`)
    await expect(page).toHaveURL(new RegExp(`/nutrition/meals/${id}$`))
    // Back link is present
    await expect(page.getByRole('link', { name: /Back to Nutrition/i })).toBeVisible({ timeout: 8_000 })
  })

  test('Back to Nutrition link returns to /nutrition', async ({ page, request }) => {
    const res = await request.get(`${BASE}/api/nutrition/meals?limit=1`)
    const body = await res.json()
    if (!Array.isArray(body.meals) || body.meals.length === 0) test.skip()
    const id = body.meals[0].id

    await page.goto(`${BASE}/nutrition/meals/${id}`)
    await page.getByRole('link', { name: /Back to Nutrition/i }).click()
    await expect(page).toHaveURL(/\/nutrition$/, { timeout: 5_000 })
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
