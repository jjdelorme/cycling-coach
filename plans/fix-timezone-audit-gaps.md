# Fix Plan: Timezone Awareness Audit Gaps

**Source:** `plans/reports/AUDIT_timezone-awareness-full.md`
**Branch:** `worktree-fix-timezone-awareness`
**Date:** 2026-04-15

---

## Overview

12 gaps remain after the Phase 0-2 timezone implementation. Two are runtime crashes (P1), six are frontend UTC date bugs (P2), two are missing frontend utilities + call site updates (P3), one is a schema gap (P4), and one is a stale comment (P5).

Phases 3 (multi-athlete PMC) and 4 (PMC rebuild) are explicitly deferred and not covered here.

---

## Parallelism Map

Tasks are grouped into batches that can be dispatched to independent engineers simultaneously. Dependencies between batches are noted.

```
Batch A (backend, independent):  Tasks 1, 2, 11, 12
Batch B (frontend foundation):   Task 9
Batch C (frontend consumers):    Tasks 3, 4, 5, 6, 7, 8   (depends on Batch B)
Batch D (frontend call sites):   Task 10                    (depends on Batch B)
```

Within Batch A, all four tasks touch different files and have zero overlap. Within Batch C, all six tasks touch different files. Batch D touches files that Batch C does not (Rides.tsx, Calendar.tsx, Dashboard.tsx, UserManagement.tsx).

---

## Task 1: Fix `server/services/weight.py` -- `rides.date` reference (P1 CRITICAL)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/server/services/weight.py`
**Lines:** 36-39
**Problem:** Query `SELECT weight FROM rides WHERE date <= %s` references the dropped `rides.date` column. This will crash at runtime.

**Pattern:** The weight resolver queries rides for a weight on or before a given date. Since `rides.date` is dropped, the local date must be derived from `start_time` using the `AT TIME ZONE` pattern. However, `get_weight_for_date()` does not receive a timezone parameter -- it only receives `conn` and `date`. The timezone must come from the request context via `get_request_tz()`.

**Before (lines 35-39):**
```python
    # 2. Ride-recorded weight -- most recent ride on or before date
    row = conn.execute(
        "SELECT weight FROM rides WHERE date <= %s AND weight IS NOT NULL AND weight > 0 "
        "ORDER BY date DESC LIMIT 1",
        (date,),
    ).fetchone()
```

**After:**
```python
    # 2. Ride-recorded weight -- most recent ride on or before date
    from server.utils.dates import get_request_tz
    tz_name = str(get_request_tz())
    row = conn.execute(
        "SELECT weight FROM rides "
        "WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE <= %s::DATE "
        "AND weight IS NOT NULL AND weight > 0 "
        "ORDER BY start_time DESC LIMIT 1",
        (tz_name, date),
    ).fetchone()
```

**Details:**
- The import should be placed at function scope (line 36) since `get_request_tz` is only needed for this one query path. Other callers of `get_weight_for_date` (from ingest, nutrition tools) operate in request context where the ContextVar is already set.
- `ORDER BY date DESC` must change to `ORDER BY start_time DESC` since `date` no longer exists.
- The `start_time::TIMESTAMPTZ AT TIME ZONE %s` pattern is established in `server/coaching/tools.py` line 796 and `server/routers/rides.py` line 36.
- Background callers (e.g., `server/ingest.py` line 114) call `get_weight_for_date(conn, ride_date)` where `ride_date` is derived from a ride's start_time. For these callers, the ContextVar defaults to UTC, which is correct since ingest runs outside an HTTP request context and the ride dates are already UTC-derived.

**Test verification:** `pytest tests/unit/ -v` -- existing tests should still pass. No new tests are strictly required because the function signature is unchanged and the query behavior is semantically identical; however, an integration test that inserts a ride with weight and calls `get_weight_for_date` would confirm the fix works against a live database. The existing integration test suite in `scripts/run_integration_tests.sh` should be run.

**Dependencies:** None. Independent of all other tasks.

---

