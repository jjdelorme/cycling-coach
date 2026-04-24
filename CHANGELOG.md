# Changelog

All notable changes to this project will be documented in this file.

## [v1.13.5-beta] - 2026-04-24

Campaign 22 (ADK tool serialization safety) plus a pair of nutritionist-agent UX fixes uncovered while testing the campaign.

### Features — Campaign 22: ADK Tool Serialization Safety
- **feat(utils): `json_safe_tool` wrapper** — new `server/utils/adk.py` decorator that wraps any agent tool's return value through `pydantic_core.to_jsonable_python`, converting `date` / `datetime` / `UUID` / `Decimal` / nested structures into JSON-serializable forms before the ADK passes them to `json.dumps()`. Uses `functools.wraps` so the original signature, docstring, and type hints are preserved for Gemini schema generation.
- **fix(adk): apply `json_safe_tool` dynamically to all agent tools** — both the Coaching agent (`server/coaching/agent.py`) and Nutritionist agent (`server/nutrition/agent.py`) now wrap every read tool with `json_safe_tool` and every write tool with `json_safe_tool(_permission_gate(fn))` at registration time. The `AgentTool(agent=…)` delegation wrapper is intentionally left unwrapped since it's a class instance, not a function. Eliminates the `TypeError: Object of type date is not JSON serializable` class of crashes without leaking serialization concerns into business logic.

### Features — Nutritionist UX
- **fix(nutrition-agent): guard against hallucinated meal-plan persistence** — the agent was emitting prose like "I have persisted this plan to your dashboard" without actually calling `generate_meal_plan`, leaving the dashboard empty while the user believed the plan was saved. Two layered defenses: (1) strengthened `MEAL PLANNING PROTOCOL` system instruction with a `CRITICAL` header explaining that the dashboard reads from the DB and chat text is invisible there, plus an explicit prohibition on persistence-claim phrases unless the corresponding write tool returned `status=success` in the same turn; (2) server-side guardrail in `chat()` that detects first-person/passive persistence claims tied to a plan/meal noun via two conservative regex patterns; if no write tool was called this turn but a claim was made, the response is replaced with an honest "did not save" message and a `nutritionist_hallucinated_persistence` warning is logged.
- **feat(nutrition-ui): show incoming context as removable chip above input** — when a `MacroCard`'s "Ask Nutritionist" button pre-loaded the chat with context, the entire context blob was dumped into the textarea, forcing the user to scroll/edit around it. Now the context surfaces as a read-only chip with an `X` button above the textarea; on send, the message body combines them as `Context:\n<chip>\n\nQuestion: <input>` so the agent sees the same content. Retry preserves the original sent payload while displaying just the user's question in the bubble.

### Tests
- **111 Playwright e2e specs pass** (2 pre-existing skips, 0 fail).
- **418 unit tests pass** — added 19 new tests in `tests/unit/test_nutrition_agent.py` covering the `_claims_persistence` regex (8 positive + 9 benign cases) and three `chat()` override paths (claim+no-write → override; claim+write → keep; no-claim → keep).
- **230 integration tests pass on shared `svc-pgdb`** — fixed three pre-existing tests that were brittle outside the local Podman flow:
  - `test_ride_local_date_derivation`: added `ON CONFLICT (filename) DO NOTHING` to its first INSERT to match every sibling test in the file.
  - `test_get_pmc_metrics_by_date`: replaced hard-coded `ctl > 40` against the bundled seed with a behavior assertion — pick the date from the DB's actual `daily_metrics` rows and verify the `date=` parameter routes to *that* row.
  - `test_mint_token_user_not_found`: set `JWT_SECRET` in the subprocess env so the user-lookup branch is reached (the CLI checks `JWT_SECRET` first and short-circuits).

### Notes
- No schema or migration changes.
- No new env vars or dependencies; `pydantic_core` was already pulled in transitively.
- Removes the previous fragile workarounds (manual `_serialize_dates` recursion in nutrition tools, scattered `::TEXT` SQL casts and `str(row['date'])` calls in coaching tools) at the registration boundary.

## [v1.13.4] - 2026-04-23

Hotfix release for the prev/next-day navigation regression on ride/workout detail pages introduced by Campaign 18 in v1.13.0.

