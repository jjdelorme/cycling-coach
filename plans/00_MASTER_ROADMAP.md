# Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## Active Campaigns

- [ ] **Campaign 13: Database Infrastructure & Reliability** (`plans/fix_db_shared_cursor.md`)
  - *Status:* Planned
  - *Goal:* Refactor `_DbConnection` to use independent cursors, eliminating the shared cursor anti-pattern and enabling nested query execution.

- [ ] **Campaign 17: Rides Search (Free-Text + Location Radius)** (`plans/feat-rides-search.md`)
  - *Status:* Built — worktree `worktree-agent-a637d1df`, ready to merge to main. Implements `?q=` text search and `?near=&radius_km=` location-radius filter via pluggable `GeocodingProvider` (Nominatim by default, `GEOCODER` env var). Requires one-time backfill of `rides.start_lat/lon` against prod DB post-deploy.
  - *Branch:* `worktree-agent-a637d1df`

- [ ] **Campaign 18: Navigation, Routing & Deep Linking** (`plans/feat-navigation-deep-linking.md`)
  - *Status:* Phases 1–3 built — worktree `worktree-agent-af461ff5`, ready to merge after Campaign 17 lands. Phases 4–6 (route guards, breadcrumbs, `/login` + `RequireAuth`) deferred to follow-up campaigns.
  - *Branch:* `worktree-agent-af461ff5`

- [ ] **Campaign 19: Geocoder Hardening** (`plans/feat-geocoder-hardening.md` — to be created)
  - *Status:* Planned — two independent phases, both follow-on to Campaign 17's `GeocodingProvider` Protocol seam.
  - **Phase A — Google Maps Provider:** Implement `GoogleMapsProvider` (Maps Geocoding API, `GEOCODER=google`, API key via `GEOCODER_GOOGLE_API_KEY` env var). The Protocol seam is already in place; this is ~100 LOC + tests.
  - **Phase B — Multi-Instance Cache:** Move the in-process Nominatim LRU cache to a Postgres-backed `geocoder_cache` table (TTL column, `ON CONFLICT DO UPDATE`). Eliminates per-instance cold-start hits against Nominatim when Cloud Run scales beyond one replica.

---

## Archived Campaigns

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
