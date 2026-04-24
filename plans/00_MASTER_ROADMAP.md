# Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## Active Campaigns

- [ ] **Campaign 19: Geocoder Hardening** (`plans/feat-geocoder-hardening.md` — to be created)
  - *Status:* Planned — two independent phases, both follow-on to Campaign 17's `GeocodingProvider` Protocol seam.
  - **Phase A — Google Maps Provider:** Implement `GoogleMapsProvider` (Maps Geocoding API, `GEOCODER=google`, API key via `GEOCODER_GOOGLE_API_KEY` env var). The Protocol seam is already in place; this is ~100 LOC + tests.
  - **Phase B — Multi-Instance Cache:** Move the in-process Nominatim LRU cache to a Postgres-backed `geocoder_cache` table (TTL column, `ON CONFLICT DO UPDATE`). Eliminates per-instance cold-start hits against Nominatim when Cloud Run scales beyond one replica.

- [ ] **Campaign 24: Integration Test Suite Repair** (`plans/fix-integration-test-suite.md` — to be created)
  - *Status:* Planned — 10 pre-existing integration test failures discovered during svc-pgdb validation of Campaign 23's data-migrations framework on 2026-04-24. Verified to reproduce on `main` HEAD `07c044a` (v1.13.4); these are NOT regressions from Campaign 23. Run `CYCLING_COACH_DATABASE_URL=postgresql://postgres:dev@localhost:5432/coach_test pytest tests/integration/` to reproduce.
  - **Cluster 1 (8 failures): `rides.date` referenced after migration 0006 dropped it**
    - Affected tests: `test_timezone_queries.py::{test_ride_local_date_derivation, test_ride_local_date_utc, test_ride_date_filter_timezone_aware, test_ride_date_filter_excludes_wrong_timezone, test_pmc_groups_by_local_date, test_tss_aggregation_by_timezone}` + `test_nutrition_api.py::{test_daily_summary_with_rides, test_weekly_summary_with_rides}`.
    - Error: `psycopg2.errors.UndefinedColumn: column "date" of relation "rides" does not exist`.
    - Root cause: tests do `INSERT INTO rides (date, start_time, filename, ...)` but `migrations/0006_timezone_schema.sql:74` dropped the `date` column (`ALTER TABLE rides DROP COLUMN IF EXISTS date`) as part of the timezone-awareness rework. The migration's preamble explicitly states the prerequisite: *"All application code has been updated to stop reading rides.date"*. Commit `0d37011 fix(tests): resolve failing integration tests due to recent timezone schema migrations` addressed some sites but missed these 8.
    - Fix: drop `date` from the column list and value tuple in each affected INSERT statement (`start_time` is sufficient — the queries derive local date via `(start_time AT TIME ZONE :tz)::DATE`).
    - Effort: ~30 min mechanical.
  - **Cluster 2 (1 failure): `body_measurements.date` is TEXT + `compute_daily_pmc` signature mismatch**
    - Affected: `test_withings_integration.py::test_pmc_weight_priority_withings_over_ride`.
    - Two chained problems surface in the same test:
      1. `compute_daily_pmc(db_conn, since_date=test_date)` is called with `test_date: datetime.date`, but `server/ingest.py:448` does `datetime.fromisoformat(since_date)` which requires `str`. Raises `TypeError: fromisoformat: argument must be str`.
      2. Cleanup `DELETE FROM body_measurements WHERE date=%s` with a `date` parameter against a `text` column yields `psycopg2.errors.UndefinedFunction: operator does not exist: text = date`.
    - Decisions needed (call this in the campaign plan, don't pre-decide):
      - For (1): broaden `compute_daily_pmc` signature to `date | str` (callers cleaner), OR make the test pass `test_date.isoformat()` (single-test fix).
      - For (2): cast in SQL (`WHERE date = %s::text` test-only), OR ship a migration that ALTERs `body_measurements.date` to native `DATE` type (matches the rides/daily_metrics direction in 0006). The latter is the consistent move but touches every other read site.
    - Effort: small if test-side fixes both; medium if column ALTER (must audit all other readers of `body_measurements.date`).
  - **Cluster 3 (1 failure): `test_meal_plan_populated` returns empty `planned` dict**
    - Affected: `test_meal_plan.py::test_meal_plan_populated`.
    - Symptom: `assert "breakfast" in day["planned"]` fails because `day["planned"] == {}`. Endpoint returns HTTP 200, just with no planned meals in the response.
    - Root cause unknown — needs investigation. Hypotheses: (a) missing seed data the test depends on; (b) real bug in meal-plan generation logic that returns empty for the seeded test user; (c) auth/user-context mismatch — the dev user has no planned meals in seed data and the endpoint silently returns empty rather than 404.
    - Effort: unknown until first hour of investigation.
  - *Test-environment caveat:* the dev machine where these were observed has a long-lived native Postgres (no podman/tmpfs container available), so the `coach_test` DB persists state across runs. However: Cluster 1 + 2 errors are schema/test-code mismatches (column missing, wrong type) — they reproduce on a fresh DB. Cluster 3's empty-`planned` could plausibly be state-related; verify against a freshly-migrated DB during investigation.

---

## Archived Campaigns

### Campaign 18: Navigation, Routing & Deep Linking (Completed)
**Tracking Plans:** `plans/feat-navigation-deep-linking.md` (Phases 1–3), `plans/feat-nav-completion.md` (Phases 4–6)
- *Phases 1–3 shipped as v1.13.0-beta on 2026-04-22 (top-level routing, ride/workout deep links, nutrition deep links).*
- *Phases 4–6 shipped as v1.13.1-beta on 2026-04-22 (RequireAuth/RequireRole guards, /login route, breadcrumbs, Calendar ?date= sync).*
- *Bundled with Campaign 13 in v1.13.2-beta (worktree `worktree-agent-af461ff5`); pending merge to main + prod promotion.*

### Campaign 13: Database Infrastructure & Reliability (Completed)
**Tracking Plan:** `plans/fix_db_shared_cursor.md`
- *Refactored `_DbConnection` in `server/database.py` to create independent `RealDictCursor` objects per query, eliminating the shared-cursor anti-pattern and supporting nested query iteration.*
- *Bundled with Campaign 18 in v1.13.2-beta (worktree `worktree-agent-af461ff5`); pending merge to main + prod promotion.*
- *Audit: `plans/reports/AUDIT_fix_db_shared_cursor.md` — PASS.*

### Campaign 17: Rides Search (Free-Text + Location Radius) (Completed)
**Tracking Plan:** `plans/feat-rides-search.md`
- *Merged to main (`7b97931`); released as v1.12.3 on 2026-04-21.*
- *Post-ship GPS bugfixes (Syria bug — ICU latlng stream normalization + FIT lap fallback) released as v1.12.5-beta; location display granularity fix (zoom=12, state_code) released as v1.12.6-beta.*
- *GPS backfill now auto-applies via Campaign 23's data-migration framework (`data_migrations/0001_backfill_ride_start_geo.py`); no operator follow-up required.*

### Campaign 16: Calendar Ride-Name Display (Completed)
**Tracking Plan:** `plans/feat-calendar-ride-names.md`
- *Merged to main (`ef2a08f`); released as v1.12.3 on 2026-04-21.*

### Campaign 14: Bug Fix — Ride Detail Lap Zoom (Completed)
**Tracking Plan:** `plans/archive/bug-ride-detail-zoom-lap.md`
- *Completed and moved to archive.*

### Campaign 15: Timezone Awareness & Schema Hardening (Completed)
**Tracking Plan:** `plans/archive/timezone-awareness.md`
- *Merged to main (`a8be0ad`); local + worktree branch removed 2026-04-18.*


### Campaign: v1.5.2 Data Science & Dashboard Overhaul (Archived)
**Tracking Plan:** `plans/archive/v1.5.2-roadmap.md`
- *Components 1-9 & 11-12 moved to archive.*

### Campaign: Macro Tracker v1.9.x — Core Meal Logging (Archived)
**Tracking Plan:** `plans/archive/macro-tracker-design.md`
- *Deferred pending completion of core reliability campaigns.*

---

## Completed Campaigns
- *See `plans/archive/` for historical records of completed work.*