### Fixes
- **fix(nav): DayDetailShell prev/next-day arrows route correctly to ride detail when a ride exists** — the prev/next chevron buttons on `/rides/:id` and `/workouts/:id` were calling `fetch('/api/rides?...')` directly without the `Authorization: Bearer ...` header (returning 401 in prod) and without the `X-Client-Timezone` header (returning empty under UTC for users in non-UTC timezones). The empty/error response triggered the fallback path to `/rides/by-date/${date}`, which renders the planned-workout view — so users with a real recorded ride for the target date saw the planned workout instead. Switched to the project's centralized `fetchRides()` helper from `lib/api.ts`, which injects both headers via the shared `request()` wrapper.
- **fix(nav): debounce rapid clicks on prev/next-day arrows** — added an `isLoading` state that disables the chevron buttons while a navigation is in flight, with `cursor-wait` styling. Prevents race conditions where two overlapping requests could land the user on a stale URL.

### Tests
- 110 Playwright e2e specs pass, 2 skipped, 0 failed.
- 32 frontend vitest pass; 390 backend pytest unit pass.

### Notes
- Pure frontend change. No backend, schema, env-var, or dependency changes.
- The fallback to `/rides/by-date/${date}` is preserved for the legitimate case of a date that has only a planned workout (no recorded ride) — `useActivityDates` unions both ride dates and workout dates, and that route correctly renders either.

## [v1.13.2] - 2026-04-22

Consolidates all betas since v1.12.3: Campaign 17 follow-up GPS fixes, Campaign 18 (navigation/routing/deep linking, all six phases), and Campaign 13 (independent DB cursors).

### Features — Campaign 18: Navigation, Routing & Deep Linking
- **feat(nav): top-level client-side routing** — replaced the in-memory tab switcher with `react-router-dom@7`. Every top-level view has its own URL (`/`, `/rides`, `/calendar`, `/analysis`, `/nutrition`, `/settings`, `/admin`); the desktop header, mobile bottom nav, and "More" menu all use `<NavLink>`; browser back/forward, deep links, and unknown paths (→ `NotFound`) all work as expected. New `frontend/src/lib/routes.ts` is the canonical route table.
- **feat(nav): ride and workout deep links** — `/rides/:id`, `/rides/by-date/:date`, and `/workouts/:id` are real routes. Dashboard "Recent Rides" rows, Calendar "View Analysis" / "Show Details" links, and the prev/next-day chevron pill all `navigate()` to the appropriate URL instead of mutating local state. Sharing a URL like `/rides/12345` opens that ride directly. New `DayDetailShell` component shares the back-link + chevron-pill chrome between `/rides/:id` and `/workouts/:id`.
- **feat(nav): nutrition deep links** — `/nutrition`, `/nutrition/week`, `/nutrition/plan`, `/nutrition/plan/:date`, and `/nutrition/meals/:id` are routable. Day/Week/Plan toggles became `<NavLink>`s; `MealPlanCalendar`'s selected day is driven by `useParams`; new `MealDetail.tsx` page renders a single meal via `useMeal(id)`. The day view reads `?date=YYYY-MM-DD`.
- **feat(nav): route guards** — new `RequireAuth` and `RequireRole` components consume the existing `roleSatisfies` helper and render a `LoadingScreen` during the auth-loading window (avoids deep-link refresh briefly bouncing to `/login`). `/admin` and `/settings` are wrapped in `RequireRole`; the old `AdminRoute` inline check is gone.
- **feat(nav): /login as a real route** — `LoginPage` promoted from an `App.tsx` early-return to a top-level `/login` route mounted outside `RequireAuth`. After successful auth it redirects to `location.state.from.pathname ?? '/'`, so a user who pastes a deep link while logged out lands on that page after signing in. Authenticated users hitting `/login` bounce to `/`.
- **feat(calendar): URL-driven date selection** — `/calendar?date=YYYY-MM-DD` now seeds both the visible month and the selected day; clicking a day or paginating months keeps the URL in sync (`replace: true` to avoid history pollution).
- **feat(nav): breadcrumbs** — new `Breadcrumbs` component walks the route table's `parent` chain via `useLocation` + `matchPath`. Renders WAI-ARIA-correct `<nav aria-label="breadcrumb">` markup with `aria-current="page"` on the leaf; hidden on `/`. Dynamic crumbs for `/rides/:id`, `/workouts/:id`, and `/nutrition/meals/:id` resolve via the existing data hooks; raw param shows during loading. Mounted in `Layout.tsx` for desktop and as a compact row for mobile.
- **chore(app): App.tsx cleanup** — early-return removed; file shrunk from 73 → 55 lines with no `useState`, no role ladders, no `useEffect`. The route table itself is the floor.
- **refactor(roles): consolidate role checks** — `Settings.tsx` and `Layout.tsx` `isAdmin` checks now use `roleSatisfies(user?.role, 'admin')` consistently. `Settings.tsx isReadOnly` intentionally left as strict equality.

