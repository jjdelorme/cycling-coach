# Cycling Coach — E2E Tests

End-to-end tests using [Playwright](https://playwright.dev/).  
These tests run against a **live application** (no mocks) connected to the Neon production database.

## Prerequisites

1. The backend must be running on port 8080:
   ```bash
   cd /home/workspace/cycling-coach
   source venv/bin/activate
   uvicorn server.main:app --host 0.0.0.0 --port 8080
   ```
   The `.env` file configures `CYCLING_COACH_DATABASE_URL` to point at Neon automatically.

2. The frontend must be built into `frontend/dist/` (already served by FastAPI):
   ```bash
   cd frontend && npm run build
   ```

3. Playwright's Chromium browser must be installed:
   ```bash
   npx playwright install chromium
   npx playwright install-deps chromium
   ```

## Running Tests

From `tests/e2e/`:

```bash
# All tests
npx playwright test --config playwright.config.ts

# A single file
npx playwright test --config playwright.config.ts 02-dashboard

# With visible browser (headed)
npx playwright test --config playwright.config.ts --headed

# Against a different host
BASE_URL=http://staging.example.com npx playwright test --config playwright.config.ts
```

Or from the repo root:
```bash
cd tests/e2e && npx playwright test --config playwright.config.ts
```

## Test Files

| File | Scope | Tests |
|------|-------|-------|
| `01-api-health.spec.ts` | API (no browser) | health, version, PMC, rides, settings, planning |
| `02-dashboard.spec.ts`  | Dashboard page | metric cards, charts, recent rides, next workout |
| `03-rides.spec.ts`      | Rides page | list view, date filter, ride detail, metrics, notes |
| `04-calendar.spec.ts`   | Calendar page | grid, month nav, day selection, rides+workouts |
| `05-analysis.spec.ts`   | Analysis page | macro plan, power curve, efficiency, zones, FTP history |
| `06-settings.spec.ts`   | Settings page | athlete, coach, system tabs — all read-only |
| `07-navigation.spec.ts` | Global nav | header, tab switching, coach panel, version |

**Total: 75 tests**

## Design Principles

- **Read-only**: These tests never mutate data. They assert that the UI renders correctly and the API returns expected shapes.
- **Data-agnostic**: Tests check structure (cards present, rows > 0, chart canvas rendered), not specific metric values, so they remain valid as training data changes.
- **No login required**: `GOOGLE_AUTH_ENABLED=false` in `.env` bypasses Google auth and returns an admin dev user automatically.
- **Desktop viewport**: Tests run at 1440×900 so the desktop header navigation is always visible.

## Re-running as a Future Agent

A Claude Code agent with this repo can re-run the full suite by:

1. Verifying the server is running: `curl http://localhost:8080/api/health`
2. Running: `cd tests/e2e && npx playwright test --config playwright.config.ts`

Screenshots of all baseline pages are saved in `tests/e2e/screenshots/` for visual reference.
