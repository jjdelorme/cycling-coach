# Plan Validation Report: Timezone Awareness (Full Platform Audit)

## Summary

*   **Overall Status:** PARTIAL -- Phase 0+1+2 substantially done, Phases 3+4 not done, critical regressions in 2 files
*   **Completion Rate:** ~70% of plan items verified as done; remaining 30% is a mix of not-implemented phases and bugs introduced by column removal

### Headline

The backend timezone transport (Phase 0), `rides.date` elimination from queries (Phase 1), and the schema migration from TEXT to TIMESTAMPTZ/DATE (Phase 2) are all implemented and working. All 310 unit tests pass. The `ContextVar`-based `dates.py` is correct. The `X-Client-Timezone` header flows from the frontend through ASGI middleware to `user_today()`.

However, **two files still reference the now-dropped `rides.date` column** (runtime crashes), the **frontend display layer is entirely unimplemented** (no `fmtDate`/`fmtDateStr`/`localDateStr` utilities in `format.ts`), many **nutrition/meal-plan components still use `toISOString().slice(0,10)`** (UTC-date bug), **Phase 3 (multi-athlete PMC `user_id`)** is not done, **Phase 4 (PMC rebuild)** is not done, and `ride_records.timestamp_utc` was not promoted to TIMESTAMPTZ.

---

## Phase-by-Phase Breakdown

### Phase 0 -- Timezone Transport (no schema change)

| Item | Status | Evidence |
|------|--------|----------|
| `X-Client-Timezone` header in `authHeaders()` | DONE | `frontend/src/lib/api.ts` line 11: `headers['X-Client-Timezone'] = Intl.DateTimeFormat().resolvedOptions().timeZone` |
| `ClientTimezoneMiddleware` in `server/main.py` | DONE | `server/main.py` lines 177-215: raw ASGI middleware, validates IANA name, sets `scope["state"]["client_tz_str"]` and calls `set_request_tz(tz)` |
| `server/utils/dates.py` uses `ContextVar` | DONE | `server/utils/dates.py` lines 6-38: `ContextVar("request_tz", default=ZoneInfo("UTC"))`, with `set_request_tz()`, `get_request_tz()`, `user_today()` |
| `threading.local` removed from `dates.py` | DONE | No `threading.local` in `dates.py`. Note: `threading.local` remains in `agent.py:77` and `nutrition/agent.py:64` for `_current_user_role`, but these are unrelated to timezone (role gating) and are acceptable |
| `server/dependencies.py` `get_client_tz()` | DONE | `server/dependencies.py` lines 6-14: reads `request.state.client_tz_str`, returns `ZoneInfo` |
| Fix `Dashboard.tsx` `toISOString` for "today" | DONE | `frontend/src/pages/Dashboard.tsx` lines 253-254: uses `now.getFullYear()`/`getMonth()`/`getDate()` (local date getters), not `toISOString()` |
| Fix `Analysis.tsx` `toISOString` for "today" | DONE | `frontend/src/pages/Analysis.tsx` lines 116-126: uses `new Date()` with local getters for `today` and `todayStr` |
| All `datetime.now()` business-logic calls fixed | DONE | Grep for `datetime.now()` (without timezone arg), `date.today()`, `datetime.today()` across `server/` returns **zero matches** |
| `athlete_settings["timezone"]` persistence removed | DONE | Grep for `athlete_settings.*timezone` returns zero matches |
| `_utc_to_local_date()` helper removed from ingest | DONE | Function no longer exists in `server/ingest.py`; replaced by `_start_time_to_date()` (line 39) |

**Phase 0 Status: DONE**

---

### Phase 1 -- Remove `rides.date` from Application Code