### Features — Campaign 17 follow-up: Rides Search hardening
- **feat(rides): free-text search** — `?q=` filter searches across ride title, user comments, coach comments, and filename via ILIKE; search input added to the Rides toolbar with an inline clear (×) button.
- **feat(rides): location-radius search** — `?near=&radius_km=` filter resolves a place name to coordinates via a pluggable `GeocodingProvider` and applies a bounding-box prefilter + Haversine post-filter in SQL; "Advanced" disclosure panel with place input, km/mi radius selector, "Use My Location" button, active-filter chip, and inline error surfacing.
- **refactor(geocoding): pluggable provider model** — `GeocodingProvider` Protocol with `NominatimProvider` as the sole implementation; provider selected via `GEOCODER` env var (default `nominatim`); cache keys namespaced by provider name so a swap doesn't return stale coords; `MockProvider` (`GEOCODER=mock`) exposes deterministic fixtures for E2E tests.

### Fixes
- **fix(db): eliminate shared cursor anti-pattern (Campaign 13)** — `_DbConnection` in `server/database.py` no longer holds a single class-level `RealDictCursor`. Each `execute()` / `executemany()` call now creates and returns an independent cursor, so nested query iteration (e.g. running a query inside a loop over the results of another query) no longer silently overwrites the parent's result set. Drop-in replacement.
- **fix(rides): granular reverse-geocoded location on ride detail** — zoom level raised from 10 → 12 so rural/trail ride starts resolve to township or community instead of just state; fallback chain extended with `suburb` and `county`; state displayed as abbreviation via `state_code` (e.g. "Abiquiú, NM" instead of "New Mexico").
- **fix(sync): ICU latlng stream GPS parsing (Syria bug)** — intervals.icu's `latlng` stream sometimes contains only latitude values with no longitude, causing the pairing logic to store `(lat, lat)` as `(start_lat, start_lon)`. For rides starting at ~35°N this reverse-geocoded to Syria. Three-layer fix: (1) `_normalize_latlng` detects the concatenated `[all_lats..., all_lons...]` format via a 1° proximity heuristic and handles `None` values; (2) new `_backfill_start_from_laps` uses FIT device lap data as an authoritative fallback and corrects the existing lat≈lon bug via `ABS(start_lat - start_lon) < 1°` guard; (3) `single_sync.py` resets `start_lat`/`start_lon` to NULL before re-syncing so backfill runs cleanly.
- **fix(rides): search clear button** — × button appears in the search input when text is present; clears query and removes `?q=` from active filter params immediately.
- **fix(backfill script portability)** — `scripts/backfill_ride_start_geo.py` now reads `CYCLING_COACH_DATABASE_URL` (matching app convention), calls `load_dotenv()` automatically, and adds repo root to `sys.path` so it runs correctly as `python3 scripts/backfill_ride_start_geo.py`.
- **fix(migrate.py)** — `python -m server.migrate` now calls `load_dotenv()` before reading `CYCLING_COACH_DATABASE_URL`, eliminating silent fallback to localhost when `.env` exists but env var is not manually exported.

### Database
- Migration `0008_rides_start_lat_lon_index.sql`: partial index on `rides(start_lat, start_lon) WHERE start_lat IS NOT NULL` to support bounding-box prefilter for the location-radius search.

### Tests
- 110 Playwright e2e specs pass (4 new in `11-breadcrumbs.spec.ts`; `/login` + redirect cases added to `07-navigation`; `?date=` deep link added to `04-calendar`; ride-deep-link cases added to `03-rides`).
- 32 frontend vitest tests pass (10 new across `RequireRole` and `roleSatisfies` suites).
- 390 backend pytest unit tests pass.
- New `test_nested_queries` in `tests/integration/test_database.py` proves the cursor-refactor regression: two cursors from the same connection iterate concurrently without interfering. All 5 `test_database.py` integration tests pass against local Postgres.

