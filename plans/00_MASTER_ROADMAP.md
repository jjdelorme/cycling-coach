# Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## Active Campaigns

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
  - **Phase 8 — Local speed smoothing:** new `smooth_speed()` in `server/metrics.py` (5-sample uniform filter, NaN-aware); wired into both ingest paths.
  - **Phase 9 — Historical backfill script:** `scripts/backfill_corrupt_gps.py` (dry-run by default, `--allow-remote` for prod, `--limit` for resumability, `--since YYYY-MM-DD` defaulting to last 14 days) detects rides where `ABS(lat-lon) < 1°` for >50% of records and re-syncs them via the Phase 6 helpers.
  - **Phase 10 — Frontend safeguard + prod rollout:** `<RideMap>` detects the corruption signature client-side and renders a warning banner instead of a wrong polyline; operator runs the Phase 9 backfill against prod (default 14-day window — older rides exist on GCS as FIT-derived JSON and were never affected) after the v1.14.x release bakes for ≥24h.
  - *Status (2026-04-24):* All 5 pre-engineering open questions resolved by user. Plan unblocked — engineer can start Phase 5.

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