| Item | Status | Evidence |
|------|--------|----------|
| Ingest no longer computes/writes `rides.date` | DONE | `server/ingest.py` `ingest_rides()` (line 587-601): INSERT does not include `date` column. Only `start_time` is stored. |
| intervals.icu uses UTC `start_date`, not `start_date_local` | DONE | `server/services/intervals_icu.py` `map_activity_to_ride()` lines 304-312: prefers `start_date` (UTC), falls back to `start_date_local` only for existence check. Stores result as `start_time` |
| `rides.date` removed from ride list query | DONE | `server/routers/rides.py` line 36-37: `(start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date` |
| `rides.date` removed from daily summary | DONE | `server/routers/rides.py` lines 104-110: uses `AT TIME ZONE` pattern |
| `rides.date` removed from weekly summary | DONE | `server/routers/rides.py` lines 121-135: uses `AT TIME ZONE` pattern |
| `rides.date` removed from monthly summary | DONE | `server/routers/rides.py` lines 184-208: uses `TO_CHAR((start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE, 'YYYY-MM')` |
| `rides.date` removed from ride detail | DONE | `server/routers/rides.py` line 217: derives date via `AT TIME ZONE` |
| `rides.date` removed from ride deletion | DONE | `server/routers/rides.py` line 272: derives `local_date` via `AT TIME ZONE` |
| Coaching tools use `AT TIME ZONE` | DONE | `server/coaching/tools.py`: `_resolve_ride_id()` (line 29-33), `get_recent_rides()` (line 158-166), `get_upcoming_workouts()` (line 198-200), `get_training_summary()` (line 258-266), `get_power_curve()` (line 605-607), `get_planned_workout_for_ride()` (line 706-712), `get_athlete_nutrition_status()` (line 795-797), `set_ride_coach_comments()` (line 732-734) all use timezone-aware queries |
| Planning tools use `user_today()` | DONE | `server/coaching/planning_tools.py`: `get_week_summary()` line 395, `sync_workouts_to_garmin()` line 451, `update_athlete_setting()` line 820 |
| Sync service uses UTC for background | DONE | `server/services/sync.py`: `_get_athlete_tz()` returns `ZoneInfo("UTC")` (line 58); all date computations use `datetime.now(_tz)` |
| `queries.py` uses `user_today()` | DONE | `server/queries.py` line 37-38: `get_current_ftp()` calls `user_today()`. Line 84: `get_power_bests_rows()` calls `user_today()` |
| `database.py` `set_athlete_setting` uses `user_today()` | DONE | `server/database.py` lines 244-246: defaults `date_set` to `user_today()` |
| PMC computation uses `AT TIME ZONE` | DONE | `server/ingest.py` `compute_daily_pmc()` lines 387-392: groups rides by `(start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE` |
| `get_week_planned_and_actual()` uses `AT TIME ZONE` | DONE | `server/queries.py` lines 166-174: actual rides filtered via `AT TIME ZONE` pattern |
| **BUG: `server/services/weight.py` still references `rides.date`** | FAILED | `server/services/weight.py` line 37: `SELECT weight FROM rides WHERE date <= %s` -- **`rides.date` has been dropped; this will crash at runtime** |
| **BUG: `server/routers/nutrition.py` still references `rides.date`** | FAILED | `server/routers/nutrition.py` line 396: `SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s` -- **`rides.date` has been dropped; this will crash at runtime** |

**Phase 1 Status: PARTIAL -- 2 critical regressions remain**

---

### Phase 2 -- Schema Migration

| Item | Status | Evidence |
|------|--------|----------|
| `rides.start_time` TEXT -> TIMESTAMPTZ | DONE | `migrations/0006_timezone_schema.sql` lines 24-43: conditional DO block checks data_type, appends `+00:00` to naive timestamps, casts to TIMESTAMPTZ |
| `rides.date` column DROP | DONE | `migrations/0006_timezone_schema.sql` line 50: `ALTER TABLE rides DROP COLUMN IF EXISTS date` |
| `daily_metrics.date` TEXT -> DATE | DONE | `migrations/0006_timezone_schema.sql` lines 62-63: loop includes `('daily_metrics', 'date')` |
| `planned_workouts.date` TEXT -> DATE | DONE | Same migration loop |
| `periodization_phases.start_date` TEXT -> DATE | DONE | Same migration loop |
| `periodization_phases.end_date` TEXT -> DATE | DONE | Same migration loop |
| `power_bests.date` TEXT -> DATE | DONE | Same migration loop |
| `athlete_settings.date_set` TEXT -> DATE | DONE | Same migration loop |
| `planned_meals.date` TEXT -> DATE | DONE | Same migration loop (added beyond plan scope) |
| `meal_logs.date` TEXT -> DATE | DONE | Same migration loop (added beyond plan scope) |
| `ride_records.timestamp_utc` TEXT -> TIMESTAMPTZ | NOT DONE | Plan specifies this column should be promoted. Migration `0006` does not touch `ride_records.timestamp_utc`. |
| `SUBSTR(date, 1, 7)` -> `TO_CHAR(date, 'YYYY-MM')` in `queries.py` | DONE | `server/queries.py` lines 109, 119: uses `TO_CHAR(date, 'YYYY-MM')` |
| `SUBSTR` -> `TO_CHAR` in `routers/rides.py` | DONE | `server/routers/rides.py` line 186: uses `TO_CHAR((start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE, 'YYYY-MM')` |
| Python read sites handle `datetime.date` returns | DONE | `server/queries.py`: `get_current_pmc_row()` (line 57), `get_pmc_row_for_date()` (line 71), `get_power_bests_rows()` (line 98-103), `get_ftp_history_rows()` (line 109-119), `get_periodization_phases()` (lines 141-147), `get_week_planned_and_actual()` (lines 179-183) all convert `date` to `str()` |
| Index on `rides(start_time)` added | DONE | Migration line 86: `CREATE INDEX IF NOT EXISTS idx_rides_start_time ON rides(start_time)` |
| Orphaned `idx_rides_date` dropped | DONE | Migration line 89: `DROP INDEX IF EXISTS idx_rides_date` |