### Notes
- Roadmap updated: Campaigns 13, 17 (already merged at `7b97931`), and 18 moved to Archived.
- Pure frontend for Campaign 18; one-file backend refactor for Campaign 13. Backend RBAC (`require_read`/`require_write`/`require_admin`) was already in place before this train.
- Operator follow-up (carried over from v1.12.3): run `scripts/backfill_ride_start_geo.py --allow-remote` against prod DB to populate `start_lat/lon` for pre-Campaign-17 rides.

## [v1.12.3] - 2026-04-20

### Features
- **feat(calendar): show ride name inline on month grid (md+)** — Calendar day cells now display the ride title alongside the TSS number on `md+` breakpoints, with a native browser tooltip exposing the full title on every breakpoint (including mobile, where the inline span is hidden). Added an E2E assertion for the title attribute.

## [v1.12.2] - 2026-04-18

### Features
- **feat(nutrition): auto-forward ambiguous meal logs to chat** — When logging an ambiguous meal (e.g., "pop tarts") via the Quick Log modal, the UI now automatically forwards you to the full nutritionist chat window instead of presenting a generic "Done" button. The agent also uses bold markdown for key actions.


## [v1.12.1] - 2026-04-17

### Fixes
- **fix(rides): render markdown in AI Coaching card** — coach_comments on the Ride Detail page were rendered as plain pre-wrapped text, so when the LLM emitted markdown (`### headings`, `**bold**`, bullet lists) users saw raw syntax instead of formatted output. Now wrapped in `ReactMarkdown` + `remarkGfm` matching the `CoachPanel` pattern, with explicit `list-disc` / `list-decimal` / header-sizing utilities since Tailwind v4 preflight resets `ul`/`ol`/`h1-h3` styling

## [v1.12.0] - 2026-04-17

### Features
- **Full timezone awareness across the app:** all date computations now respect the user's local timezone via `X-Client-Timezone` header and `ContextVar`-based request context; users in non-UTC timezones see correct local dates for meals, rides, coaching, and training summaries
- **Router timezone dependency:** every ride-querying API endpoint now accepts the client timezone via `get_client_tz` FastAPI dependency
- **Frontend date formatting utilities:** 7 new functions in `format.ts` (`fmtDateShort`, `fmtDateLong`, `fmtDateTime`, `fmtTimestamp`, `fmtDateStr`, `fmtDateStrLong`, `localDateStr`); handle both UTC timestamps and date-only strings correctly. `Rides.tsx`, `Calendar.tsx`, `Dashboard.tsx`, `UserManagement.tsx` now use shared format utilities instead of inline date formatting

### Fixes
- **fix(timezone): ride queries rewritten** — all `rides.date` WHERE/ORDER references replaced with `(start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE` derivation; local dates computed at query time, not storage time
- **fix(timezone): 18 frontend UTC date bugs** across 6 nutrition components (`Nutrition.tsx`, `MealTimeline.tsx`, `NutritionDashboardWidget.tsx`, `MealPlanCalendar.tsx`, `MealPlanDayDetail.tsx`, `MacroCard.tsx`) — replaced `toISOString().slice(0,10)` with `localDateStr()`
- **fix(timezone): naive datetime.now() purge** — replaced with timezone-aware `get_request_tz()` / `user_today()` across nutrition, settings, withings, and weight services
- **fix(timezone): backfill NULL `start_time`** — migration 0006 populates `start_time` at noon UTC for ~310 ride rows from legacy intervals.icu syncs that wrote `date` but not `start_time`; restores rides list / 7-day strip on environments restored from prod. Migration also enforces `NOT NULL` on `start_time`
- **fix(timezone): runtime crashes** — `server/services/weight.py` and `server/routers/nutrition.py` still referenced the dropped `rides.date` column; rewritten to use `AT TIME ZONE` pattern
- **fix(rides): defense-in-depth `WHERE start_time IS NOT NULL`** added to the four list/summary query sites in `server/routers/rides.py`
- **fix(pmc): always compute PMC in UTC** — eliminates flip-flopping between UTC (background sync) and local timezone (user actions); PMC is a mathematical model where calendar day boundaries don't affect 42-day exponential averages
- **fix(database): `_adapt_sql` regex** no longer mangles Postgres `::TYPE` cast syntax (e.g. `::TIMESTAMPTZ`); added negative lookbehind to skip double-colon casts