## Task 2: Fix `server/routers/nutrition.py` -- `rides.date` reference (P1 CRITICAL)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/server/routers/nutrition.py`
**Lines:** 395-399
**Problem:** Query `SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s` references the dropped `rides.date` column. This will crash at runtime on the `GET /api/nutrition/daily-summary` endpoint.

**Pattern:** The identical fix already exists in `server/coaching/tools.py` lines 794-798 (`get_athlete_nutrition_status` tool). That code uses:
```python
tz_name = get_request_tz().key
...
"WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE",
(tz_name, date),
```

The `daily_summary` endpoint in `nutrition.py` is a FastAPI route handler, so `get_request_tz()` is available (the ContextVar is set by the ASGI middleware on every request). Alternatively, we can add a `get_client_tz` dependency to the route signature for explicitness and consistency with `server/routers/rides.py`.

**Preferred approach:** Use the `get_client_tz` FastAPI dependency for consistency with other routers.

**Before (lines 384-399):**
```python
@router.get("/daily-summary")
async def daily_summary(date: str = "", user: CurrentUser = Depends(require_read)):
    """Get aggregated macros and caloric balance for a date."""
    from server.utils.dates import user_today
    if not date:
        date = user_today()

    with get_db() as conn:
        totals = get_daily_meal_totals(conn, date)
        targets = get_macro_targets(conn)

        ride_row = conn.execute(
            "SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s",
            (date,),
        ).fetchone()
```

**After (lines 384-401):**
```python
@router.get("/daily-summary")
async def daily_summary(
    date: str = "",
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    """Get aggregated macros and caloric balance for a date."""
    from server.utils.dates import user_today
    if not date:
        date = user_today(tz)

    tz_name = str(tz)
    with get_db() as conn:
        totals = get_daily_meal_totals(conn, date)
        targets = get_macro_targets(conn)

        ride_row = conn.execute(
            "SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides "
            "WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE",
            (tz_name, date),
        ).fetchone()
```

**Additional changes required at the top of the file:**

Add imports at line 1-6 area. Currently the file imports from `server.auth`, `server.models.schemas`, `server.database`, `server.queries`, and `server.nutrition.photo`. Two new imports are needed:

**Before (line 1):**
```python
"""Nutrition meal logging and Nutritionist chat endpoints."""
```

**After the existing imports (add after the `from server.nutrition.photo import ...` line, around line 23):**
```python
from zoneinfo import ZoneInfo
from server.dependencies import get_client_tz
```

**Note:** The `user_today()` call on line 389 (original) should also be changed to `user_today(tz)` so the default date is computed using the explicit timezone from the dependency, not the implicit ContextVar. This is for consistency and testability, matching the pattern in `server/routers/rides.py` line 101: `user_today(tz)`.

**Test verification:** `pytest tests/unit/ -v` -- all 310 tests should pass. Integration test: `./scripts/run_integration_tests.sh`. The endpoint can also be manually tested with `curl http://localhost:8000/api/nutrition/daily-summary`.

**Dependencies:** None. Independent of all other tasks.

---

## Task 3: Fix `frontend/src/pages/Nutrition.tsx` -- `toISOString` UTC bug (P2)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/frontend/src/pages/Nutrition.tsx`
**Instances:** 2

**Instance 3a -- Line 16 (initial state):**

**Before:**
```typescript
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
```

**After:**
```typescript
  const [date, setDate] = useState(() => localDateStr())
```

**Instance 3b -- Line 170 (onMealSaved callback):**

**Before:**
```typescript
          const today = new Date().toISOString().slice(0, 10)
```

**After:**
```typescript
          const today = localDateStr()
```

**Import addition (line 1 area):** Add `localDateStr` to imports. Currently no `format.ts` import exists in this file. Add after existing imports (after line 9):

```typescript
import { localDateStr } from '../lib/format'
```

**Dependencies:** Depends on Task 9 (`localDateStr` must exist in `format.ts`).

---

## Task 4: Fix `frontend/src/components/MealTimeline.tsx` -- `toISOString` UTC bug (P2)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/frontend/src/components/MealTimeline.tsx`
**Instances:** 3

**Instance 4a -- Line 15:**

**Before:**
```typescript
  const today = new Date().toISOString().slice(0, 10)
```

