# Weight Architecture Implementation Plan

**Design Spec:** `plans/design-weight-architecture.md`
**Status:** In Progress

## Analysis & Context

- **Objective:** Close all implementation gaps identified in the weight architecture design doc.
- **Affected Files:**
  - `server/services/weight.py` (NEW)
  - `tests/unit/test_weight_service.py` (NEW)
  - `server/queries.py` (FTP W/kg bug fix)
  - `server/services/withings.py` (ICU push trigger)
  - `server/coaching/agent.py` (use weight resolver)
  - `server/coaching/tools.py` (use weight resolver)
  - `server/nutrition/agent.py` (use weight resolver)
  - `server/nutrition/tools.py` (use weight resolver via get_caloric_balance)
  - `server/ingest.py` (use weight resolver for ride ingestion)
  - `frontend/src/pages/Settings.tsx` (Withings-managed weight field)
- **Key Dependencies:** `server/services/intervals_icu.update_weight()` at line 400, existing `body_measurements` table
- **Note:** PMC (`compute_daily_pmc` in `ingest.py`) already implements the full Withings-priority chain inline — no changes needed there.

## Micro-Step Checklist

- [x] Phase 1: Create weight resolver abstraction
  - [x] Step 1.A: Unit tests for `get_weight_for_date` + `get_current_weight`
  - [x] Step 1.B: Implement `server/services/weight.py`
  - [x] Step 1.C: Verify unit tests pass
- [x] Phase 2: Fix FTP history W/kg bug (Gap 3)
  - [x] Step 2.A: Fix `get_ftp_history_rows()` in `server/queries.py`
  - [x] Step 2.B: Verify unit tests pass
- [x] Phase 3: Gap 1 — Withings → ICU wellness push
  - [x] Step 3.A: Add unit tests for ICU push in `tests/unit/test_withings.py`
  - [x] Step 3.B: Add ICU push in `sync_weight()` in `server/services/withings.py`
  - [x] Step 3.C: Add ICU push in `handle_webhook_notification()` in `server/services/withings.py`
  - [x] Step 3.D: Verify unit tests pass
- [x] Phase 4: Consumer migrations
  - [x] Step 4.A: `server/coaching/agent.py:_build_system_instruction()` → `get_current_weight(conn)`
  - [x] Step 4.B: `server/coaching/tools.py:get_athlete_status()` → `get_current_weight(conn)`
  - [x] Step 4.C: `server/nutrition/agent.py:_build_system_instruction()` → `get_current_weight(conn)`
  - [x] Step 4.D: `server/nutrition/tools.py:get_caloric_balance()` → `get_weight_for_date(conn, date)` passed to `_estimate_daily_bmr(weight_kg)`
  - [x] Step 4.E: `server/ingest.py:parse_ride_json()` → `get_weight_for_date(conn, ride_date)` (with ride-file override after)
  - [x] Step 4.F: Verify all unit tests pass
- [x] Phase 5: Gap 2 — Settings UI read-only weight field
  - [x] Step 5.A: `frontend/src/pages/Settings.tsx` weight field read-only when Withings active
  - [x] Step 5.B: Frontend build verification

## Success Criteria

1. `server/services/weight.py` exports `get_weight_for_date` and `get_current_weight`.
2. All unit tests in `tests/unit/test_weight_service.py` pass.
3. `get_ftp_history_rows()` uses `AVG(weight)` per month from `daily_metrics` (not MAX).
4. `sync_weight()` and `handle_webhook_notification()` push to ICU after storing; ICU failure does not break the sync.
5. All weight reads in coaching and nutrition agents route through `get_current_weight(conn)`.
6. `parse_ride_json()` uses `get_weight_for_date(conn, ride_date)` as the base weight (ride-file weight overrides afterward).
7. Settings weight field shows "Managed by Withings" and is disabled when Withings connected + has measurements.
8. `pytest tests/unit/ -v` exits 0 with no failures.