**Phase 2 Status: PARTIAL -- `ride_records.timestamp_utc` not promoted**

---

### Phase 3 -- Multi-Athlete PMC (`user_id` on `daily_metrics`)

| Item | Status | Evidence |
|------|--------|----------|
| `daily_metrics` has `user_id` column | NOT DONE | Migration `0006` does not add `user_id` to `daily_metrics`. No ALTER TABLE for this. |
| `daily_metrics` PK changed to `(user_id, date)` | NOT DONE | No change to primary key in any migration |
| `compute_daily_pmc()` scoped by `user_id` | NOT DONE | `server/ingest.py` `compute_daily_pmc()` has no `user_id` parameter or filter |
| PMC queries scoped by `user_id` | NOT DONE | `server/queries.py` `get_current_pmc_row()` and `get_pmc_row_for_date()` have no `user_id` filter |

**Phase 3 Status: NOT DONE**

---

### Phase 4 -- Rebuild PMC from Corrected Data

| Item | Status | Evidence |
|------|--------|----------|
| PMC rebuild trigger after migration | NOT DONE | No code or migration step triggers a full PMC rebuild. The sync service does recompute PMC after downloading rides (`server/services/sync.py` line 941), but there is no explicit post-migration rebuild |

**Phase 4 Status: NOT DONE** (acceptable to defer until Phase 3 is done)

---

### Frontend Display Layer

| Item | Status | Evidence |
|------|--------|----------|
| `fmtDate(isoUtc)` in `format.ts` | NOT DONE | `frontend/src/lib/format.ts` has no `fmtDate` function for UTC timestamp formatting. The existing `fmtTime` (line 47) formats seconds-as-duration, not ISO timestamps |
| `fmtDateLong(isoUtc)` in `format.ts` | NOT DONE | Not present |
| `fmtDateTime(isoUtc)` in `format.ts` | NOT DONE | Not present |
| `fmtTime(isoUtc)` for timestamps in `format.ts` | NOT DONE | Not present (existing `fmtTime` takes seconds) |
| `fmtDateStr(dateStr)` in `format.ts` | NOT DONE | Not present |
| `fmtDateStrLong(dateStr)` in `format.ts` | NOT DONE | Not present |
| `localDateStr(d?)` in `format.ts` | NOT DONE | Not present |
| Call site updates (Rides.tsx, Calendar.tsx, Dashboard.tsx, UserManagement.tsx) | NOT DONE | No call sites updated to use format utilities that don't exist |
| `Nutrition.tsx` `toISOString().slice(0,10)` | NOT DONE | Line 16 and 170 still use `new Date().toISOString().slice(0, 10)` |
| `MealTimeline.tsx` `toISOString().slice(0,10)` | NOT DONE | Lines 15, 23, 30 |
| `NutritionDashboardWidget.tsx` `toISOString().slice(0,10)` | NOT DONE | Line 11 |
| `MealPlanCalendar.tsx` `toISOString().slice(0,10)` | NOT DONE | Lines 21, 29, 43, 48, 52, 94, 95, 106, 107 |
| `MealPlanDayDetail.tsx` `toISOString().slice(0,10)` | NOT DONE | Line 27 |
| `MacroCard.tsx` `toISOString().slice(0,10)` | NOT DONE | Line 195 |