**After:**
```typescript
  const today = localDateStr()
```

**Instance 4b -- Line 23:**

**Before:**
```typescript
    if (date === yesterday.toISOString().slice(0, 10)) return 'Yesterday'
```

**After:**
```typescript
    if (date === localDateStr(yesterday)) return 'Yesterday'
```

**Instance 4c -- Line 30:**

**Before:**
```typescript
    onDateChange(next.toISOString().slice(0, 10))
```

**After:**
```typescript
    onDateChange(localDateStr(next))
```

**Import addition:** Add after line 4 (after the `type { MealSummary }` import):

```typescript
import { localDateStr } from '../lib/format'
```

**Dependencies:** Depends on Task 9.

---

## Task 5: Fix `frontend/src/components/NutritionDashboardWidget.tsx` -- `toISOString` UTC bug (P2)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/frontend/src/components/NutritionDashboardWidget.tsx`
**Instances:** 1

**Instance 5a -- Line 11:**

**Before:**
```typescript
  const today = new Date().toISOString().slice(0, 10)
```

**After:**
```typescript
  const today = localDateStr()
```

**Import addition:** Add after line 4 (after the `Apple, ChevronRight` import):

```typescript
import { localDateStr } from '../lib/format'
```

**Dependencies:** Depends on Task 9.

---

## Task 6: Fix `frontend/src/components/MealPlanCalendar.tsx` -- `toISOString` UTC bug (P2)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/frontend/src/components/MealPlanCalendar.tsx`
**Instances:** 9 occurrences of `toISOString().slice(0, 10)` across 4 logical contexts.

**Instance 6a -- Line 21 (inside `getMonday` helper):**

**Before:**
```typescript
  return d.toISOString().slice(0, 10)
```

**After:**
```typescript
  return localDateStr(d)
```

**Instance 6b -- Line 29 (initial state for `weekStart`):**

**Before:**
```typescript
  const [weekStart, setWeekStart] = useState(() => getMonday(new Date().toISOString().slice(0, 10)))
```

**After:**
```typescript
  const [weekStart, setWeekStart] = useState(() => getMonday(localDateStr()))
```

**Instance 6c -- Line 43 (shiftWeek):**

**Before:**
```typescript
    setWeekStart(d.toISOString().slice(0, 10))
```

**After:**
```typescript
    setWeekStart(localDateStr(d))
```

**Instance 6d -- Line 48 (goToThisWeek):**

**Before:**
```typescript
    setWeekStart(getMonday(new Date().toISOString().slice(0, 10)))
```

**After:**
```typescript
    setWeekStart(getMonday(localDateStr()))
```

**Instance 6e -- Line 52 (today constant):**

**Before:**
```typescript
  const today = new Date().toISOString().slice(0, 10)
```

**After:**
```typescript
  const today = localDateStr()
```

**Instance 6f -- Lines 94-95 (goToPrevDay, cross-week navigation):**

**Before:**
```typescript
        setWeekStart(getMonday(d.toISOString().slice(0, 10)))
        setSelectedDate(d.toISOString().slice(0, 10))
```

**After:**
```typescript
        setWeekStart(getMonday(localDateStr(d)))
        setSelectedDate(localDateStr(d))
```

**Instance 6g -- Lines 106-107 (goToNextDay, cross-week navigation):**

**Before:**
```typescript
        setWeekStart(d.toISOString().slice(0, 10)))
        setSelectedDate(d.toISOString().slice(0, 10))
```

**After:**
```typescript
        setWeekStart(getMonday(localDateStr(d)))
        setSelectedDate(localDateStr(d))
```

**Import addition:** Add after line 4 (after `MealPlanDayDetail` import):

```typescript
import { localDateStr } from '../lib/format'
```

**Dependencies:** Depends on Task 9.

---

## Task 7: Fix `frontend/src/components/MealPlanDayDetail.tsx` -- `toISOString` UTC bug (P2)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/frontend/src/components/MealPlanDayDetail.tsx`
**Instances:** 1

**Instance 7a -- Line 27:**

**Before:**
```typescript
  const today = new Date().toISOString().slice(0, 10)
```

