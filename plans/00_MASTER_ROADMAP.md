# Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## Active Campaigns

- [ ] **Campaign 13: Database Infrastructure & Reliability** (`plans/fix_db_shared_cursor.md`)
  - *Status:* Planned
  - *Goal:* Refactor `_DbConnection` to use independent cursors, eliminating the shared cursor anti-pattern and enabling nested query execution.

- [ ] **Campaign 16: Calendar Ride-Name Display** (`plans/feat-calendar-ride-names.md`)
  - *Status:* Planned (awaiting approval)
  - *Goal:* On the Calendar view, render the ride title alongside TSS when there's room (Tailwind `md:` breakpoint). Single-file frontend change; no backend work — title already flows through to the calendar.
  - *Suggested branch:* `feat/calendar-ride-names`

- [ ] **Campaign 17: Rides Search (Free-Text + Location Radius)** (`plans/feat-rides-search.md`)
  - *Status:* Planned (awaiting approval)
  - *Goal:* Add `?q=` free-text search on the Rides screen (Phase 1) and `?near=&radius_km=` location-radius filter via Nominatim geocoding + Haversine SQL (Phase 2). Phase 2 is gated on backfilling `rides.start_lat/start_lon` from `ride_records` for ICU-synced rides.
  - *Suggested branches:* `feat/rides-search-text`, `feat/rides-search-radius`

- [ ] **Campaign 18: Navigation, Routing & Deep Linking** (`plans/feat-navigation-deep-linking.md`)
  - *Status:* Planned (awaiting approval) — multi-week, 6 phases
  - *Goal:* Introduce `react-router-dom`, sync URLs with the address bar, support deep links to rides/meals/workouts, and add breadcrumbs. Each phase independently shippable. Requires E2E test updates to switch from `button` to `link` role queries.
  - *Suggested branches:* `feat/nav-phase1-router`, `feat/nav-phase2-rides-deep-link`, `feat/nav-phase3-nutrition-deep-link`, `feat/nav-phase4-route-guards`, `feat/nav-phase5-breadcrumbs`, `feat/nav-phase6-auth-cleanup`

---

## Archived Campaigns

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
