# Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## Active Campaigns

- [ ] **Campaign 22: ADK Tool Serialization Safety** (`plans/fix-adk-json-serialization.md`)
  - *Status:* Planned
  - *Goal:* Implement a central `to_jsonable_python` wrapper for Google ADK tools to eliminate `TypeError: Object of type date is not JSON serializable` crashes and remove fragile manual date formatting from individual tools.

- [ ] **Campaign 19: Geocoder Hardening** (`plans/feat-geocoder-hardening.md` — to be created)
  - *Status:* Planned — two independent phases, both follow-on to Campaign 17's `GeocodingProvider` Protocol seam.
  - **Phase A — Google Maps Provider:** Implement `GoogleMapsProvider` (Maps Geocoding API, `GEOCODER=google`, API key via `GEOCODER_GOOGLE_API_KEY` env var). The Protocol seam is already in place; this is ~100 LOC + tests.
  - **Phase B — Multi-Instance Cache:** Move the in-process Nominatim LRU cache to a Postgres-backed `geocoder_cache` table (TTL column, `ON CONFLICT DO UPDATE`). Eliminates per-instance cold-start hits against Nominatim when Cloud Run scales beyond one replica.

- [ ] **Campaign 20: Ride Map with Synced Timeline Cursor + GPS Data-Quality Foundation** (`plans/feat-ride-map.md`)
  - *Status:* **Phases 1–4 (map UI) shipped on `feat/ride-map` worktree (audit PASS WITH NOTES). Phases 5–10 (GPS data-quality) PLANNED 2026-04-22 — same branch, same release.**
  - **Why expanded:** real-world testing of the C20 map exposed that ICU's `latlng` stream returns a lat-only payload variant (e.g. ride 3238 length=7003 odd) that the Campaign 17 parser fix did not cover. Per-record `ride_records.lat/lon` are corrupted on every ICU-synced ride hit by this variant — map renders a wrong polyline. User directive: fold the fix into C20, ship in the same release.
  - **Phase 1–4 (DONE):** `<RideMap>` component with MapLibre GL + OpenFreeMap; lazy-loaded; cursor-sync to timeline chart; lap + drag-zoom highlighting; indoor placeholder.
  - **Phase 5 — FIT-records fetch path:** `fetch_activity_fit_records()` parses FIT `record` messages we already download for laps. No call sites wired yet.
  - **Phase 6 — FIT-primary cutover:** `_store_records_or_fallback` makes ICU re-sync use FIT for per-record GPS/power/HR/cadence/altitude/distance/speed/temperature; streams remain the fallback when FIT is unavailable.
  - **Phase 7 — Streams-parser hardening:** `_normalize_latlng` detects the lat-only variant and returns `[]`; `_store_streams` defensive guard refuses to write rows that trip the corruption signature.
    - **Coordination note (2026-04-25):** Campaign 23 (v1.14.0-beta) already addressed the typed-entry ICU shape (`{"type": "latlng", "data": [lats], "data2": [lons]}`) by zipping `data` + `data2` in `_extract_streams`, plus a defensive `ABS(lat-lon) >= 1.0` guard at the `_backfill_start_location` write site. C20 Phase 7 should re-scope around what's still broken after C23 lands — likely the legitimately lat-only-no-data2 shape (if it actually exists) vs. the `_store_streams` per-record write site (which C23 didn't add a guard at, only `_backfill_start_location`). Re-audit before implementing.
  - **Phase 8 — Local speed smoothing:** new `smooth_speed()` in `server/metrics.py` (5-sample uniform filter, NaN-aware); wired into both ingest paths.
  - **Phase 9 — Historical backfill script:** `scripts/backfill_corrupt_gps.py` (dry-run by default, `--allow-remote` for prod, `--limit` for resumability, `--since YYYY-MM-DD` defaulting to last 14 days) detects rides where `ABS(lat-lon) < 1°` for >50% of records and re-syncs them via the Phase 6 helpers.
    - **Coordination note (2026-04-25):** complementary to Campaign 23's `0001_backfill_ride_start_geo` (which fixes `rides.start_lat/start_lon` only). C20 Phase 9 fixes per-record `ride_records.lat/lon`. Different tables, different scope. Once C20 lands, consider promoting the backfill script to a `data_migrations/0002_*.py` so it auto-applies on deploy under the framework C23 introduced, rather than requiring operator action.
  - **Phase 10 — Frontend safeguard + prod rollout:** `<RideMap>` detects the corruption signature client-side and renders a warning banner instead of a wrong polyline; operator runs the Phase 9 backfill against prod (default 14-day window — older rides exist on GCS as FIT-derived JSON and were never affected) after the v1.14.x release bakes for ≥24h.
  - *Status (2026-04-24):* All 5 pre-engineering open questions resolved by user. Plan unblocked — engineer can start Phase 5.

