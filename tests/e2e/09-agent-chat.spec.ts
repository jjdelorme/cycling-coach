/**
 * Agent chat smoke tests — POST to /api/coaching/chat and /api/nutrition/chat
 * to exercise the full ADK runner path: tool registration → schema build for
 * Gemini → LLM call → response.
 *
 * Why this exists: Campaign 22's `json_safe_tool` wrapper was applied to
 * `preload_memory_tool` (a PreloadMemoryTool *instance*, not a function) and
 * crashed `inspect.signature` during ADK schema generation on every chat.
 * Unit tests that only checked tool *names* missed it; mocked integration
 * tests bypassed the runner. A real POST catches that whole class of
 * "agent looks fine on paper, blows up at chat time" regressions.
 *
 * The LLM call requires Vertex AI ADC; if creds are unavailable in CI, the
 * server returns 500 (or 401 from Google) and these will fail loudly — which
 * is the right signal: the agent is broken in some environment.
 *
 * Run:
 *   npx playwright test --config tests/e2e/playwright.config.ts 09-agent-chat
 */
import { test, expect } from '@playwright/test'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'

// Gemini calls can take several seconds; bound the wait so a hung LLM
// doesn't pin the suite indefinitely.
const CHAT_TIMEOUT_MS = 60_000

test.describe('Agent chat smoke tests', () => {
  test.setTimeout(CHAT_TIMEOUT_MS + 10_000)

  test('POST /api/coaching/chat builds tool schema and returns 200', async ({ request }) => {
    const res = await request.post(`${BASE}/api/coaching/chat`, {
      data: { message: 'Reply with the single word: pong.', session_id: null },
      timeout: CHAT_TIMEOUT_MS,
    })
    // 500 here means ADK schema generation failed — exactly the bug class
    // this spec is designed to catch. Surface the body for fast diagnosis.
    if (res.status() !== 200) {
      const body = await res.text()
      throw new Error(`Expected 200, got ${res.status()}. Body: ${body.slice(0, 1000)}`)
    }
    const body = await res.json()
    expect(typeof body.response).toBe('string')
    expect(body.response.length).toBeGreaterThan(0)
    expect(typeof body.session_id).toBe('string')
  })

  test('POST /api/nutrition/chat builds tool schema and returns 200', async ({ request }) => {
    const res = await request.post(`${BASE}/api/nutrition/chat`, {
      data: { message: 'Reply with the single word: pong.', session_id: null },
      timeout: CHAT_TIMEOUT_MS,
    })
    if (res.status() !== 200) {
      const body = await res.text()
      throw new Error(`Expected 200, got ${res.status()}. Body: ${body.slice(0, 1000)}`)
    }
    const body = await res.json()
    expect(typeof body.response).toBe('string')
    expect(body.response.length).toBeGreaterThan(0)
    expect(typeof body.session_id).toBe('string')
  })
})