**Frontend Display Layer Status: NOT DONE** (zero of the planned format utilities or call site updates exist)

---

## File-by-File Status (Plan's Affected Files Tables)

### Backend -- Critical

| File | Plan Line(s) | Was Naive `datetime.now()`? | Current Status |
|------|-------------|----------------------------|----------------|
| `server/coaching/agent.py` | 95-97, 146 | Yes | FIXED -- lines 101-103: `datetime.now(tz)` using `get_request_tz()`. Line 155: `seven_days_ago` derived from tz-aware `today` |
| `server/coaching/tools.py` | 149, 189-190, 244, 294, 593-594 | Yes | FIXED -- all calls use `datetime.now(get_request_tz())` or `user_today()` |
| `server/routers/rides.py` | 92 | Yes (`date.today()`) | FIXED -- line 101: uses `user_today(tz)` with FastAPI dependency |

### Backend -- High

| File | Plan Line(s) | Was Naive? | Current Status |
|------|-------------|------------|----------------|
| `server/coaching/planning_tools.py` | 394, 469-470 | Yes | FIXED -- line 395: `user_today()`. Line 451: `datetime.now(get_request_tz())` |
| `server/services/sync.py` | 370-372, 639-640, 708-713 | Yes | FIXED -- all uses go through `_get_athlete_tz()` which returns `ZoneInfo("UTC")` (correct for background sync) |

### Backend -- Medium

| File | Plan Line(s) | Was Naive? | Current Status |
|------|-------------|------------|----------------|
| `server/queries.py` | 37, 72 | Yes | FIXED -- line 38: `user_today()`. Line 84: `user_today()` |
| `server/database.py` | 456 | Yes | FIXED -- line 245: `user_today()` |
| `server/ingest.py` | 84, 178, 404 | Yes | FIXED -- FIT ingest uses `_start_time_to_date()` (UTC from source file). PMC uses `user_today()` at line 441 |
| `server/services/intervals_icu.py` | 171-173, 414 | Yes | FIXED -- lines 171-172: `datetime.now(timezone.utc)` (correct for API calls). Line 416-417: `user_today()` |

### Frontend -- Critical/High

| File | Plan Line(s) | Was Naive? | Current Status |
|------|-------------|------------|----------------|
| `Dashboard.tsx` | 250 | Yes (`toISOString`) | FIXED -- line 254: local date getters |
| `Analysis.tsx` | 116 | Yes (`toISOString`) | FIXED -- line 121-125: local date getters |
| `api.ts` | `authHeaders()` | Missing header | FIXED -- line 11: `X-Client-Timezone` header |

---

## Remaining Naive `datetime.now()` / `date.today()` / `datetime.today()` Calls

Grep across `server/` for `datetime.now()` without timezone arg, `date.today()`, and `datetime.today()`:

**Zero matches found.** All business-logic calls have been replaced with timezone-aware equivalents.

The following existing `datetime.now(timezone.utc)` calls are correct and intentionally preserved (audit/system timestamps):
- `server/services/sync.py` line 39: `_now_iso()`
- `server/coaching/session_service.py`: session timestamps
- `server/coaching/memory_service.py`: memory entry timestamps
- `server/auth.py`: JWT claims
- `server/services/intervals_icu.py` lines 171-172: API fetch window (UTC is correct here)

---

## Anti-Shortcut and Quality Scan

*   **Placeholders/TODOs:** None found in modified server or frontend files. The only "placeholder" match is `_adapt_sql` referencing "SQLite-style placeholders" which is a comment about the SQL conversion logic, not a TODO.
*   **Test Integrity:** All 310 unit tests pass (verified via `pytest tests/unit/ -v`). No tests were commented out, skipped, or gutted. Timezone-specific tests exist in `tests/unit/test_dates.py` (7 tests) and `tests/unit/test_database_timezone.py` (2 tests) and `tests/unit/test_date_type_handling.py` (12 tests) covering ContextVar isolation, user_today behavior, ASGI middleware propagation, and DATE type handling.
*   **Test Coverage for New Code:** The `ContextVar` implementation, `user_today()`, and ASGI middleware all have dedicated unit tests. The DATE type migration has comprehensive tests for every read path (`test_date_type_handling.py`).

---

## Gap List (Ordered by Priority)

