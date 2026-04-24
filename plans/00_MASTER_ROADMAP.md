# Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## Active Campaigns

- [ ] **Campaign 19: Geocoder Hardening** (`plans/feat-geocoder-hardening.md` — to be created)
  - *Status:* Planned — two independent phases, both follow-on to Campaign 17's `GeocodingProvider` Protocol seam.
  - **Phase A — Google Maps Provider:** Implement `GoogleMapsProvider` (Maps Geocoding API, `GEOCODER=google`, API key via `GEOCODER_GOOGLE_API_KEY` env var). The Protocol seam is already in place; this is ~100 LOC + tests.
  - **Phase B — Multi-Instance Cache:** Move the in-process Nominatim LRU cache to a Postgres-backed `geocoder_cache` table (TTL column, `ON CONFLICT DO UPDATE`). Eliminates per-instance cold-start hits against Nominatim when Cloud Run scales beyond one replica.

- [ ] **Campaign 20: Ride Map with Synced Timeline Cursor + GPS Data-Quality Foundation** (`plans/feat-ride-map.md`)
  - *Status (2026-04-24):* **All 10 engineering phases ✅ shipped on `feat/ride-map`.** Phases 5-7 audit PASS (`AUDIT_feat-ride-map_c20_phases5-7.md`). Phases 8-10 audit PASS WITH NOTES (`AUDIT_feat-ride-map_c20_phases8-10.md`). Pending operator follow-up below.
  - **Phase 1–4 (DONE):** `<RideMap>` component with MapLibre GL + OpenFreeMap; lazy-loaded; cursor-sync to timeline chart; lap + drag-zoom highlighting; indoor placeholder.
  - **Phase 5–7 (DONE, merged at `134064e`):** FIT-records fetch path + FIT-primary cutover for ICU sync + lat-only Variant B parser hardening with D4 corruption write-guard.
  - **Phase 8–10 (DONE, latest at `ab49f5a`):** local 5-sample speed smoothing + `backfill_corrupt_gps.py` (dry-run default, `--no-dry-run` to write, `--allow-remote` for prod) with bundled FIT-download dedup via `fetch_activity_fit_all` + frontend `<RideMap>` corruption banner that displaces a wrong polyline.
  - **Operator follow-up — Step 10.E prod backfill (NOT yet run):**
    - *Pre-condition:* v1.14.x containing Phases 5-10 deployed to prod and baked ≥24 h with no error spike.
    - 1. `python scripts/backfill_corrupt_gps.py --dry-run --allow-remote` from a workstation with prod credentials. Inspect summary `total_corrupt`, `since_date`.
    - 2. If `total_corrupt > 100`, run `--no-dry-run --allow-remote --limit 50` first to verify end-to-end before the full sweep.
    - 3. `python scripts/backfill_corrupt_gps.py --no-dry-run --allow-remote`. Monitor Cloud Logging for `gps_source` events: `source=fit` (good), `source=fallback_streams` (degraded but acceptable), `source=none` (failure — investigate per ride).
    - 4. Verify post-state with the SQL in Phase 9.D of `plans/feat-ride-map.md`.
    - 5. Spot-check 3 rides on the live map UI.
  - **Optional polish items** (not merge blockers, not operator-blocking): refresh stale mocks in `tests/integration/test_sync.py:169,297` to use `fetch_activity_fit_all`; add a `--color-warning` design token to replace the `yellow` stand-in in the corruption banner.

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
- *Pending operator action: run `scripts/backfill_ride_start_geo.py --allow-remote` against prod DB to populate `start_lat/lon` for pre-Campaign-17 rides.*

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