**After:**
```typescript
  const today = localDateStr()
```

**Import addition:** Add after line 5 (after the `type { MealPlanDay, PlannedMeal }` import):

```typescript
import { localDateStr } from '../lib/format'
```

**Dependencies:** Depends on Task 9.

---

## Task 8: Fix `frontend/src/components/MacroCard.tsx` -- `toISOString` UTC bug (P2)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/frontend/src/components/MacroCard.tsx`
**Instances:** 1

**Instance 8a -- Line 195:**

**Before:**
```typescript
                  max={new Date().toISOString().slice(0, 10)}
```

**After:**
```typescript
                  max={localDateStr()}
```

**Import addition:** Add after line 6 (after the `type { MealSummary }` import):

```typescript
import { localDateStr } from '../lib/format'
```

**Dependencies:** Depends on Task 9.

---

## Task 9: Add date formatting utilities to `frontend/src/lib/format.ts` (P3)

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/frontend/src/lib/format.ts`
**Lines:** Append after line 113 (after the `zoneLabel` function).

**Problem:** Zero date/time formatting utilities exist. The plan at `plans/timezone-awareness.md` lines 292-341 specifies 7 new functions. These are needed by Tasks 3-8 and Task 10.

**Code to append at end of file (after line 113):**

```typescript

// ---------------------------------------------------------------------------
// Date / time formatting for timezone-aware display
// ---------------------------------------------------------------------------

// For UTC timestamp strings from the server (rides.start_time, sync timestamps)
// new Date() parses UTC correctly; toLocaleDateString renders in browser timezone.
export function fmtDateShort(isoUtc: string): string {
  return new Date(isoUtc).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  })
}

export function fmtDateLong(isoUtc: string): string {
  return new Date(isoUtc).toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  })
}

export function fmtDateTime(isoUtc: string): string {
  return new Date(isoUtc).toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  })
}

export function fmtTimestamp(isoUtc: string): string {
  return new Date(isoUtc).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit',
  })
}

// For date-only strings (YYYY-MM-DD) from planned_workouts, periodization_phases, etc.
// Appending T00:00:00 forces local midnight -- prevents UTC shift turning Apr 9 into Apr 8.
export function fmtDateStr(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  })
}

export function fmtDateStrLong(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  })
}