### Database
- Migration `0006_timezone_schema.sql`: cast `start_time` to TIMESTAMPTZ, drop legacy `date` column, enforce `NOT NULL` on `start_time` (idempotent, safe to re-run)
- Migration `0007_ride_records_timestamp.sql`: promote `ride_records.timestamp_utc` from TEXT to TIMESTAMPTZ (idempotent, guarded by column type check)

### Deployment
- **cloudbuild.yaml:** run DB migrations via Cloud SQL Proxy before prod deploy
- **cloudbuild-test.yaml:** parse Cloud SQL instance from `CYCLING_COACH_DATABASE_URL_TEST` secret and pass via `--set-cloudsql-instances` for both migrate and deploy steps; test revisions previously stayed bound to prod regardless of the test secret. Removed hardcoded `_CLOUD_SQL_INSTANCE` substitution

### Tests
- 5 unit tests for nutrition timezone-aware tool calls
- 4 unit tests for nutrition rides.date query rewrites
- 5 unit tests verifying router `tz` dependency wiring
- 2 unit tests for `set_athlete_setting` timezone behavior
- 1 unit test for withings UTC-aware datetime
- 6 integration tests for `AT TIME ZONE` query pattern against real Postgres

### Chores
- `.gitignore` updated: e2e test artifacts (`test-results/`, `playwright-report/`) no longer tracked

## [v1.10.0] - 2026-04-14

### Features
- **Ride timeline drag-to-zoom:** click and drag to select a region of the ride timeline, chart zooms to that range with selection stats (avg power, HR, cadence, duration); supports iterative sub-zooming; Reset Zoom button restores full timeline
- **Ride timeline step/lap zoom:** click a workout step or lap to zoom the timeline chart to that segment

### Fixes
- fix(nutrition): allow editing meal time in addition to date — meal edit card now shows a time picker alongside the date picker
- fix(nutrition): add camera capture option for meal photo on Android — split Photo button into Camera and Gallery
- fix(nutrition): render agent notes as markdown with proper formatting
- fix(ui): increase note font sizes on mobile and desktop for readability

## [v1.9.8] - 2026-04-14

### Features
- **Meal plan calendar:** weekly grid view with day columns and meal slot summaries; day detail view with prev/next navigation and "Back to Calendar" link; planned vs logged adherence bar; swipe navigation on mobile; empty state CTA to open nutritionist
- **Nutritionist meal planning tools:** AI agent can generate, replace, and clear planned meals via `generate_meal_plan`, `replace_planned_meal`, `clear_meal_plan` tools; dietary preferences and nutritionist principles configurable in Settings
- **Auto-refresh:** meal plan calendar auto-updates when the nutritionist modifies plans (derived state from live TanStack Query data)
- **Quick-log meal modal:** self-contained popup with three-state flow (input → spinner → result card); "Chat about this" opens the nutritionist panel with the session auto-loaded
- **User notes on logged meals:** editable textarea in MacroCard, saved via `user_notes` column
- **Meal analysis:** "Analyze" button sends meal data + photo to nutritionist agent, saves feedback as `agent_notes`; "Ask a Question" on planned meals opens nutritionist chat with full meal context
- **Mobile bottom nav:** consolidated 5-tab layout — Dashboard, Calendar, Nutrition, Coach, and "More" overflow menu (Rides, Analysis, theme toggle, Settings, Users)

### Fixes
- fix(rides): correct lap-to-record mapping for irregularly sampled streams — lap highlight now works correctly on ICU-synced rides where record count differs from ride duration
- fix(rides): use `total_elapsed_time` (wall-clock) instead of `total_timer_time` (active-only) for lap boundary calculations
- fix(nutrition): navigate to day view after logging a meal so the new meal is immediately visible
- fix(nutrition): resolve nutritionist chat crash from missing `rides.date` column and date serialization
- fix(ui): compact "Log a Meal" FAB on mobile — shows only `+` icon; full pill with text on desktop
- fix(ui): responsive Settings tab labels — icons-only on mobile for inactive tabs

