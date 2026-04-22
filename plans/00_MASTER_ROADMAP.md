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

- [ ] **Campaign 20: Ride Map with Synced Timeline Cursor** (`plans/feat-ride-map.md`)
  - *Status:* Planned — decisions resolved 2026-04-22, ready to build. MapLibre GL + OpenFreeMap "liberty" tiles, lazy-loaded chunk, hover-only cursor sync, indoor rides hide the map card as a first-class state.
  - *Goal:* On the ride detail page, render the full GPS track overlaid on a map (roads/trails with labels appropriate to the ride type — road names for road rides, trail names for MTB/gravel/hike). As the user hovers/scrubs along the existing ride timeline charts (power, HR, elevation), a position indicator (bubble/marker) moves along the route on the map in sync with the cursor's time index.

- [ ] **Campaign 21: Ride Map — "Follow Cursor" Auto-Pan Toggle** (`plans/feat-ride-map-follow-cursor.md` — to be created)
  - *Status:* Planned — follow-on to Campaign 20. Do not start until C20 ships.
  - *Goal:* Add an opt-in "follow cursor" toggle on the ride map that, when enabled, auto-pans the map to keep the hover-scrub marker in view as the user moves the cursor along the timeline chart. Disabled by default to avoid vertigo on heavily-zoomed maps; enabled by users who want to follow the route in detail.
  - *Open design questions:*
    - **Pan trigger:** Pan only when the marker leaves the viewport, or pan continuously to keep marker centred?
    - **Pan style:** Smooth `flyTo` (cinematic, may lag fast scrubs) vs. instant `setCenter` (snappier, but can feel jumpy)?
    - **Toggle persistence:** Per-ride, per-session, or stored in user settings?
  - *Note:* Click-to-pin is no longer a separate concern — the existing drag-to-select-zoom on the chart already serves that role and is wired up to the map in Campaign 20 Phase 4.

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