### Priority 1: CRITICAL -- Runtime Crashes

1. **`server/services/weight.py` line 37** -- `SELECT weight FROM rides WHERE date <= %s` references dropped `rides.date` column. Must be changed to `WHERE start_time <= %s::TIMESTAMPTZ ORDER BY start_time DESC` or similar.

2. **`server/routers/nutrition.py` line 396** -- `SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s` references dropped `rides.date` column. Must be changed to `WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE` with timezone parameter.

### Priority 2: HIGH -- UTC Date Bug in Frontend Nutrition

3. **`frontend/src/pages/Nutrition.tsx`** lines 16, 170 -- `new Date().toISOString().slice(0, 10)` produces UTC date. Should use local date getters.

4. **`frontend/src/components/MealTimeline.tsx`** lines 15, 23, 30 -- same UTC date bug.

5. **`frontend/src/components/NutritionDashboardWidget.tsx`** line 11 -- same.

6. **`frontend/src/components/MealPlanCalendar.tsx`** lines 21, 29, 43, 48, 52, 94, 95, 106, 107 -- same.

7. **`frontend/src/components/MealPlanDayDetail.tsx`** line 27 -- same.

8. **`frontend/src/components/MacroCard.tsx`** line 195 -- same.

### Priority 3: MEDIUM -- Missing Planned Frontend Utilities

9. **`frontend/src/lib/format.ts`** -- Missing all 7 date formatting functions specified in the plan: `fmtDate`, `fmtDateLong`, `fmtDateTime`, `fmtTime` (for timestamps), `fmtDateStr`, `fmtDateStrLong`, `localDateStr`. These are needed to handle the new `TIMESTAMPTZ` and `DATE` column types correctly.

10. **Frontend call site updates** -- None of the planned call site updates (Rides.tsx line 251/278, Calendar.tsx line 218, Dashboard.tsx line 358, UserManagement.tsx line 152, etc.) have been made.

### Priority 4: MEDIUM -- Schema Gap

11. **`ride_records.timestamp_utc` not promoted to TIMESTAMPTZ** -- Plan specifies this column should be converted from TEXT. Migration `0006` does not touch it. Low urgency since no timezone query uses this column, but it is a deviation from the plan.

### Priority 5: LOW -- Stale Comment

12. **`server/routers/analysis.py` lines 65-68** -- Code comment references `rides(date)` for a potential index: `CREATE INDEX IF NOT EXISTS idx_rides_date ON rides(date)`. This column no longer exists; the comment should reference `rides(start_time)`.

### Priority 6: DEFERRED -- Phase 3+4

13. **Phase 3: Multi-Athlete PMC** -- `daily_metrics` needs `user_id` column, PK change, and `compute_daily_pmc()` scoping. This is a feature addition, not a bug.

14. **Phase 4: PMC Rebuild** -- Depends on Phase 3. Not applicable until Phase 3 is implemented.

---

## Test Status

```
$ pytest tests/unit/ -v
310 passed, 1 warning in 10.83s
```

All tests pass. No failures. No skipped tests.

---

## Conclusion

The timezone awareness implementation is **substantially complete for the core backend** (Phases 0-2). The `ContextVar`-based timezone transport, the `AT TIME ZONE` query pattern, and the schema migration are all correctly implemented and tested. The architecture is sound.

However, the implementation is **not safe to deploy** due to two critical runtime crashes in `server/services/weight.py` and `server/routers/nutrition.py` that reference the now-dropped `rides.date` column. These must be fixed before any deployment that includes migration `0006`.

The frontend display layer (format utilities and `toISOString` fixes for nutrition components) is entirely unimplemented. The Dashboard and Analysis pages were fixed, but the Nutrition pages and related components still have the UTC date bug.

Phase 3 (multi-athlete PMC) and Phase 4 (PMC rebuild) are not implemented but are documented as future work in the plan itself.

**Actionable recommendations for the Engineer:**

1. **Fix `weight.py` and `nutrition.py`** immediately -- these are runtime crashes.
2. **Fix nutrition frontend `toISOString()` calls** -- these produce wrong dates for users not in UTC.
3. **Add `format.ts` date utilities** -- needed for correct date display after the schema migration.
4. **Promote `ride_records.timestamp_utc`** to TIMESTAMPTZ in a follow-up migration.
5. **Phase 3+4** can be deferred to a separate work item.