// Canonical local YYYY-MM-DD string for use as API query parameters.
// Replaces scattered getFullYear()/getMonth()/getDate() constructions.
export function localDateStr(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
```

**Naming note:** The plan originally specified `fmtDate` and `fmtTime` for timestamps, but `format.ts` already exports `fmtTime(seconds: number)` at line 47 for duration formatting. To avoid a name collision and confusion, this plan uses:
- `fmtDateShort` instead of `fmtDate` (for UTC timestamp to short date)
- `fmtTimestamp` instead of `fmtTime` (for UTC timestamp to time-of-day)

The existing `fmtTime(seconds)` at line 47 is left untouched.

**Test verification:** `cd frontend && npx tsc --noEmit` -- TypeScript compilation should succeed with no errors. Additionally, frontend unit tests (if any) should pass.

**Dependencies:** None. This is a foundation task that Tasks 3-8 and Task 10 depend on.

---

## Task 10: Call site updates in Rides.tsx, Calendar.tsx, Dashboard.tsx, UserManagement.tsx (P3) -- DONE

**Problem:** Several components use inline date formatting that should use the new `format.ts` utilities for consistency and correctness.

### 10a: `frontend/src/pages/Rides.tsx` line 251

**Before (lines 248-251):**
```typescript
      const ts = raw.includes('Z') || raw.includes('+') || raw.includes('T') && raw.match(/[+-]\d{2}:?\d{2}$/)
        ? raw
        : raw + 'Z'
      return new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
```

**After:**
```typescript
      const ts = raw.includes('Z') || raw.includes('+') || raw.includes('T') && raw.match(/[+-]\d{2}:?\d{2}$/)
        ? raw
        : raw + 'Z'
      return fmtTimestamp(ts)
```

**Import update (line 14):**

**Before:**
```typescript
import { fmtDuration, fmtDistance, fmtElevation, fmtTime, zoneColor, fmtSport } from '../lib/format'
```

**After:**
```typescript
import { fmtDuration, fmtDistance, fmtElevation, fmtTime, zoneColor, fmtSport, fmtTimestamp, fmtDateStr } from '../lib/format'
```

### 10b: `frontend/src/pages/Rides.tsx` line 278

**Before:**
```typescript
                {currentDate && new Date(currentDate + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
```

**After:**
```typescript
                {currentDate && fmtDateStr(currentDate)}
```

### 10c: `frontend/src/pages/Calendar.tsx` line 217

**Before:**
```typescript
              {new Date(selectedDay + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
```

**After:**
```typescript
              {fmtDateStrLong(selectedDay)}
```

**Import update (line 4):**

**Before:**
```typescript
import { fmtDuration, fmtDistance, fmtSport } from '../lib/format'
```

**After:**
```typescript
import { fmtDuration, fmtDistance, fmtSport, fmtDateStrLong } from '../lib/format'
```

### 10d: `frontend/src/pages/Dashboard.tsx` line 357

**Before:**
```typescript
                    {nextWorkout.date === today ? 'Today' : new Date(nextWorkout.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
```

**After:**
```typescript
                    {nextWorkout.date === today ? 'Today' : fmtDateStr(nextWorkout.date)}
```

**Import update (line 18):**

**Before:**
```typescript
import { fmtDuration, fmtDistance, fmtWeight, fmtSport } from '../lib/format'
```

**After:**
```typescript
import { fmtDuration, fmtDistance, fmtWeight, fmtSport, fmtDateStr, localDateStr } from '../lib/format'
```

### 10e: `frontend/src/pages/Dashboard.tsx` line 230

The inline `fmt` function can be replaced with `localDateStr`:

**Before (line 230):**
```typescript
    const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
```

**After:**
```typescript
    const fmt = localDateStr
```

This preserves the same interface (`fmt(d: Date) => string`) while using the shared utility. The rest of the function (`mondays.push(fmt(m))` at line 235, `thisMonday: fmt(thisMon)` at line 237) works unchanged.

### 10f: `frontend/src/components/UserManagement.tsx` line 152

**Before:**
```typescript
                        {u.last_login ? new Date(u.last_login).toLocaleDateString() : 'Never Active'}
```

**After:**
```typescript
                        {u.last_login ? fmtDateShort(u.last_login) : 'Never Active'}
```

**Import addition (add after line 3):**

```typescript
import { fmtDateShort } from '../lib/format'
```

**Test verification:** `cd frontend && npx tsc --noEmit` and `cd frontend && npm run build`.

**Dependencies:** Depends on Task 9 (format utilities must exist first).

---

## Task 11: Promote `ride_records.timestamp_utc` TEXT to TIMESTAMPTZ (P4) -- DONE

**File to create:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/migrations/0007_ride_records_timestamp.sql`

**Pattern:** Follow the idempotent DO-block pattern from `migrations/0006_timezone_schema.sql` lines 24-43.

**Migration content:**

```sql
-- 0007_ride_records_timestamp.sql
-- Promote ride_records.timestamp_utc from TEXT to TIMESTAMPTZ.
--
-- WHY: The timezone schema migration (0006) promoted rides.start_time to
-- TIMESTAMPTZ but missed ride_records.timestamp_utc. This column stores
-- per-second UTC timestamps from FIT file recordings. Promoting to
-- TIMESTAMPTZ enables proper timestamp arithmetic and type safety.
--
-- This is a potentially large ALTER (ride_records can have millions of rows)
-- but is safe because all values are already UTC ISO8601 strings.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'ride_records' AND column_name = 'timestamp_utc'
      AND data_type = 'text'
  ) THEN
    -- Append '+00:00' to timestamps missing timezone info
    UPDATE ride_records
    SET timestamp_utc = timestamp_utc || '+00:00'
    WHERE timestamp_utc IS NOT NULL
      AND timestamp_utc NOT LIKE '%Z'
      AND timestamp_utc NOT LIKE '%+%'
      AND LENGTH(timestamp_utc) > 10
      AND timestamp_utc !~ '[+-]\d{2}:\d{2}$';

    -- Cast to TIMESTAMPTZ
    ALTER TABLE ride_records ALTER COLUMN timestamp_utc TYPE TIMESTAMPTZ
      USING timestamp_utc::TIMESTAMPTZ;
  END IF;
END $$;
```

**Risk:** The `ride_records` table can be very large (millions of rows). The UPDATE + ALTER TABLE will take time and hold a lock. For production, this should be tested on a staging copy first. The idempotent guard (`IF EXISTS ... data_type = 'text'`) makes it safe to re-run.

**Test verification:** 
1. Start local test DB: `podman run -d --name coach-test-db -p 5433:5432 -e POSTGRES_DB=coach_test -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=dev -e POSTGRES_HOST_AUTH_METHOD=trust --tmpfs /var/lib/postgresql/data docker.io/library/postgres:16-alpine`
2. Run migrations: `DATABASE_URL=postgresql://postgres:dev@localhost:5433/coach_test python -m server.migrate`
3. Verify column type: `psql -h localhost -p 5433 -U postgres coach_test -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'ride_records' AND column_name = 'timestamp_utc';"` -- should return `timestamp with time zone`.
4. Clean up: `podman rm -f coach-test-db`

**Dependencies:** None. Independent of all other tasks.

---

## Task 12: Fix stale comment in `server/routers/analysis.py` (P5 LOW) -- DONE

**File:** `/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/server/routers/analysis.py`
**Lines:** 65-68

**Problem:** Comment references `rides(date)` for a potential index, but that column was dropped in migration 0006. The comment should reference `rides(start_time)` instead, which already has an index (`idx_rides_start_time` created in migration 0006 line 86).

**Before (lines 64-68):**
```python
    PERFORMANCE NOTE: This query does a full scan of ride_records joined to rides.
    Adding a composite index on ride_records(ride_id, power) and an index on
    rides(date) would significantly speed up filtered queries.
    Example migration:
      CREATE INDEX IF NOT EXISTS idx_ride_records_ride_id_power ON ride_records(ride_id, power);
      CREATE INDEX IF NOT EXISTS idx_rides_date ON rides(date);
```

**After:**
```python
    PERFORMANCE NOTE: This query does a full scan of ride_records joined to rides.
    Adding a composite index on ride_records(ride_id, power) would speed up
    filtered queries. An index on rides(start_time) already exists (idx_rides_start_time).
    Example migration:
      CREATE INDEX IF NOT EXISTS idx_ride_records_ride_id_power ON ride_records(ride_id, power);
```

**Dependencies:** None. Independent of all other tasks.

---

## Testing Strategy

### Unit Tests (all tasks)
```bash
source venv/bin/activate
pytest tests/unit/ -v
```
Expected: all 310+ tests pass, no regressions.

### TypeScript Compilation (Tasks 3-10)
```bash
cd frontend && npx tsc --noEmit
```
Expected: zero errors.

### Frontend Build (Tasks 3-10)
```bash
cd frontend && npm run build
```
Expected: successful production build.

### Integration Tests (Tasks 1, 2, 11)
```bash
./scripts/run_integration_tests.sh -v
```
Expected: all integration tests pass.

### Manual Smoke Test (Tasks 1-2)
After starting the dev server (`./scripts/dev.sh`):
1. Navigate to Nutrition page, check daily summary loads without 500 error.
2. If weight data exists, verify the PMC/settings pages still resolve weight correctly.

---

## Success Criteria

1. Zero references to `rides.date` remain in any `.py` file (verify with `grep -r "rides.date\|rides\.date\|WHERE date" server/` -- no false positives from `meal_logs.date` or `planned_meals.date` which are legitimate).
2. Zero instances of `toISOString().slice(0, 10)` remain in any `.tsx` file (verify with `grep -r "toISOString().slice" frontend/src/`).
3. `frontend/src/lib/format.ts` exports 7 new date/time formatting functions.
4. `ride_records.timestamp_utc` has type `timestamp with time zone` after migration.
5. All 310+ unit tests pass.
6. TypeScript compilation succeeds with zero errors.
7. Frontend production build succeeds.
