# 🗺️ Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## 🚀 Active Campaigns

### Campaign: v1.5.2 Data Science & Dashboard Overhaul
**Status:** 🟡 Planning
**Goal:** Upgrade the platform from simple data ingestion to a sophisticated "Data Science & Coaching" engine. This release addresses critical data quality issues (power anomalies, sensor failures), implements dynamic athlete state management (Weight/FTP), and restores the "Actual vs. Planned" visual context to the dashboard.
**Tracking Plan:** `plans/v1.5.2-roadmap.md`

#### Epics / Milestones
- [x] **Phase 1: Foundations & Metric Integrity** (`plans/v1.5.2-01-foundations-metrics.md`)
  - *Status:* Completed ✅
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
- [ ] **Phase 6: Sync Recalculation** (`plans/v1.5.2-06-sync-recalculation.md`)
  - *Status:* Planned
  - *Goal:* Unify the metric calculation pipeline for Intervals.icu synced rides to ensure power bests and metrics are consistent with JSON imports.

## Backlog

- When importing from intervals.icu, you are not getting the activity name (can you check for this?)
- Be careful not to creating duplicate workouts on intervals.icu, there's an issue here
- When you select a day on the calendar, it doesn't highlight anymore -- this is a regression.
- When running in development, the build number shown on the page should be a version#-dirty-commithash type of value so that we know we're not on the clean vx.x.x tag. I think it would make sense to show at least the UI version number in the lower right hand corner (footer) of every page.
- when you click on the "analyze" button inside a ride, make sure that the coach has context for the workout that was scheduled.  If the user deviated from that plan, note it and see if it made sense or not, also evaluate whether that should impact the rest of the week's training.  Don't actually change the week, but suggest to the user that it might and offer a button for example to update the week .


DONE:

- How is the the coach's "Plan Management" text field used? Is this injected into every coaching AI session with ADK? I'm wondering if you need to repeat all of what is there? Doesn't ADK already represent what tools it has? There are more instrucitons, which are good, but I'm wondering if there is some redundancy there with what the ADK tool registration already passes to the model? 


* Document systems of record, for example weight can't be updated on connect.garmin.com via intervals.icu.  Should we keep our system as the system of record 
  - Show a diagram of how we read and write data through intervals.icu as a conduit to connect.garmin.com.
  - Intervals.icu is also getting data from strava & connect.garmin.com? How does it deal with that? For example ride titles come via strava not garmin, but garmin syncs with strava and so does intervals.icu, yet there are not duplicates.  