### Database
- Migration `0003_planned_meals.sql`: `planned_meals` table with unique constraint on (user_id, date, meal_slot); seeds dietary preferences and nutritionist principles defaults
- Migration `0004_rides_add_date_column.sql`: adds `date` column to rides table
- Migration `0005_meal_user_notes.sql`: adds `user_notes` column to meals

### Tests
- 25 unit tests for nutrition planning tools
- 17 integration tests for meal plan API endpoints
- 9 Playwright E2E tests for meal plan calendar

## [v1.9.0] - 2026-04-11

### Features
- **Withings weight integration:** unified weight resolver (`server/services/weight.py`) with Withings-priority chain; Withings sync and webhook push measurements to Intervals.icu; Settings field disabled when managed by Withings
- **AI nutritionist agent:** full nutrition tab with meal capture (photo + voice), macro tracking cards, meal timeline, daily summary strip, and dedicated nutritionist chat panel
- **AI coach markdown tables:** GFM table rendering in coach and nutritionist chat panels
- **Dashboard:** rolling 7-day multi-axis line chart with toggleable metrics (TSS, Hours, Kcal, Distance, Climbing, Avg W)
- **Ride detail:** calories displayed on ride detail and calendar preview
- **Rate limiting UX:** coaching and nutrition panels show "model is busy" warning with retry button on 429

### Architecture
- **Database migrations:** replaced `init_db()` with numbered SQL migration system (`migrations/` + `server/migrate.py`); Cloud Build applies pending migrations on beta deploy
- **Weight service:** all components (coaching, nutrition, ingest) route through the weight resolver instead of reading `athlete_settings` directly
- **Chat sessions:** `session_type` column distinguishes coaching vs nutrition sessions; replaces broken `LIKE 'nutrition-%'` filter
- **Meal photos:** served via API proxy (`/api/nutrition/photos/{id}`) instead of GCS signed URLs

### Deploy & Infrastructure
- **Withings OAuth:** redirect URI derived from request headers — works for any Cloud Run URL including tagged test deployments
- **Cloud Build:** Cloud SQL Auth Proxy added to test migration step; `COPY migrations/` added to Dockerfile; deployer SA permissions documented
- **Dependencies:** `google-adk` 1.29.0, `google-cloud-aiplatform` 1.147.0, Docker base image switched to `python:3.12-slim`

### Tests
- 16 unit tests for weight service and Withings→ICU push
- Unit and integration tests for nutrition API, rate limiting, and agent tool wiring

## [v1.8.3] - 2026-04-10

- fix(tests): 7 integration test bug fixes (weight_kg alias, structlog event key, READ COMMITTED cross-connection visibility, float("") crash on empty HR/age defaults, mock patch namespace, ASGI middleware contextvars)
- fix(tests): harden all planning tool tests for persistent DB (pre-clean DELETE+commit before inserts, has_power_data=TRUE filter for power ride lookups)
- fix(tests): OTel trace ID test now uses standalone probe app — immune to SPA catch-all shadowing when frontend/dist is present
- test: 75 Playwright E2E tests covering health, dashboard, rides, calendar, analysis, settings, and navigation
- test: `scripts/run_integration_tests.sh --use-svc-pgdb` runs integration suite against shared k8s svc-pgdb (no Podman required)
- test: `scripts/seed_svc_pgdb.sh` seeds svc-pgdb with schema + historical data + synthetic recent rows (inline, no committed file mutations)

## [v1.8.2-beta] - 2026-04-09

- feat(dashboard): rolling 7-day multi-axis line chart with toggleable metrics (TSS, Hours, Kcal, Distance, Climbing, Avg W), each with its own Y-axis; default: TSS + Hours + Kcal
- feat(api): `GET /api/rides/summary/daily` endpoint with weighted-average power aggregation across multiple rides per day
- test: 9 unit tests for `aggregate_daily_rides`

## [v1.8.1-beta] - 2026-04-09

- feat(ui): display calories on ride detail and calendar preview (combined Avg Power + NP into stacked card, replaced NP with Calories in calendar mini preview)
- feat(ui): rolling 7-day multi-axis line chart on dashboard with toggleable metrics (TSS, Hours, Kcal, Miles, Climbing, Avg W)
- feat(api): `GET /api/rides/summary/daily` endpoint with weighted-average power aggregation
- test: 9 unit tests for `aggregate_daily_rides` pure function

