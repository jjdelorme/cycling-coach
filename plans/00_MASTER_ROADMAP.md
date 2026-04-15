# Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## Active Campaigns

- [ ] **Campaign 13: Database Infrastructure & Reliability** (`plans/fix_db_shared_cursor.md`)
  - *Status:* Planned
  - *Goal:* Refactor `_DbConnection` to use independent cursors, eliminating the shared cursor anti-pattern and enabling nested query execution.

- [ ] **Campaign 14: Bug Fix — Ride Detail Lap Zoom** (`plans/bug-ride-detail-zoom-lap.md`)
  - *Status:* Planned
  - *Goal:* Resolve UX issue where lap selection breaks while the ride detail chart is zoomed. Implement "Option B" (zoom to lap) for better UX.

- [ ] **Campaign 15: Timezone Awareness & Schema Hardening** (`plans/timezone-awareness.md`)
  - *Status:* Planning/Phase 0 (Worktree)
  - *Goal:* Correct system-wide "UTC by accident" behavior. Migrate DATE/TIMESTAMPTZ columns, implement header-based timezone transport, and fix all daily logic to respect athlete's local day.

---

## Archived Campaigns

### Campaign: v1.5.2 Data Science & Dashboard Overhaul (Archived)
**Tracking Plan:** `plans/archive/v1.5.2-roadmap.md`
- *Components 1-9 & 11-12 moved to archive.*

### Campaign: Macro Tracker v1.9.x — Core Meal Logging (Archived)
**Tracking Plan:** `plans/archive/macro-tracker-design.md`
- *Deferred pending completion of core reliability campaigns.*

---

## Completed Campaigns
- *See `plans/archive/` for historical records of completed work.*
