# Master Roadmap

This document serves as the top-level view of all active, planned, and completed Strategic Campaigns. 

> **Rule:** Do NOT track individual tasks here. Detailed task breakdowns and micro-steps belong in the specific Campaign Plan files.

## Active Campaigns

### Campaign: v1.5.2 Data Science & Dashboard Overhaul
**Status:** Mostly Complete
**Tracking Plan:** `plans/v1.5.2-roadmap.md`

#### Campaigns
- [x] **Campaign 1: Foundations & Metric Integrity** (`plans/v1.5.2-01-foundations-metrics.md`)
- [x] **Campaign 2: Sophisticated Ingestion Engine** (`plans/v1.5.2-02-ingestion-engine.md`)
- [x] **Campaign 3: Dynamic Agent Intelligence** (`plans/v1.5.2-03-agent-intelligence.md`)
- [x] **Campaign 4: Enhanced Analysis API** (`plans/v1.5.2-04-analysis-api.md`)
- [ ] **Campaign 5: Dashboard & UI Restoration** (`plans/v1.5.2-05-dashboard-restoration.md`)
- [x] **Campaign 6: Sync Recalculation** (`plans/v1.5.2-06-sync-recalculation.md`)
- [x] **Campaign 7: Intervals.icu Bi-directional Sync** (`plans/v1.5.2-07-intervals-integration.md`)
- [x] **Campaign 8: Delete Ride Feature** (`plans/feat_delete_ride.md`)
- [x] **Campaign 9: UI Maintenance & Infrastructure** (`plans/v1.5.2-09-ui-maintenance.md`)
- [ ] **Campaign 10: Frontend Testing Infrastructure** (`plans/feat_frontend_unit_tests.md`)
  - *Status:* Planned
  - *Goal:* Establish comprehensive unit and integration testing suite for React frontend to prevent regressions.

- [ ] **Campaign 11: Withings Body Scale Integration** (`plans/feat_withings_weight.md`)
  - *Status:* Implemented (feat/withings-weight-integration)
  - *Goal:* OAuth 2.0 integration with Withings Health API to pull daily body weight measurements from scale into `body_measurements` table, use as highest-priority weight source in PMC pipeline, and surface as a Weight Trend chart in the Analysis page.

- [ ] **Campaign 12: Withings Push Notification Webhooks** (`plans/feat_withings_webhooks.md`)
  - *Status:* Implemented alongside Campaign 11 (feat/withings-weight-integration)
  - *Goal:* Subscribe to Withings push notifications so new weight measurements sync automatically without polling. Withings calls our webhook when new data arrives; we fetch only the notified window and recompute PMC.

- [ ] **Campaign 13: Database Infrastructure & Reliability** (`plans/fix_db_shared_cursor.md`)
  - *Status:* Planned
  - *Goal:* Refactor `_DbConnection` to use independent cursors, eliminating the shared cursor anti-pattern and enabling nested query execution.

- [ ] **Campaign 14: Bug Fix — Ride Detail Lap Zoom** (`plans/bug-ride-detail-zoom-lap.md`)
  - *Status:* Planned
  - *Goal:* Resolve UX issue where lap selection breaks while the ride detail chart is zoomed. Implement "Option B" (zoom to lap) for better UX.

---

### Campaign: Macro Tracker v1.9.x — Core Meal Logging

**Status:** In Progress
**Goal:** Add meal photo logging, AI-powered macronutrient estimation, and a dedicated Nutritionist agent. Users snap a photo, the Nutritionist agent analyzes it via Gemini multimodal vision, and structured macro data is persisted alongside the photo.

#### Design Docs
- `plans/macro-tracker-design.md` — master spec with v1/v2 scope split
- `plans/design-ux-ui.md` — UX/UI
- `plans/design-ai-integration.md` — AI architecture
- `plans/design-backend.md` — backend architecture

#### Implementation Plans
- `plans/impl_backend_v1.md` — backend engineer's single source of truth
- `plans/impl_frontend_v1.md` — frontend engineer's single source of truth

#### Sub-campaigns
- [ ] **Campaign 1: Macro Tracker v1 — Core Logging**
  - *Status:* In Progress
  - *Scope:* DB schema (3 new tables), GCS photo upload, Nutritionist ADK agent, `/api/nutrition` REST API, Nutrition tab + page, MacroCard, MealTimeline, DailySummaryStrip, Nutritionist chat tab in CoachPanel, meal CRUD, React Query hooks, tests
- [ ] **Campaign 2: Macro Tracker v2 — Intelligence Layer**
  - *Status:* Planned (deferred)
  - *Scope:* AgentTool wiring (Coach→Nutritionist for complex fueling reasoning), Dashboard energy balance widget with sparkline, weekly summary stacked bar chart, rate limiting on photo analysis, voice notes (audio Part to Gemini), swipe gestures
- [ ] **Campaign 3: Macro Tracker v3 — Offline Support**
  - *Status:* Planned (deferred)
  - *Scope:* IndexedDB meal queuing, retry on connectivity, CloudOff indicator on pending meals, background sync for photos, offline macro entry without AI analysis