- [ ] **Campaign 21: Ride Map — "Follow Cursor" Auto-Pan Toggle** (`plans/feat-ride-map-follow-cursor.md` — to be created)
  - *Status:* Planned — follow-on to Campaign 20. Do not start until C20 ships.
  - *Goal:* Add an opt-in "follow cursor" toggle on the ride map that, when enabled, auto-pans the map to keep the hover-scrub marker in view as the user moves the cursor along the timeline chart. Disabled by default to avoid vertigo on heavily-zoomed maps; enabled by users who want to follow the route in detail.
  - *Open design questions:*
    - **Pan trigger:** Pan only when the marker leaves the viewport, or pan continuously to keep marker centred?
    - **Pan style:** Smooth `flyTo` (cinematic, may lag fast scrubs) vs. instant `setCenter` (snappier, but can feel jumpy)?
    - **Toggle persistence:** Per-ride, per-session, or stored in user settings?
  - *Note:* Click-to-pin is no longer a separate concern — the existing drag-to-select-zoom on the chart already serves that role and is wired up to the map in Campaign 20 Phase 4.

- [ ] **Campaign 24: Integration Test Suite Repair** (`plans/fix-integration-test-suite.md` — to be created)
  - *Status:* Planned — pre-existing integration test failures discovered during svc-pgdb validation of Campaign 23 on 2026-04-24. Verified to reproduce on `main` (the version of `main` we forked from); these are NOT regressions from Campaign 23. Re-validate the failure list after this branch merges — `25ecde7 fix(tests): make 3 integration tests robust to shared-DB and host env` on main partially overlaps. Run `CYCLING_COACH_DATABASE_URL=postgresql://postgres:dev@localhost:5432/coach_test pytest tests/integration/` to reproduce after merge.
  - **Cluster 1 (8 failures, mostly fixed by main's `25ecde7`): `rides.date` referenced after migration 0006 dropped it**
    - Originally affected: `test_timezone_queries.py::{test_ride_local_date_derivation, test_ride_local_date_utc, test_ride_date_filter_timezone_aware, test_ride_date_filter_excludes_wrong_timezone, test_pmc_groups_by_local_date, test_tss_aggregation_by_timezone}` + `test_nutrition_api.py::{test_daily_summary_with_rides, test_weekly_summary_with_rides}`.
    - Error: `psycopg2.errors.UndefinedColumn: column "date" of relation "rides" does not exist`.
    - Root cause: tests INSERT `(date, start_time, filename, ...)` but `migrations/0006_timezone_schema.sql:74` dropped the `date` column.
    - **Status after main merge:** all 6 `test_timezone_queries.py` sites now correctly INSERT without `date` (verified post-merge). The 2 `test_nutrition_api.py` sites need re-checking — were not touched by `25ecde7`.
    - Fix (residual): drop `date` from the 2 remaining INSERT sites if still present.
    - Effort: ≤15 min mechanical.
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
- *Bundled with Campaign 13 in v1.13.2-beta and merged to main; released as v1.13.2 on 2026-04-22.*

### Campaign 13: Database Infrastructure & Reliability (Completed)
**Tracking Plan:** `plans/fix_db_shared_cursor.md`
- *Refactored `_DbConnection` in `server/database.py` to create independent `RealDictCursor` objects per query, eliminating the shared-cursor anti-pattern and supporting nested query iteration.*
- *Released as part of v1.13.2 on 2026-04-22 (bundled with Campaign 18).*
- *Audit: `plans/reports/AUDIT_fix_db_shared_cursor.md` — PASS.*

### Campaign 17: Rides Search (Free-Text + Location Radius) (Completed)
**Tracking Plan:** `plans/feat-rides-search.md`
- *Merged to main (`7b97931`); released as v1.12.3 on 2026-04-21.*
- *Post-ship GPS bugfixes (Syria bug — ICU latlng stream normalization + FIT lap fallback) released as v1.12.5-beta; location display granularity fix (zoom=12, state_code) released as v1.12.6-beta. All consolidated into v1.13.2 prod release on 2026-04-22.*
- *GPS backfill now auto-applies via Campaign 23's data-migration framework (`data_migrations/0001_backfill_ride_start_geo.py`); no operator follow-up required after v1.14.0-beta.*

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
