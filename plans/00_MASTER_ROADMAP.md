# 🗺️ Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## 🚀 Active Campaigns

### Campaign: v1.5.2 Data Science & Dashboard Overhaul
**Status:** 🟡 Planning
**Goal:** Upgrade the platform from simple data ingestion to a sophisticated "Data Science & Coaching" engine. This release addresses critical data quality issues (power anomalies, sensor failures), implements dynamic athlete state management (Weight/FTP), and restores the "Actual vs. Planned" visual context to the dashboard.
**Tracking Plan:** `plans/v1.5.2-roadmap.md`

#### Epics / Milestones
- [ ] **Phase 1: Foundations & Metric Integrity** (`plans/v1.5.2-01-foundations-metrics.md`)
  - *Status:* Planned
  - *Goal:* DB Schema updates, data science tooling (numpy, scipy), and unified source-of-truth metrics.
- [ ] **Phase 2: Sophisticated Ingestion Engine** (`plans/v1.5.2-02-ingestion-engine.md`)
  - *Status:* Planned
  - *Goal:* Statistical outlier removal, EF cleaning, and robust handling of stochastic data and sensor errors.
- [ ] **Phase 3: Dynamic Agent Intelligence** (`plans/v1.5.2-03-agent-intelligence.md`)
  - *Status:* Planned
  - *Goal:* Tool-based metric retrieval and dynamic prompt injection to ensure the AI uses live DB state.
- [ ] **Phase 4: Enhanced Analysis API** (`plans/v1.5.2-04-analysis-api.md`)
  - *Status:* Planned
  - *Goal:* Delivery of Aggregated Power Curves, Time-in-Zones, and Efficiency Trends APIs.
- [ ] **Phase 5: Dashboard & UI Restoration** (`plans/v1.5.2-05-dashboard-restoration.md`)
  - *Status:* Planned
  - *Goal:* Weekly Volume Chart (Actual vs Planned) overlay, 3-week projections, and friendly sport names.

