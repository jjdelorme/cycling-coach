# 🗺️ Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## 🚀 Active Campaigns

### Campaign: v1.5.2 Data Science & Dashboard Overhaul
**Status:** 🟡 Planning
**Goal:** Upgrade the platform from simple data ingestion to a sophisticated "Data Science & Coaching" engine. This release addresses critical data quality issues (power anomalies, sensor failures), implements dynamic athlete state management (Weight/FTP), and restores the "Actual vs. Planned" visual context to the dashboard.
**Tracking Plan:** `plans/v1.5.2-roadmap.md`

#### Campaigns
- [x] **Campaign 1: Foundations & Metric Integrity** (`plans/v1.5.2-01-foundations-metrics.md`)
  - *Status:* Completed ✅
  - *Goal:* DB Schema updates, data science tooling (numpy, scipy), and unified source-of-truth metrics.
- [x] **Campaign 2: Sophisticated Ingestion Engine** (`plans/v1.5.2-02-ingestion-engine.md`)
  - *Status:* Completed ✅
  - *Goal:* Statistical outlier removal (Z-score), physiological HR cleaning, and robust handling of sensor errors.
- [ ] **Campaign 3: Dynamic Agent Intelligence** (`plans/v1.5.2-03-agent-intelligence.md`)
  - *Status:* Planned
  - *Goal:* Tool-based metric retrieval and dynamic prompt injection to ensure the AI uses live DB state.
- [ ] **Campaign 4: Enhanced Analysis API** (`plans/v1.5.2-04-analysis-api.md`)
  - *Status:* Planned
  - *Goal:* Delivery of Aggregated Power Curves, Time-in-Zones, and Efficiency Trends APIs.
- [ ] **Campaign 5: Dashboard & UI Restoration** (`plans/v1.5.2-05-dashboard-restoration.md`)
  - *Status:* Planned
  - *Goal:* Weekly Volume Chart (Actual vs Planned) overlay, 3-week projections, and friendly sport names.
- [x] **Campaign 6: Sync Recalculation** (`plans/v1.5.2-06-sync-recalculation.md`)
  - *Status:* Completed ✅
  - *Goal:* Unify the metric calculation pipeline for Intervals.icu synced rides to ensure power bests and metrics are consistent with JSON imports.
- [x] **Campaign 7: Intervals.icu Bi-directional Sync** (`plans/v1.5.2-07-intervals-integration.md`)
  - *Status:* Completed ✅
  - *Goal:* Implement write-back capabilities for FTP, Weight, and Workouts to Intervals.icu, and resolve duplicate workout issues.

- [ ] **Campaign 8: Delete Ride Feature** (`plans/feat_delete_ride.md`)
  - *Status:* Planned
  - *Goal:* Full-stack capability to hard-delete rides and cascade DB deletions while recalculating PMC logic.