## [v1.7.11-beta] - 2026-04-08

- fix(ci): push branch and tag atomically so Cloud Build workspace includes the tag and `git describe` resolves the correct version
- chore(ci): remove debug output from test build VERSION step

## [v1.7.9-beta] - 2026-04-08

- fix(ci): remove --depth=1 from git fetch so annotated tag objects are fetched and version displays correctly

## [v1.7.8-beta] - 2026-04-08

- feat(observability): OpenTelemetry tracing — AI coach chat sessions now export `agent.chat` and `agent.tool_call` spans to GCP Cloud Trace; structured logs correlated via `logging.googleapis.com/trace`

## [v1.7.7-beta] - 2026-04-08

- fix(ci): fetch tags before git describe so VERSION shows tag not commit hash

## [v1.7.6-beta] - 2026-04-08

- fix(ci): sanitize branch name in test build image tag (fixes builds for branches with `/` in name)

## [v1.7.5-beta] - 2026-04-07

- feat(observability): structured JSON logging across the entire backend

## [v1.7.4-beta] - 2026-04-07

- CI: switched prod Cloud Build trigger from branch push to tag push with tag guard

## [v1.7.3] - 2026-04-07

### Release
- Merge of `2026-04-06-feedback` branch into main, incorporating the adaptive AI coach architecture (v1.7.2) and analysis page fixes (v1.7.1). See those entries for full details.

## [v1.7.2] - 2026-04-06

### AI Coach — Adaptive Architecture

The coaching agent is now fully adaptive. All hard-coded workout prescriptions,
weekly templates, and static coach notes have been removed. The LLM agent makes
every training decision from real athlete data.

- **Removed** `generate_weekly_plan` and `regenerate_phase_workouts` — these
  embedded rigid weekly structures (Mon=recovery, Tue=Z2, etc.) and a hard-coded
  3-week build / 1-week recovery mesocycle that produced identical workouts
  every week regardless of athlete state.
- **Added** `generate_week_from_spec` — a dumb batch-insert tool. The agent
  queries CTL/ATL/TSB, recent ride quality, and phase context, then decides what
  to prescribe. Tools execute; the LLM coaches.
- **Removed** `_WORKOUT_COACH_NOTES` static dict — coach notes are now written
  by the agent based on actual athlete context, never pulled from a Python
  lookup table.
- **System prompt** now injects the last 7 days of rides on every session so the
  agent has immediate adaptive context without an extra tool call.
- **Adaptive planning protocol** in `DEFAULT_PLAN_MANAGEMENT`: TSB thresholds
  for intensity decisions, mandatory pre-prescription data checks, no rigid
  periodization cycles.

### Security

- **Restricted `update_coach_settings`** to `athlete_profile` and
  `coaching_principles` only — removes the agent's ability to rewrite its own
  `coach_role` / `plan_management` system prompt sections via prompt injection.
- **Prompt injection mitigations** — athlete-provided fields (`athlete_notes`,
  `post_ride_comments`) are wrapped with `[ATHLETE DATA: ...]` delimiters in all
  tool outputs so the LLM treats them as untrusted data, not instructions.

### Infrastructure

- **`server/zones.py`** — new single source of truth for all zone boundary
  definitions (`POWER_ZONES`, `HR_ZONES`, `power_zone_label`,
  `compute_power_zones`, `compute_hr_zones`). Eliminates four duplicate
  definitions across `tools.py`, `analysis.py`, `planning.py`, and
  `tcx_export.py`, including a silent boundary inconsistency (0.56 vs 0.55).
