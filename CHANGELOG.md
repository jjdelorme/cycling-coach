# Changelog

All notable changes to this project will be documented in this file.

## [v1.9.9-beta] - 2026-04-14

### Fixes
- fix(nutrition): allow editing meal time in addition to date — meal edit card now shows a time picker alongside the date picker, and `logged_at` is updated via the API
- fix(nutrition): add camera capture option for meal photo on Android — split Photo button into Camera (uses `capture="environment"`) and Gallery so Android users can take photos directly

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
