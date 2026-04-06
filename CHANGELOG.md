# Changelog

All notable changes to this project will be documented in this file.

## [v1.7.1] - 2026-04-06

### Fixes
- **Analysis:** Fixed critical crash on the Analysis page — `todayIdx` was referenced inside the `chartData` useMemo before it was initialized (JavaScript TDZ), blanking the page the moment weekly overview data loaded.
- **Analysis:** `weight_kg` field now correctly appears in FTP History chart tooltips. The backend was returning the field as `weight`; renamed to match the expected `weight_kg` key.
- **Analysis:** FTP History date range selector (1W / 3M / 6M / 1Y / ALL) now correctly filters data. The endpoint was ignoring `start_date` / `end_date` query parameters.

### Infrastructure
- Added `scripts/migrate_add_zone_indexes.sql` — idempotent migration to add `idx_ride_records_ride_id_power` and `idx_rides_date`, targeting the 2.5–3s slow query on the Zones tab. Run against any environment to apply.

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