- **Removed hardcoded FTP=261** (one athlete's personal FTP) from 8 locations
  across `queries.py`, `workout_generator.py`, `planning.py`, `fit_export.py`,
  and `tcx_export.py`. Missing FTP now propagates as `0`.
- **Generic installation defaults** — `ATHLETE_SETTINGS_DEFAULTS` and
  `DEFAULT_ATHLETE_PROFILE` replaced with empty/placeholder values. Platform is
  now truly multi-athlete ready.

### Tests

- Added 11 new integration tests covering `set_workout_coach_notes`,
  `replace_workout`, `generate_week_from_spec` (template, custom, rest, mixed,
  error, notes round-trip), `get_upcoming_workouts` coach_notes field.
- Integration tests for deleted functions removed; replaced with
  `generate_week_from_spec` equivalents.

### Documentation

- **`AGENTS.md`** — new *AI Coaching Architecture Principles* section with five
  hard mandates: no hard-coded prescriptions, no static notes, agent decides /
  tools execute, adaptive by default, DB is the source of truth.

## [v1.7.1] - 2026-04-06

### Fixes
- **Analysis:** Fixed critical crash on the Analysis page — `todayIdx` was referenced inside the `chartData` useMemo before it was initialized (JavaScript TDZ), blanking the page the moment weekly overview data loaded.
- **Analysis:** `weight_kg` field now correctly appears in FTP History chart tooltips. The backend was returning the field as `weight`; renamed to match the expected `weight_kg` key.
- **Analysis:** FTP History date range selector (1W / 3M / 6M / 1Y / ALL) now correctly filters data. The endpoint was ignoring `start_date` / `end_date` query parameters.

### Infrastructure
- Added `scripts/migrate_add_zone_indexes.sql` — idempotent migration to add `idx_ride_records_ride_id_power` and `idx_rides_date`, targeting the 2.5–3s slow query on the Zones tab. Run against any environment to apply.

## [v1.7.0] - 2026-04-05

### Fixes
- **UI:** Formatted interval lap duration consistently with planned intervals.
- **UI:** Fixed ride navigation buttons.
- **API:** Added error handling to the `activity-dates` endpoint.

## [v1.6.3] - 2026-04-05

### Features & Enhancements
- **Syncing:** Added `_download_planned_workouts` phase to import missing Intervals.icu calendar events into the local database.
- **Syncing:** Added an expandable and scrollable log view to the sync result banner for detailed status feedback.
- **Infrastructure:** Introduced a test deployment pipeline for automated branch-based builds.

### Fixes
- **Syncing:** Fixed a potential background sync hang by correctly using `asyncio.get_running_loop()`.
- **Syncing:** Optimized sync performance by batch-fetching Intervals.icu calendar events, eliminating N+1 API calls.
- **Syncing:** Improved the sync summary to correctly count and report downloaded workouts.
- **Syncing:** Prevented event loop blocking during workout deduplication tasks.
- **UI:** Improved component typing and test coverage for planned workout comparisons.

## [v1.6.2] - 2026-04-02

### Features & Enhancements
- **Workouts:** Added side-by-side Actual vs. Planned comparisons for Avg Power and NP on ride summaries.
- **Workouts:** Extended the ride timeline chart to visualize uncompleted segments of planned workouts.
- **Workouts:** Added "Actual Power" and target difference to individual intervals on the workout step table.

## [v1.6.0] - 2026-04-01

This release encompasses major architectural and feature enhancements, advancing the platform far beyond a minor fix.

### Features & Enhancements
- **Metrics & Analytics:** Implemented a foundational metrics engine with signal processing and math vectorization using `numpy` and `scipy`.
- **Data Ingestion:** Added advanced statistical filters, robust stream extraction, and unified metrics recalculation.
- **Agent Intelligence:** Implemented dynamic agent intelligence (Campaign 3) with a scrollable recent sessions list for the AI Coach.
- **Ride Management:** Added the ability to delete rides directly from the UI.
- **FIT File Parsing:** Introduced native FIT file lap parsing and advanced analysis API enhancements.
- **User Interface:** Added an app version indicator to the footer, restored ghost bar chart overlays, improved calendar highlights, and added dynamic `SportIcon` components.
- **Branding:** Added 'C' brand logo and favicon.
- **Syncing:** Improved Intervals.icu integration and created reliable single-ride re-syncing with visual feedback.

### Architecture & Infrastructure
- Expanded database schema for robust power analytics and data cleaning.
- Refactored testing infrastructure into distinctly separated unit and integration tests.
- Added comprehensive `README.md` with systems of record and screenshots.
- Replaced static `VERSION` file management; FastAPI and Vite now dynamically resolve the version directly from Git tags.

### Fixes
- Fixed calculation of Normalized Power (NP) per lap from stream power data.
- Improved Intervals.icu sync status logs and feedback.
- Fixed critical data-wiping tests.
- UI: Aligned re-sync and delete buttons side-by-side in the ride detail view.

### Database & Data
- Backfilled all historical rides with cleaned metrics and implemented historical-aware lookups (`get_latest_metric`).
