/**
 * API health & version — smoke tests against running server.
 *
 * These tests hit the JSON API directly (no browser) and are the fastest
 * signal that the backend is up and connected to the database.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 01-api-health
 */
import { test, expect } from '@playwright/test'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

test.describe('API – health & version', () => {
  test('GET /api/health returns ok with ride count > 0', async ({ request }) => {
    const res = await request.get(`${BASE}/api/health`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.status).toBe('ok')
    expect(typeof body.rides).toBe('number')
    expect(body.rides).toBeGreaterThan(0)
  })

  test('GET /api/version returns a version string', async ({ request }) => {
    const res = await request.get(`${BASE}/api/version`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(typeof body.version).toBe('string')
    expect(body.version.length).toBeGreaterThan(0)
  })

  test('GET /api/pmc returns array of daily PMC entries', async ({ request }) => {
    const res = await request.get(`${BASE}/api/pmc`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body)).toBe(true)
    expect(body.length).toBeGreaterThan(0)
    const entry = body[0]
    expect(entry).toHaveProperty('date')
    expect(entry).toHaveProperty('ctl')
    expect(entry).toHaveProperty('atl')
    expect(entry).toHaveProperty('tsb')
  })

  test('GET /api/rides returns array of ride summaries', async ({ request }) => {
    const res = await request.get(`${BASE}/api/rides?limit=10`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body)).toBe(true)
    expect(body.length).toBeGreaterThan(0)
    const ride = body[0]
    expect(ride).toHaveProperty('id')
    expect(ride).toHaveProperty('date')
    expect(ride).toHaveProperty('sport')
    expect(ride).toHaveProperty('duration_s')
  })

  test('GET /api/rides/:id returns full ride detail', async ({ request }) => {
    // Fetch list first to get a valid ID
    const listRes = await request.get(`${BASE}/api/rides?limit=1`)
    const [summary] = await listRes.json()
    expect(summary.id).toBeTruthy()

    const res = await request.get(`${BASE}/api/rides/${summary.id}`)
    expect(res.status()).toBe(200)
    const ride = await res.json()
    expect(ride.id).toBe(summary.id)
    expect(ride).toHaveProperty('date')
    expect(ride).toHaveProperty('sport')
    // records may be empty for some rides but the key must exist
    expect(ride).toHaveProperty('records')
  })

  test('GET /api/analysis/power-curve returns curve data', async ({ request }) => {
    const res = await request.get(`${BASE}/api/analysis/power-curve?range=3m`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    // Expecting { durations: [...], powers: [...] } or similar structure
    expect(body).toBeTruthy()
  })

  test('GET /api/coaching/settings returns settings object', async ({ request }) => {
    const res = await request.get(`${BASE}/api/coaching/settings`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('units')
    expect(body).toHaveProperty('athlete_profile')
    expect(body).toHaveProperty('coaching_principles')
  })

  test('GET /api/athlete/settings returns athlete settings', async ({ request }) => {
    const res = await request.get(`${BASE}/api/athlete/settings`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    // Keys: ftp, weight_kg, lthr, etc.
    expect(body).toHaveProperty('ftp')
  })

  test('GET /api/plan/week/:date returns weekly plan', async ({ request }) => {
    // Path: /api/plan/week/{monday_date}
    const res = await request.get(`${BASE}/api/plan/week/2026-04-07`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('planned')
    expect(Array.isArray(body.planned)).toBe(true)
  })
})
