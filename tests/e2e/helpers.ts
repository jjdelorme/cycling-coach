/**
 * Shared helpers for cycling-coach e2e tests.
 *
 * Navigation uses the desktop header (hidden on mobile) because tests run
 * at 1440×900 where the top nav is always visible.
 */
import { type Page, expect } from '@playwright/test'

export const BASE_URL = process.env.BASE_URL ?? 'http://localhost:8080'

/** Click a desktop-header nav button by its visible label text. */
export async function navTo(page: Page, label: 'Dashboard' | 'Rides' | 'Calendar' | 'Analysis') {
  await page.locator('header').getByRole('button', { name: label }).click()
}

/** Navigate to Settings via the gear icon in the desktop header. */
export async function navToSettings(page: Page) {
  await page.locator('header button[title="Settings"]').click()
}

/** Wait until the loading spinner / "Loading…" text disappears. */
export async function waitForLoaded(page: Page, timeout = 15_000) {
  await page.waitForFunction(
    () => !document.body.innerText.includes('Loading'),
    { timeout },
  )
}

/** Assert no JS console errors were logged (ignores network warnings). */
export function attachConsoleListener(page: Page): string[] {
  const errors: string[] = []
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  return errors
}
