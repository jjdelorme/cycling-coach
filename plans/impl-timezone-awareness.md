# Feature Implementation Plan: fix-timezone-awareness

## Analysis & Context

- **Objective:** Complete the timezone-awareness fix across the full stack. Phase 0 (ContextVar transport, middleware, frontend date fixes, coaching tool `user_today()` adoption) is done. Phases 1-4 normalize `start_time` to UTC, rewrite all `rides.date` queries to derive local dates at query time, drop the `rides.date` column, migrate column types, and rebuild PMC.
- **Architectural decisions (non-negotiable):**
  1. Store everything in UTC
  2. Derive local dates at query time using `X-Client-Timezone` header
  3. Drop `rides.date` column entirely
  4. Remove `athlete_settings.timezone` persistence
  5. No timezone stored on the athlete -- header is the only source
- **Key Dependencies:** `zoneinfo` (stdlib), `contextvars` (stdlib), `psycopg2`, `timezonefinder` (GPS→timezone for historical data fix)
- **Peer Review Decisions (2026-04-10):**
  - B1: ClientTimezoneMiddleware must be rewritten as raw ASGI (BaseHTTPMiddleware breaks ContextVar propagation)
  - B3/D2: Historical non-UTC start_time values fixed via GPS coordinates (start_lat/start_lon → timezonefinder), fallback to America/New_York for indoor rides without GPS
  - D1: intervals.icu `start_date` field verified empirically during implementation; fallback to `start_date_local` + `icu_timezone` if needed
  - D3: `user_today()` keeps returning `str`
  - Phase 3E (multi-athlete user_id) deferred to separate work item
  - Missing steps added: planning.py (Step 2.B2), sync router (Step 2.H2), get_week_summary call site (Step 2.E)

---

## Audit -- What Is Already Done (Phase 0)

| Item | File | Status |
|------|------|--------|
| `server/utils/dates.py` uses `ContextVar` | `server/utils/dates.py` | DONE |
| `ClientTimezoneMiddleware` in `server/main.py` | `server/main.py` | BUG — uses BaseHTTPMiddleware, ContextVar doesn't propagate (B1) |
| `server/dependencies.py` with `get_client_tz()` | `server/dependencies.py` | DONE |
| `authHeaders()` sends `X-Client-Timezone` | `frontend/src/lib/api.ts` | DONE |
| `server/coaching/agent.py` uses `user_today()` | `server/coaching/agent.py` | DONE |
| `server/coaching/tools.py` uses `user_today()` | `server/coaching/tools.py` | DONE |
| `server/nutrition/agent.py` uses `user_today()` | `server/nutrition/agent.py` | DONE |
| `server/nutrition/tools.py` uses `user_today()` | `server/nutrition/tools.py` | DONE |
| `server/nutrition/planning_tools.py` uses `user_today()` | `server/nutrition/planning_tools.py` | DONE |
| Frontend `toISOString()` fixes in Dashboard/Analysis | `frontend/src/pages/Dashboard.tsx`, `Analysis.tsx` | DONE |
| 88/88 unit tests pass | `tests/unit/` | DONE |

---

## Micro-Step Checklist

- [x] Phase 0 Fixes (complete)
  - [x] Step 0.A: Write unit tests for `server/utils/dates.py`
  - [x] Step 0.B: Run unit tests -- 88/88 passed
  - [x] Step 0.C: Fix `toISOString()` in `frontend/src/pages/Dashboard.tsx`
  - [x] Step 0.D: Fix `toISOString()` in `frontend/src/pages/Analysis.tsx`
  - [x] Step 0.E: Fix `server/utils/dates.py` -- ContextVar
  - [x] Step 0.F: Update ClientTimezoneMiddleware
- [ ] Phase 0 Bug Fix
  - [ ] Step 0.G: Rewrite ClientTimezoneMiddleware as raw ASGI middleware (B1 fix)
- [ ] Phase 1: Normalize start_time to UTC and stop writing rides.date
  - [ ] Step 1.A: Fix intervals.icu to store UTC `start_date` instead of `start_date_local`
  - [ ] Step 1.B: Fix `server/ingest.py` -- stop computing `ride_date`, stop writing `rides.date`
  - [x] Step 1.C: Fix remaining `datetime.now()` calls (intervals_icu.py, planning.py) (Status: database.py set_athlete_setting uses user_today(); withings.py sync_weight uses datetime.now(timezone.utc); weight.py get_current_weight uses user_today(); intervals_icu.py fetch_activities and update_weight already fixed; planning.py already fixed)
  - [x] Step 1.D: Remove `athlete_settings.timezone` writes and reads (Status: Already done by prior engineer; coaching.py no longer writes timezone to athlete_settings)
  - [x] Step 1.E: Fix background sync timezone source (`_get_athlete_tz()` in sync.py) (Status: Already done; _get_athlete_tz() returns ZoneInfo("UTC") with explanatory comment)
  - [ ] Step 1.F: Write unit tests for intervals.icu mapping and ingest changes
  - [ ] Step 1.G: Run unit tests -- verify no regressions
- [ ] Phase 2: Rewrite all rides.date queries to use start_time
  - [x] Step 2.A: Rewrite `server/queries.py` -- all rides.date references (Status: Already done; get_current_ftp uses ORDER BY start_time; get_week_planned_and_actual uses AT TIME ZONE pattern with tz_name param)
  - [x] Step 2.B: Rewrite `server/routers/rides.py` -- all rides.date references (Status: All 5 endpoints already converted; verified via tests)
  - [x] Step 2.C: Rewrite `server/routers/analysis.py` -- all rides.date references (Status: Fixed route_matches hardcoded UTC -> client tz; zone_distribution/efficiency_factor already done; power_curve_history deferred to Phase 3 per plan)
  - [x] Step 2.D: Rewrite `server/coaching/tools.py` -- all rides.date references (Status: _resolve_ride_id, get_recent_rides, get_training_summary, get_planned_workout_for_ride already converted; get_athlete_nutrition_status fixed: naive datetime.now() -> user_today(), rides WHERE date -> AT TIME ZONE pattern)
  - [x] Step 2.E: Rewrite `server/coaching/planning_tools.py` -- rides.date in `set_ride_coach_comments` AND `get_week_summary` call site (Status: Already done; set_ride_coach_comments uses AT TIME ZONE pattern; get_week_summary passes tz_name=get_request_tz().key)
  - [x] Step 2.F: Rewrite `server/coaching/agent.py` -- recent rides query (Status: Already done; _build_system_instruction uses AT TIME ZONE pattern with tz_name from get_request_tz().key)
  - [x] Step 2.G: Rewrite `server/ingest.py` -- compute_daily_pmc, backfill_hr_tss, get_benchmark_for_date, sync_athlete_settings_from_latest_ride, power_bests INSERT (Status: compute_daily_pmc already has tz_name param and AT TIME ZONE queries; run_ingestion passes tz_name="UTC"; sync_athlete_settings uses start_time ordering; get_benchmark_for_date uses start_time ordering with TODO Phase 3 comment; backfill_hr_tss uses start_time with TODO Phase 3 comment; power_bests INSERT uses start_time[:10]; withings webhook passes tz_name="UTC")
  - [x] Step 2.H: Rewrite `server/services/sync.py` -- dedup fingerprints, ride_date references, power_bests INSERT (Status: compute_daily_pmc call passes tz_name="UTC"; fingerprint dedup uses start_time[:10] with TODO Phase 3 comment; power_bests INSERT has TODO Phase 3 comment)
  - [x] Step 2.I: Rewrite `server/services/single_sync.py` -- date references, power_bests INSERT (Status: target_date uses start_time[:10] with TODO Phase 3 comment; power_bests INSERT has TODO Phase 3 comment)
  - [x] Step 2.B2: Rewrite `server/routers/planning.py` -- get_activity_dates, weekly_overview, plan_compliance rides.date refs (Status: Fixed get_week_plans_batch missing tz passthrough; get_activity_dates/weekly_overview/plan_compliance/get_week_plan already done)
  - [x] Step 2.H2: Rewrite `server/routers/sync.py` -- backfill_streams rides.date reference (Status: No rides.date references found; queries use r.start_time already)
  - [x] Step 2.J: Write integration tests for key query rewrites (Status: Created tests/integration/test_timezone_queries.py with 6 tests: local date derivation, UTC date, timezone-aware filtering, exclusion filtering, PMC grouping by local date, TSS aggregation by timezone)
  - [ ] Step 2.K: Run all tests
- [ ] Phase 3: Schema migration -- drop rides.date, promote column types
  - [ ] Step 3.A: Write and apply migration SQL
  - [ ] Step 3.B: Update `_SCHEMA` in `server/database.py`
  - [ ] Step 3.C: Fix SUBSTR-based queries (get_ftp_history_rows, monthly_summary, power_curve_history)
  - [ ] Step 3.D: Fix Python code that expects string returns from DATE/TIMESTAMPTZ columns
  - [ ] Step 3.E: GPS-based historical data fix (timezonefinder for start_lat/start_lon, fallback America/New_York)
  - [ ] Step 3.F: Run integration tests against migrated schema
- [ ] Phase 4: Rebuild PMC and smoke test
  - [ ] Step 4.A: Full ingest + rebuild PMC
  - [ ] Step 4.B: End-to-end smoke test with timezone header

---

## Step-by-Step Implementation Details

### Phase 1: Normalize start_time to UTC and Stop Writing rides.date

Phase 1 is **prerequisite** for Phase 2. The `AT TIME ZONE` query pattern only works if `start_time` is uniformly UTC. Currently, intervals.icu rides store a LOCAL timestamp in `start_time`. This must be fixed first.

---

#### Step 1.A -- Fix intervals.icu to store UTC `start_date` instead of `start_date_local`

**File:** `server/services/intervals_icu.py`
**Function:** `map_activity_to_ride()` (lines 299-373)

**Problem:** Line 304 reads `start_date_local` -- a LOCAL timestamp from intervals.icu. Line 324 assigns it to `start_time`. This means `start_time` contains local time, not UTC. When Phase 2 applies `AT TIME ZONE`, the offset would be applied twice.

The intervals.icu API returns both `start_date_local` (local) and `start_date` (UTC ISO string). We must use `start_date` for storage.

**Current code (lines 304-309, 322-324):**
```python
start_date = activity.get("start_date_local", "")
if not start_date:
    return None

# intervals.icu uses ISO format; extract date portion
date = start_date[:10] if len(start_date) >= 10 else start_date
...
ride = {
    "date": date,
    "start_time": start_date,
    ...
}
```

**New code:**
```python
# Use UTC start_date for storage; fall back to start_date_local only for existence check
start_date_utc = activity.get("start_date")
start_date_local = activity.get("start_date_local", "")
if not start_date_utc and not start_date_local:
    return None

# Store the UTC timestamp for start_time (used for AT TIME ZONE queries)
# Keep local date in "date" field temporarily for backward compat (dropped in Phase 3)
start_time_value = start_date_utc or start_date_local
date = start_date_local[:10] if len(start_date_local) >= 10 else (start_date_utc[:10] if start_date_utc else "")
...
ride = {
    "date": date,
    "start_time": start_time_value,
    ...
}
```

**Why keep `date` temporarily:** The `rides.date` column still exists in this phase and downstream code (sync.py dedup fingerprints, etc.) still reads it. We keep writing it using the LOCAL date from intervals.icu (which is correct for the `date` column's semantics). We change `start_time` to UTC. The `date` column is dropped in Phase 3.

> **DECISION NEEDED:** The intervals.icu API field `start_date` is documented as UTC. However, we should verify this empirically with one or two activities. If `start_date` is actually local (some APIs mislabel this), we would need to parse `start_date_local` and reverse-apply the timezone offset using the activity's `icu_timezone` field. The engineer should verify by comparing `start_date` and `start_date_local` for a known ride -- if the difference matches the athlete's timezone offset, `start_date` is truly UTC. If they are identical, `start_date` is local and we need a different approach.

**Test (Step 1.F):** Unit test in `tests/unit/test_intervals_icu.py` -- mock activity dicts with both `start_date` and `start_date_local`, assert `map_activity_to_ride()` sets `start_time` to the UTC value from `start_date`.

---

#### Step 1.B -- Fix server/ingest.py -- stop computing ride_date, stop writing rides.date

**File:** `server/ingest.py`

**Sub-step 1.B.1: Remove `_utc_to_local_date` function (lines 36-48)**

Delete the entire function:
```python
def _utc_to_local_date(start_time: str, tz_name: str) -> str:
    ...
```

**Sub-step 1.B.2: Remove timezone lookup and ride_date computation in `parse_ride_json` (lines 99-106)**

**Current code (lines 99-106):**
```python
_tz_name = "UTC"
if conn:
    _tz_row = conn.execute(
        "SELECT value FROM athlete_settings WHERE key = 'timezone' AND is_active = TRUE"
    ).fetchone()
    if _tz_row:
        _tz_name = _tz_row["value"] or "UTC"
ride_date = _utc_to_local_date(start_time, _tz_name)
```

**New code:**
```python
# Derive ride_date from start_time for backward compat (rides.date still exists).
# FIT timestamps are UTC; slice YYYY-MM-DD. This is "wrong" for the user's local date
# but rides.date is dropped in Phase 3. We keep writing it to avoid schema errors.
ride_date = start_time[:10] if start_time else ""
```

**Why still write rides.date:** The column is NOT NULL in the schema. Removing the write before dropping the column would break INSERTs. Phase 3 drops the column and the NOT NULL constraint together.

**Sub-step 1.B.3: Fix get_benchmark_for_date ride lookup (line 74-78)**

**Current code (lines 74-78):**
```python
row = conn.execute(
    f"SELECT {col} FROM rides WHERE {col} > 0 AND date <= %s ORDER BY date DESC LIMIT 1",
    (date_str,)
).fetchone()
```

This is fine for now -- `date` still exists. We rewrite this in Phase 2, Step 2.G.

**Sub-step 1.B.4: Remove athlete_settings timezone import**

In `parse_ride_json`, remove the now-unused athlete_settings timezone query. Also remove the `from zoneinfo import ZoneInfo` and `from datetime import timezone` imports from `_utc_to_local_date` (which is deleted).

**Test (Step 1.F):** Unit test verifying `parse_ride_json` no longer calls the athlete_settings timezone query. Mock a JSON file, assert the returned ride dict has `date` derived from `start_time[:10]`.

---

#### Step 1.C -- Fix remaining datetime.now() calls

**File: `server/services/intervals_icu.py`**

**Line 171 (`fetch_activities`):**
```python
# Current:
oldest = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
# New:
from datetime import timezone
oldest = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
```

**Line 173 (`fetch_activities`):**
```python
# Current:
newest = datetime.now().strftime("%Y-%m-%d")
# New:
newest = datetime.now(timezone.utc).strftime("%Y-%m-%d")
```

Note: These are API fetch bounds, not user-facing dates, so UTC is correct. One day of drift in the API fetch window is acceptable -- the dedup logic handles overlaps.

**Line 414 (`update_weight`):**
```python
# Current:
date = datetime.now().strftime("%Y-%m-%d")
# New:
from server.utils.dates import user_today
date = user_today()
```

This is user-facing (weight date on intervals.icu), so it should use the user's local date. However, `update_weight` is called from two contexts: (1) the coaching tool `update_athlete_setting` (request context available) and (2) potentially from background jobs. In the request context, `user_today()` returns the correct local date. In background context, it falls back to UTC, which is acceptable.

**File: `server/routers/planning.py`**

**Line 348:**
```python
# Current:
datetime.now().isoformat(timespec="seconds")
# New:
from datetime import timezone
datetime.now(timezone.utc).isoformat(timespec="seconds")
```

This is an audit timestamp (`synced_at`), so UTC is correct.

**Test:** These are simple one-line fixes. Verify with `grep -rn "datetime.now()" server/` that no un-timezone-aware `datetime.now()` calls remain in business logic after this step.

---

#### Step 1.D -- Remove athlete_settings.timezone writes and reads

**File: `server/routers/coaching.py` (lines 24-27)**

**Current code:**
```python
from server.database import get_athlete_setting, set_athlete_setting
tz_str = getattr(request.state, "client_tz_str", "UTC")
if tz_str != "UTC" and get_athlete_setting("timezone") != tz_str:
    set_athlete_setting("timezone", tz_str)
```

**New code:** Delete these 4 lines entirely. The timezone is transported via the header on every request. There is no reason to persist it.

**File: `server/ingest.py` (already handled in Step 1.B.2)**
The athlete_settings timezone read was removed in Step 1.B.2.

**Test:** Unit test that verifies the coaching chat endpoint does NOT call `set_athlete_setting("timezone", ...)`. Alternatively, grep confirmation: `grep -rn "athlete_setting.*timezone" server/` should return zero results after this step.

---

#### Step 1.E -- Fix background sync timezone source

**File: `server/services/sync.py` (lines 47-55)**

**Current code:**
```python
def _get_athlete_tz():
    """Read the stored athlete timezone from athlete_settings; fall back to UTC."""
    from zoneinfo import ZoneInfo
    from server.database import get_athlete_setting
    tz_name = get_athlete_setting("timezone") or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")
```

**Problem:** After Step 1.D removes `athlete_settings.timezone`, this function always returns UTC. Background sync uses it for:
- `_download_rides`: date window for fetch_activities (`oldest`/`newest`) -- lines 382-384
- `_download_planned_workouts`: today/end_date for workout window -- lines 651-654
- `_upload_workouts`: today for start_date -- lines 723-729

**Analysis:** All three uses compute date boundaries for API fetch windows. Using UTC instead of the athlete's local timezone means:
- The fetch window could be off by one day at timezone boundaries
- But the dedup logic (filename + fingerprint) prevents duplicate imports
- And the watermark (`rides_newest`) prevents re-downloading old data
- The error is at most 1 day in a 365-day or 28-day window

**Resolution:** Replace `_get_athlete_tz()` with a hardcoded UTC fallback. Add a comment explaining why this is acceptable.

**New code:**
```python
def _get_athlete_tz():
    """Return UTC for background sync date windows.

    Background sync runs without an HTTP request context, so there is no
    X-Client-Timezone header. Using UTC means the fetch window could be off
    by up to one calendar day at timezone boundaries. This is acceptable
    because:
      - Ride dedup (filename + date+distance fingerprint) prevents duplicates
      - The watermark prevents re-downloading already-synced rides
      - Planned workout dedup uses (date, name) pairs
    """
    from zoneinfo import ZoneInfo
    return ZoneInfo("UTC")
```

**Test:** Verify sync still works by running integration test or manual smoke test with UTC. No separate unit test needed -- the function is now trivial.

---

#### Step 1.F -- Write unit tests for Phase 1 changes

**File: `tests/unit/test_intervals_icu.py` (create or extend)**

```python
def test_map_activity_to_ride_uses_utc_start_date():
    """map_activity_to_ride must set start_time to the UTC start_date, not start_date_local."""
    from server.services.intervals_icu import map_activity_to_ride
    activity = {
        "id": "i12345",
        "start_date": "2026-04-09T03:30:00Z",       # UTC
        "start_date_local": "2026-04-08T21:30:00",   # CDT (UTC-6)
        "type": "Ride",
        "moving_time": 3600,
        "distance": 40000,
    }
    ride = map_activity_to_ride(activity)
    assert ride is not None
    # start_time must be the UTC value
    assert ride["start_time"] == "2026-04-09T03:30:00Z"
    # date (temporary, backward compat) should be the LOCAL date
    assert ride["date"] == "2026-04-08"


def test_map_activity_to_ride_fallback_no_utc():
    """When start_date is missing, fall back to start_date_local."""
    from server.services.intervals_icu import map_activity_to_ride
    activity = {
        "id": "i12346",
        "start_date_local": "2026-04-08T21:30:00",
        "type": "Ride",
        "moving_time": 3600,
        "distance": 40000,
    }
    ride = map_activity_to_ride(activity)
    assert ride is not None
    assert ride["start_time"] == "2026-04-08T21:30:00"
```

**File: `tests/unit/test_ingest.py` (extend or create)**

```python
def test_parse_ride_json_no_timezone_query(tmp_path, mocker):
    """parse_ride_json must NOT query athlete_settings for timezone."""
    # Create a minimal ride JSON
    import json
    ride_json = {
        "session": [{"start_time": "2026-04-09T03:30:00Z", "total_timer_time": 3600}],
        "sport": [{}],
        "user_profile": [{}],
        "zones_target": [{}],
        "record": [],
    }
    filepath = tmp_path / "test_ride.json"
    filepath.write_text(json.dumps(ride_json))

    # Mock conn to track queries
    mock_conn = mocker.MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = None

    from server.ingest import parse_ride_json
    ride, _, _, _ = parse_ride_json(str(filepath), conn=mock_conn)

    # Verify no timezone query was made
    for call in mock_conn.execute.call_args_list:
        sql = call[0][0]
        assert "timezone" not in sql.lower(), f"Unexpected timezone query: {sql}"
```

---

#### Step 1.G -- Run unit tests

```bash
source venv/bin/activate && pytest tests/unit/ -v
```

**Success criterion:** All tests pass, including new ones from Step 1.F.

---

### Phase 2: Rewrite All rides.date Queries to Use start_time

After Phase 1, `start_time` is uniformly UTC across both FIT and intervals.icu rides. But `start_time` is still TEXT. Phase 2 rewrites queries to derive local dates from `start_time` while it is still TEXT (casting to TIMESTAMPTZ inline). Phase 3 changes the column type.

**The query pattern:** Every query that previously filtered or grouped by `rides.date` now uses:
```sql
(rides.start_time::TIMESTAMPTZ AT TIME ZONE %(tz)s)::DATE
```
where `%(tz)s` is the IANA timezone string from `get_request_tz().key` or a function parameter.

**Important:** `start_time` is TEXT right now. The `::TIMESTAMPTZ` cast works on ISO8601 strings like `2026-04-09T03:30:00Z` and `2026-04-09T03:30:00+00:00`. The cast will fail on strings without timezone info (e.g., `2026-04-09T03:30:00`). Pre-Phase-1 intervals.icu rides that stored `start_date_local` (no Z suffix) would fail. This is handled by Step 1.A ensuring new synced rides use UTC, and by the data migration in Phase 3 which fixes historical data.

> **DECISION NEEDED:** What about historical intervals.icu rides already in the database with local `start_time` values (no timezone suffix)? Options: (A) Write a one-time data fix script to parse these and append `+00:00` as a best-effort approximation. (B) Add a COALESCE/fallback in the query pattern that falls back to `rides.date` when `start_time::TIMESTAMPTZ` fails. (C) Just treat them as UTC (the offset error is at most ~12 hours, affecting only the date derivation). The engineer should check how many rides have non-UTC start_time values: `SELECT COUNT(*) FROM rides WHERE start_time NOT LIKE '%Z' AND start_time NOT LIKE '%+%' AND start_time NOT LIKE '%-%'` (excluding date-only formats).

---

#### Step 2.A -- Rewrite `server/queries.py`

**File:** `server/queries.py`

**Change 1: `get_current_ftp()` (line 43)**

Current:
```python
row = conn.execute(
    "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY date DESC LIMIT 1"
).fetchone()
```

New:
```python
row = conn.execute(
    "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY start_time DESC LIMIT 1"
).fetchone()
```

No timezone conversion needed -- we just need the most recent ride by time, not by local date.

**Change 2: `get_week_planned_and_actual()` (lines 137-143)**

Current:
```python
actual = conn.execute(
    """SELECT id, date, sport, sub_sport, duration_s, tss, avg_power,
              normalized_power, avg_hr, distance_m, total_ascent
       FROM rides WHERE date >= %s AND date <= %s ORDER BY date""",
    (start_str, end_str),
).fetchall()
```

New -- accept a `tz` parameter:
```python
def get_week_planned_and_actual(conn, start_str: str, end_str: str, tz_name: str = "UTC") -> tuple[list[dict], list[dict]]:
    """Get planned workouts and actual rides for a Mon-Sun date range.

    Args:
        start_str: Week start YYYY-MM-DD
        end_str: Week end YYYY-MM-DD
        tz_name: IANA timezone for deriving ride local date from start_time
    """
    planned = conn.execute(
        "SELECT * FROM planned_workouts WHERE date >= %s AND date <= %s ORDER BY date",
        (start_str, end_str),
    ).fetchall()

    actual = conn.execute(
        """SELECT id, (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
                  sport, sub_sport, duration_s, tss, avg_power,
                  normalized_power, avg_hr, distance_m, total_ascent
           FROM rides
           WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE BETWEEN %s AND %s
           ORDER BY start_time""",
        (tz_name, tz_name, start_str, end_str),
    ).fetchall()

    return [dict(p) for p in planned], [dict(a) for a in actual]
```

**Callers to update:**
- `server/coaching/planning_tools.py` line 404: `get_week_planned_and_actual(conn, start_str, end_str)` -> `get_week_planned_and_actual(conn, start_str, end_str, tz_name=get_request_tz().key)`

---

#### Step 2.B -- Rewrite `server/routers/rides.py`

**File:** `server/routers/rides.py`

Every endpoint that filters by `rides.date` needs rewriting. There are 6 queries.

**Change 1: `list_rides()` (lines 33-45)**

Current:
```python
query = "SELECT * FROM rides WHERE 1=1"
...
if start_date:
    query += " AND date >= %s"
if end_date:
    query += " AND date <= %s"
query += " ORDER BY date DESC LIMIT %s"
```

New -- add `tz: ZoneInfo = Depends(get_client_tz)` parameter:
```python
@router.get("", response_model=list[RideSummary])
def list_rides(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    sport: Optional[str] = Query(None),
    limit: int = Query(500),
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    tz_name = str(tz)
    query = "SELECT *, (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date FROM rides WHERE 1=1"
    params: list = [tz_name]
    if start_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE"
        params.extend([tz_name, start_date])
    if end_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE <= %s::DATE"
        params.extend([tz_name, end_date])
    if sport:
        query += " AND (sport = %s OR sub_sport = %s)"
        params.extend([sport, sport])
    query += " ORDER BY start_time DESC LIMIT %s"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [RideSummary(**dict(r)) for r in rows]
```

**Change 2: `daily_summary()` (lines 88-102)**

Current query (line 98-100):
```python
rows = conn.execute(
    "SELECT date, duration_s, tss, total_calories, distance_m, total_ascent, avg_power FROM rides WHERE date >= %s ORDER BY date",
    (since,),
).fetchall()
```

New:
```python
tz_name = str(tz)
rows = conn.execute(
    """SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
              duration_s, tss, total_calories, distance_m, total_ascent, avg_power
       FROM rides
       WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE
       ORDER BY start_time""",
    (tz_name, tz_name, since),
).fetchall()
```

**Change 3: `weekly_summary()` (lines 105-161)**

Current query filters by `rides.date`. Rewrite similarly, adding `tz: ZoneInfo = Depends(get_client_tz)`:
```python
@router.get("/summary/weekly", response_model=list[WeeklySummary])
def weekly_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    tz_name = str(tz)
    query = """
        SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
               duration_s, tss, distance_m, total_ascent, avg_power, avg_hr, best_20min_power
        FROM rides WHERE 1=1
    """
    params: list = [tz_name]
    if start_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE"
        params.extend([tz_name, start_date])
    if end_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE <= %s::DATE"
        params.extend([tz_name, end_date])
    query += " ORDER BY start_time"
    ...
```

The Python aggregation code (lines 128-161) stays the same -- it reads `d["date"]` which now comes from the derived column.

**Change 4: `monthly_summary()` (lines 164-195)**

Current: `SUBSTR(date, 1, 7) as month` and `WHERE date >= %s`. Replace:
```python
@router.get("/summary/monthly", response_model=list[MonthlySummary])
def monthly_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    tz_name = str(tz)
    query = """
        SELECT
            TO_CHAR((start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE, 'YYYY-MM') as month,
            COUNT(*) as rides,
            ROUND(CAST(SUM(duration_s) / 3600.0 AS NUMERIC), 1) as duration_h,
            ROUND(CAST(SUM(COALESCE(tss, 0)) AS NUMERIC), 1) as tss,
            ROUND(CAST(SUM(COALESCE(distance_m, 0)) / 1000.0 AS NUMERIC), 1) as distance_km,
            CAST(SUM(COALESCE(total_ascent, 0)) AS INTEGER) as ascent_m,
            ROUND(CAST(AVG(CASE WHEN avg_power > 0 THEN avg_power END) AS NUMERIC), 0) as avg_power,
            ROUND(CAST(AVG(CASE WHEN avg_hr > 0 THEN avg_hr END) AS NUMERIC), 0) as avg_hr,
            MAX(best_20min_power) as best_20min
        FROM rides
        WHERE 1=1
    """
    params: list = [tz_name]
    if start_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE"
        params.extend([tz_name, start_date])
    if end_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE <= %s::DATE"
        params.extend([tz_name, end_date])
    query += " GROUP BY month ORDER BY month"
    ...
```

**Change 5: `delete_ride()` (lines 248-269)**

Current reads `ride["date"]` for PMC recalculation:
```python
ride = conn.execute("SELECT date FROM rides WHERE id = %s", (ride_id,)).fetchone()
ride_date = ride["date"]
...
compute_daily_pmc(conn, since_date=ride_date)
```

New -- derive local date from start_time. But `delete_ride` runs in a request context, so we can use the ContextVar:
```python
@router.delete("/{ride_id}")
def delete_ride(ride_id: int, user: CurrentUser = Depends(require_write), tz: ZoneInfo = Depends(get_client_tz)):
    tz_name = str(tz)
    with get_db() as conn:
        ride = conn.execute(
            "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS local_date FROM rides WHERE id = %s",
            (tz_name, ride_id),
        ).fetchone()
        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")

        ride_date = ride["local_date"]
        conn.execute("DELETE FROM ride_records WHERE ride_id = %s", (ride_id,))
        conn.execute("DELETE FROM ride_laps WHERE ride_id = %s", (ride_id,))
        conn.execute("DELETE FROM power_bests WHERE ride_id = %s", (ride_id,))
        conn.execute("DELETE FROM rides WHERE id = %s", (ride_id,))
        compute_daily_pmc(conn, since_date=ride_date)
    return {"status": "ok"}
```

---

#### Step 2.C -- Rewrite `server/routers/analysis.py`

**File:** `server/routers/analysis.py`

**Change 1: `zone_distribution()` (lines 73-80)**

Current: `AND r.date >= ?` / `AND r.date <= ?`

New -- add tz dependency:
```python
@router.get("/zones")
def zone_distribution(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    tz_name = str(tz)
    query = """
        SELECT r.ftp, rr.power
        FROM ride_records rr
        JOIN rides r ON rr.ride_id = r.id
        WHERE rr.power IS NOT NULL AND rr.power > 0 AND r.ftp > 0
          AND rr.power <= 2000 AND rr.power <= (r.ftp * 5)
    """
    params: list = []
    if start_date:
        query += " AND (r.start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE"
        params.extend([tz_name, start_date])
    if end_date:
        query += " AND (r.start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE <= %s::DATE"
        params.extend([tz_name, end_date])
    ...
```

**Change 2: `efficiency_factor()` (lines 122-161)**

Current: `AND date >= ?` / `AND date <= ?` / `ORDER BY date` / `ORDER BY CAST(date AS DATE)`

New -- add tz dependency. The window function also needs updating:
```python
@router.get("/efficiency")
def efficiency_factor(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    tz_name = str(tz)
    query = """
        SELECT id, (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
               normalized_power, avg_hr, duration_s, sub_sport,
               (CAST(normalized_power AS FLOAT) / avg_hr) as ef,
               AVG(CAST(normalized_power AS FLOAT) / avg_hr) OVER (
                   ORDER BY start_time::TIMESTAMPTZ
                   RANGE BETWEEN INTERVAL '30 days' PRECEDING AND CURRENT ROW
               ) as rolling_ef
        FROM rides
        WHERE normalized_power > 0 AND avg_hr > 0
          AND sport IN ('ride', 'ebikeride', ...)
          AND duration_s >= 1800
          AND intensity_factor BETWEEN 0.5 AND 0.8
    """
    params: list = [tz_name]
    if start_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE"
        params.extend([tz_name, start_date])
    if end_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE <= %s::DATE"
        params.extend([tz_name, end_date])
    query += " ORDER BY start_time"
    ...
```

**Change 3: `power_curve_history()` (lines 32-49)**

Current: `SUBSTR(date, 1, 7) as month` on `power_bests`

`power_bests.date` is a TEXT field that mirrors `rides.date`. After Phase 2 it will be derived from `rides.start_time` via a join. But for now, `power_bests.date` still exists and is still written. Leave this query as-is in Phase 2. It will be fixed in Phase 3 when we change column types.

**Change 4: `route_matches()` (lines 175-209)**

Current: `ORDER BY date`. Replace with `ORDER BY start_time`. The result dict includes `date` -- derive it:
```python
rows = conn.execute("""
    SELECT id, (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
           sub_sport, duration_s, distance_m, total_ascent,
           avg_power, normalized_power, avg_hr, tss, start_lat, start_lon
    FROM rides
    WHERE start_lat IS NOT NULL
      AND id != %s
      AND ABS(start_lat - %s) < 0.01
      AND ABS(start_lon - %s) < 0.01
    ORDER BY start_time
""", (tz_name, ride_id, target["start_lat"], target["start_lon"])).fetchall()
```

Add `tz: ZoneInfo = Depends(get_client_tz)` to the endpoint signature.

---

#### Step 2.D -- Rewrite `server/coaching/tools.py`

**File:** `server/coaching/tools.py`

Coaching tools run in request context, so `get_request_tz()` is available.

**Change 1: `_resolve_ride_id()` (lines 27-34)**

Current:
```python
row = conn.execute(
    "SELECT id, date, duration_s FROM rides WHERE date = ? ORDER BY duration_s DESC LIMIT 1",
    (date,),
).fetchone()
```

New:
```python
def _resolve_ride_id(conn, date: str):
    """Resolve a YYYY-MM-DD date to a ride_id (longest ride on that date)."""
    tz_name = get_request_tz().key
    row = conn.execute(
        """SELECT id, (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date, duration_s
           FROM rides
           WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE
           ORDER BY duration_s DESC LIMIT 1""",
        (tz_name, tz_name, date),
    ).fetchone()
    if not row:
        return None, f"No ride found for date {date}"
    return row["id"], row["date"]
```

**Change 2: `get_recent_rides()` (lines 150-159)**

Current:
```python
cutoff = (datetime.now(get_request_tz()) - timedelta(days=days_back)).strftime("%Y-%m-%d")
...
rows = conn.execute(
    """SELECT id, date, sub_sport, ... FROM rides WHERE date >= ? ORDER BY date DESC""",
    (cutoff,),
).fetchall()
```

New:
```python
cutoff = (datetime.now(get_request_tz()) - timedelta(days=days_back)).strftime("%Y-%m-%d")
tz_name = get_request_tz().key
...
rows = conn.execute(
    """SELECT id, (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
              sub_sport, duration_s, distance_m, tss, avg_power,
              normalized_power, avg_hr, total_ascent, best_20min_power,
              post_ride_comments, coach_comments
       FROM rides
       WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE
       ORDER BY start_time DESC""",
    (tz_name, tz_name, cutoff),
).fetchall()
```

**Change 3: `get_upcoming_workouts()` (lines 181-210)**

This queries `planned_workouts`, NOT `rides`. `planned_workouts.date` is a calendar intention -- no change needed. Already correct.

**Change 4: `get_training_summary()` (lines 230-266)**

Current:
```python
cutoff = (datetime.now(get_request_tz()) - timedelta(days=days)).strftime("%Y-%m-%d")
...
row = conn.execute(
    """SELECT COUNT(*) as rides, ... FROM rides WHERE date >= ?""",
    (cutoff,),
).fetchone()
```

New:
```python
cutoff = (datetime.now(get_request_tz()) - timedelta(days=days)).strftime("%Y-%m-%d")
tz_name = get_request_tz().key
...
row = conn.execute(
    """SELECT COUNT(*) as rides,
              ROUND(CAST(SUM(duration_s) / 3600.0 AS NUMERIC), 1) as hours,
              ROUND(CAST(SUM(COALESCE(tss, 0)) AS NUMERIC), 0) as tss,
              ROUND(CAST(SUM(COALESCE(distance_m, 0)) / 1000.0 AS NUMERIC), 0) as distance_km,
              ROUND(CAST(SUM(COALESCE(total_ascent, 0)) AS NUMERIC), 0) as ascent_m
       FROM rides
       WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE""",
    (tz_name, cutoff),
).fetchone()
```

**Change 5: `get_power_curve()` (lines 581-629)**

The query delegates to `get_power_bests_rows()` which queries `power_bests.date`, not `rides.date`. Leave as-is in Phase 2. Fixed in Phase 3 when `power_bests.date` column type changes.

**Change 6: `get_ride_analysis()` (lines 323-452)**

Uses `_resolve_ride_id(conn, date)` which is already fixed in Change 1. The ride analysis itself queries by `ride_id`, not by date. No additional changes needed.

**Change 7: `get_planned_workout_for_ride()` (lines 675-752)**

Current (lines 696-700):
```python
actual = conn.execute(
    """SELECT id, date, sub_sport, ... FROM rides WHERE date = ? ORDER BY duration_s DESC LIMIT 1""",
    (date,),
).fetchone()
```

New:
```python
tz_name = get_request_tz().key
actual = conn.execute(
    """SELECT id, (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
              sub_sport, duration_s, distance_m, tss,
              avg_power, normalized_power, avg_hr, total_ascent, ftp
       FROM rides
       WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE
       ORDER BY duration_s DESC LIMIT 1""",
    (tz_name, tz_name, date),
).fetchone()
```

---

#### Step 2.E -- Rewrite `server/coaching/planning_tools.py`

**File:** `server/coaching/planning_tools.py`

**Change: `set_ride_coach_comments()` (lines 714-741)**

Current (line 729):
```python
row = conn.execute(
    "SELECT id, sub_sport FROM rides WHERE date = ? ORDER BY duration_s DESC LIMIT 1",
    (date,),
).fetchone()
```

New:
```python
tz_name = get_request_tz().key
row = conn.execute(
    """SELECT id, sub_sport FROM rides
       WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE
       ORDER BY duration_s DESC LIMIT 1""",
    (tz_name, date),
).fetchone()
```

Add import: `from server.utils.dates import get_request_tz` (already imported at top of file).

---

#### Step 2.F -- Rewrite `server/coaching/agent.py`

**File:** `server/coaching/agent.py`

**Change: Recent rides query (lines 149-154)**

Current:
```python
recent_rides = conn.execute(
    """SELECT date, sub_sport, duration_s, tss, normalized_power
       FROM rides WHERE date >= ? ORDER BY date DESC LIMIT 7""",
    (seven_days_ago,),
).fetchall()
```

New:
```python
tz_name = get_request_tz().key
recent_rides = conn.execute(
    """SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
              sub_sport, duration_s, tss, normalized_power
       FROM rides
       WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE >= %s::DATE
       ORDER BY start_time DESC LIMIT 7""",
    (tz_name, tz_name, seven_days_ago),
).fetchall()
```

Add import at top: `from server.utils.dates import get_request_tz` (may already be imported).

---

#### Step 2.G -- Rewrite `server/ingest.py`

**File:** `server/ingest.py`

**Change 1: `compute_daily_pmc()` (lines 377-498)**

This is the most complex change. Currently:
```python
cursor = conn.execute(
    "SELECT date, SUM(tss) as total_tss FROM rides WHERE tss > 0 GROUP BY date ORDER BY date"
)
```

And later:
```python
ride_data_rows = conn.execute(
    "SELECT date, weight, ftp FROM rides ORDER BY date"
).fetchall()
```

PMC is an offline computation. It does NOT run in a request context (runs during ingest or sync). Therefore there is no ContextVar timezone. We need to accept a timezone parameter.

**New function signature:**
```python
def compute_daily_pmc(conn, since_date: str | None = None, tz_name: str = "UTC"):
```

**New queries:**
```python
cursor = conn.execute(
    """SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
              SUM(tss) as total_tss
       FROM rides WHERE tss > 0
       GROUP BY (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE
       ORDER BY date""",
    (tz_name, tz_name),
)
```

```python
ride_data_rows = conn.execute(
    """SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS date,
              weight, ftp
       FROM rides ORDER BY start_time""",
    (tz_name,),
).fetchall()
```

**Callers to update:**
- `server/ingest.py` `run_ingestion()` line 726: `compute_daily_pmc(conn)` -- background job, pass `tz_name="UTC"` (explicit)
- `server/services/sync.py` line 928: `compute_daily_pmc(conn, since_date=earliest)` -- background job, pass `tz_name="UTC"`
- `server/routers/rides.py` line 267: `compute_daily_pmc(conn, since_date=ride_date)` -- request context, pass `tz_name=str(tz)` from the `get_client_tz` dependency

> **DECISION NEEDED:** PMC computation currently uses `user_today()` for the end date (line 427). In a background job, `user_today()` returns UTC. Should we pass the timezone to `user_today(tz)` explicitly, or is UTC acceptable for the PMC end date? The PMC end date controls "compute metrics through today" -- using UTC means the PMC might not include today's rides for users in negative UTC offsets until midnight UTC. Recommendation: accept this limitation for background jobs; for request-triggered PMC recomputation (delete_ride), pass the user's timezone.

**Change 2: `get_benchmark_for_date()` (lines 74-78)**

Current:
```python
row = conn.execute(
    f"SELECT {col} FROM rides WHERE {col} > 0 AND date <= %s ORDER BY date DESC LIMIT 1",
    (date_str,)
).fetchone()
```

New -- this is called from `parse_ride_json` (background context) and `single_sync.py` (background context). No request timezone available. Use `start_time` ordering instead:
```python
row = conn.execute(
    f"SELECT {col} FROM rides WHERE {col} > 0 AND start_time <= %s ORDER BY start_time DESC LIMIT 1",
    (date_str,)
).fetchone()
```

Note: `date_str` here is a YYYY-MM-DD string being compared against `start_time` which is an ISO timestamp. PostgreSQL text comparison works: `'2026-04-09T03:30:00Z' <= '2026-04-09'` is FALSE (string comparison), which is wrong. After Phase 3 when `start_time` is TIMESTAMPTZ, we need `start_time <= %(date)s::TIMESTAMPTZ`. For now, keep using `rides.date` until Phase 3 drops it. Mark with a TODO comment.

**Actually -- defer this change to Phase 3.** The `rides.date` column still exists and this function is only called from background contexts. Rewriting it now introduces string comparison bugs. Instead, add a `# TODO Phase 3: rewrite to use start_time after column type migration` comment.

**Change 3: `backfill_hr_tss()` (lines 345-373)**

Current (line 350):
```python
rows = conn.execute(
    "SELECT id, date, avg_hr, duration_s FROM rides WHERE ..."
).fetchall()
```

Uses `r["date"]` for `get_latest_metric(conn, "lthr", r["date"])`. Since this is a background job and `get_latest_metric` compares against `athlete_settings.date_set`, the comparison works with any date string. Keep using `rides.date` for now. Defer to Phase 3.

**Change 4: `sync_athlete_settings_from_latest_ride()` (lines 520-541)**

Current (line 523):
```python
row = conn.execute(
    "SELECT date, ftp, weight FROM rides WHERE ftp > 0 AND weight > 0 ORDER BY date DESC LIMIT 1"
).fetchone()
```

New -- order by `start_time` (no date derivation needed, just ordering):
```python
row = conn.execute(
    "SELECT start_time, ftp, weight FROM rides WHERE ftp > 0 AND weight > 0 ORDER BY start_time DESC LIMIT 1"
).fetchone()
```

Update the log lines that reference `row["date"]` to use `row["start_time"][:10]`:
```python
logger.info("ftp_auto_synced", previous=current_ftp, new=new_ftp, source_date=row["start_time"][:10])
...
set_athlete_setting("ftp", new_ftp, date_set=row["start_time"][:10])
```

**Change 5: `ingest_rides()` power_bests INSERT (line 605)**

Current:
```python
conn.executemany(
    "INSERT INTO power_bests (ride_id, date, duration_s, ...) VALUES (?, ?, ?, ...)",
    [(ride_id, ride["date"], pb["duration_s"], ...) for pb in power_bests],
)
```

`ride["date"]` is still being written in Phase 2. This is fine -- `power_bests.date` mirrors `rides.date`. Both will be removed/changed in Phase 3.

---

#### Step 2.H -- Rewrite `server/services/sync.py`

**File:** `server/services/sync.py`

**Change 1: Dedup fingerprints in `_download_rides()` (lines 416-424)**

Current:
```python
rows = conn.execute("SELECT filename, date, distance_m FROM rides").fetchall()
for r in rows:
    row = dict(r)
    existing_filenames.add(row["filename"])
    dist = round((row["distance_m"] or 0) / 100) * 100
    existing_fingerprints.add((row["date"], dist))
```

The fingerprint uses `rides.date`. Since we still write `rides.date` in Phase 2, this remains functional. However, new rides from intervals.icu now have `date` derived from `start_date_local` (Step 1.A), while FIT-ingested rides have `date = start_time[:10]` (UTC). The fingerprint may not match for cross-source dedup of the same ride recorded at different UTC offsets. This is an existing bug that Phase 3 resolves by removing `rides.date` and fingerprinting on `start_time`.

**For Phase 2:** Leave fingerprint logic as-is. Add TODO comment.

**Change 2: power_bests INSERT in `_download_rides()` (line 587-600)**

Current uses `ride["date"]`. Still being written. Leave as-is in Phase 2.

---

#### Step 2.I -- Rewrite `server/services/single_sync.py`

**File:** `server/services/single_sync.py`

**Change 1: `target_date` (line 39)**

Current:
```python
target_date = ride_data["date"]
```

This is used for logging, benchmark lookups, and power_bests INSERT. Since `ride_data["date"]` is still populated (from `map_activity_to_ride`), leave as-is in Phase 2. Add TODO comment.

---

#### Step 2.J -- Write integration tests for key query rewrites

**File:** `tests/integration/test_timezone_queries.py` (create)

These tests require the test database (port 5433) and verify that the `AT TIME ZONE` pattern produces correct results.

```python
"""Integration tests for timezone-aware ride queries.

Requires test database (coach-test-db on port 5433).
Run via: ./scripts/run_integration_tests.sh
"""
from datetime import date


def test_ride_local_date_derivation(db_conn):
    """A ride at 2026-04-09T03:00:00Z should appear as 2026-04-08 in America/Chicago (UTC-5 in April)."""
    db_conn.execute(
        "INSERT INTO rides (date, start_time, filename, sport, duration_s) "
        "VALUES (%s, %s, %s, %s, %s)",
        ("2026-04-09", "2026-04-09T03:00:00Z", "tz_test_1", "cycling", 3600),
    )
    db_conn.commit()

    row = db_conn.execute(
        "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS local_date FROM rides WHERE filename = %s",
        ("America/Chicago", "tz_test_1"),
    ).fetchone()

    assert row["local_date"] == "2026-04-08"


def test_ride_local_date_utc(db_conn):
    """Same ride should appear as 2026-04-09 in UTC."""
    row = db_conn.execute(
        "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS local_date FROM rides WHERE filename = %s",
        ("UTC", "tz_test_1"),
    ).fetchone()

    # May need to insert first if test isolation resets between tests
    if row:
        assert row["local_date"] == "2026-04-09"


def test_ride_date_filter_timezone_aware(db_conn):
    """Filtering by local date 2026-04-08 in Chicago should include the ride."""
    rows = db_conn.execute(
        """SELECT filename FROM rides
           WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE""",
        ("America/Chicago", "2026-04-08"),
    ).fetchall()

    filenames = [r["filename"] for r in rows]
    assert "tz_test_1" in filenames


def test_pmc_groups_by_local_date(db_conn):
    """compute_daily_pmc should group rides by local date."""
    # Insert a ride with TSS
    db_conn.execute(
        "INSERT INTO rides (date, start_time, filename, sport, duration_s, tss, ftp, weight) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        ("2026-04-09", "2026-04-09T03:00:00Z", "pmc_tz_test", "cycling", 3600, 80, 250, 75),
    )
    db_conn.commit()

    from server.ingest import compute_daily_pmc
    compute_daily_pmc(db_conn, tz_name="America/Chicago")

    row = db_conn.execute(
        "SELECT date, total_tss FROM daily_metrics WHERE date = %s",
        ("2026-04-08",),
    ).fetchone()

    # The ride at 03:00 UTC = 10:00 PM CDT on April 8 should appear under April 8
    assert row is not None
    assert row["total_tss"] >= 80
```

---

#### Step 2.K -- Run all tests

```bash
source venv/bin/activate && pytest tests/unit/ -v
./scripts/run_integration_tests.sh -v
```

**Success criterion:** All unit tests and integration tests pass.

---

### Phase 3: Schema Migration -- Drop rides.date, Promote Column Types

Phase 3 happens AFTER all application code has been rewritten to not depend on `rides.date` for queries (Phase 2). The column is still being WRITTEN (for INSERT compatibility) but no longer READ.

---

#### Step 3.A -- Write and apply migration SQL

**File:** Create `scripts/migrate_timezone.sql` for documentation; apply via Python.

```sql
-- 1. Drop rides.date column (no longer read by any query)
ALTER TABLE rides DROP COLUMN IF EXISTS date;

-- 2. Promote start_time TEXT -> TIMESTAMPTZ
-- First, fix any non-UTC start_time values from legacy intervals.icu syncs.
-- Append '+00:00' to values that lack timezone info (treat as UTC as best effort).
UPDATE rides
SET start_time = start_time || '+00:00'
WHERE start_time IS NOT NULL
  AND start_time NOT LIKE '%Z'
  AND start_time NOT LIKE '%+%'
  AND LENGTH(start_time) > 10
  AND start_time NOT LIKE '%-__:__';

-- Now safe to cast
ALTER TABLE rides ALTER COLUMN start_time TYPE TIMESTAMPTZ USING start_time::TIMESTAMPTZ;

-- 3. Promote other TEXT date columns to proper types
ALTER TABLE daily_metrics ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE planned_workouts ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE periodization_phases ALTER COLUMN start_date TYPE DATE USING start_date::DATE;
ALTER TABLE periodization_phases ALTER COLUMN end_date TYPE DATE USING end_date::DATE;
ALTER TABLE power_bests ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE athlete_settings ALTER COLUMN date_set TYPE DATE USING date_set::DATE;

-- 4. Add index on start_time for timezone-aware date queries
CREATE INDEX IF NOT EXISTS idx_rides_start_time ON rides(start_time);

-- 5. Drop the now-orphaned index on rides(date)
DROP INDEX IF EXISTS idx_rides_date;
```

**Apply the migration:**
```bash
source venv/bin/activate
# VERIFY we're hitting localhost, NOT production
echo $DATABASE_URL

python -c "
import os, psycopg2
conn = psycopg2.connect(os.environ.get('DATABASE_URL', 'postgresql://postgres:dev@localhost:5432/coach'))
cur = conn.cursor()
# Read and execute the migration
with open('scripts/migrate_timezone.sql') as f:
    cur.execute(f.read())
conn.commit()
print('Migration applied successfully')
conn.close()
"
```

**Verify:**
```bash
python -c "
import os, psycopg2
conn = psycopg2.connect(os.environ.get('DATABASE_URL', 'postgresql://postgres:dev@localhost:5432/coach'))
cur = conn.cursor()
cur.execute(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='rides' ORDER BY ordinal_position\")
for row in cur.fetchall():
    print(row)
conn.close()
"
```

**Success criteria:**
- `date` does not appear in the rides column list
- `start_time` shows as `timestamp with time zone`
- `daily_metrics.date` shows as `date`

---

#### Step 3.B -- Update `_SCHEMA` in `server/database.py`

**File:** `server/database.py`

**Change 1:** Remove `date TEXT NOT NULL,` from the `rides` CREATE TABLE (line 30).

**Change 2:** Change `start_time TEXT` to `start_time TIMESTAMPTZ` (line 61).

**Change 3:** Change `timestamp_utc TEXT` to `timestamp_utc TIMESTAMPTZ` in `ride_records` (line 67).

**Change 4:** Change all TEXT date columns to proper types:
- `daily_metrics`: `date TEXT PRIMARY KEY` -> `date DATE PRIMARY KEY`
- `planned_workouts`: `date TEXT` -> `date DATE`
- `power_bests`: `date TEXT NOT NULL` -> `date DATE NOT NULL`
- `periodization_phases`: `start_date TEXT NOT NULL` -> `start_date DATE NOT NULL`, `end_date TEXT NOT NULL` -> `end_date DATE NOT NULL`
- `athlete_settings`: `date_set TEXT NOT NULL` -> `date_set DATE NOT NULL`

**Change 5:** Remove the orphaned index:
```sql
-- Remove this line:
CREATE INDEX IF NOT EXISTS idx_rides_date ON rides(date);
-- Add this line:
CREATE INDEX IF NOT EXISTS idx_rides_start_time ON rides(start_time);
```

**Change 6:** Update `ingest_rides()` INSERT statement (lines 570-582).

Remove `:date` from the INSERT column list and VALUES list. The ride dict no longer needs a `date` key.

**Change 7:** Update `parse_ride_json()` to stop producing `ride["date"]`.

Remove `ride_date` computation entirely. Remove `"date": ride_date` from the ride dict.

**Change 8:** Update `map_activity_to_ride()` to stop producing `ride["date"]`.

Remove `"date": date` from the ride dict. (Callers that need a local date derive it from `start_time` at query time.)

**Change 9:** Update all code that writes to `power_bests` to compute date from `start_time`:
- `ingest_rides()` line 605: change `ride["date"]` to derive from `start_time`
- `sync.py _download_rides()` line 589: change `ride["date"]` 
- `single_sync.py` line 145: change `target_date`

For power_bests, the `date` column should store the LOCAL date (derived from the ride's start_time in the user's timezone). In background contexts (ingest, sync), use UTC. In request contexts, use the ContextVar timezone. Since power_bests.date is used for power curve filtering, UTC is acceptable for background jobs.

---

#### Step 3.C -- Fix SUBSTR-based queries

After the `date` column type changes from TEXT to DATE, `SUBSTR(date, 1, 7)` breaks.

**File: `server/queries.py` `get_ftp_history_rows()` (lines 93, 103)**

Current:
```python
query = """SELECT SUBSTR(date, 1, 7) as month, MAX(ftp) as ftp, MAX(weight) as weight_kg
           FROM daily_metrics WHERE ftp > 0"""
...
query += " GROUP BY SUBSTR(date, 1, 7) ORDER BY month"
```

New:
```python
query = """SELECT TO_CHAR(date, 'YYYY-MM') as month, MAX(ftp) as ftp, MAX(weight) as weight_kg
           FROM daily_metrics WHERE ftp > 0"""
...
query += " GROUP BY TO_CHAR(date, 'YYYY-MM') ORDER BY month"
```

**File: `server/routers/analysis.py` `power_curve_history()` (line 36)**

Current:
```python
rows = conn.execute("""
    SELECT SUBSTR(date, 1, 7) as month, duration_s, MAX(power) as power
    FROM power_bests
    GROUP BY month, duration_s
    ORDER BY month, duration_s
""").fetchall()
```

New:
```python
rows = conn.execute("""
    SELECT TO_CHAR(date, 'YYYY-MM') as month, duration_s, MAX(power) as power
    FROM power_bests
    GROUP BY TO_CHAR(date, 'YYYY-MM'), duration_s
    ORDER BY month, duration_s
""").fetchall()
```

**File: `server/routers/rides.py` `monthly_summary()`**

Already rewritten in Step 2.B to use `TO_CHAR((...), 'YYYY-MM')`.

---

#### Step 3.D -- Fix Python code that expects string returns from DATE/TIMESTAMPTZ columns

After column type changes, `psycopg2` returns `datetime.date` objects for DATE columns and `datetime.datetime` objects for TIMESTAMPTZ columns. Code that does string operations like `row["date"][:10]` or string comparisons will break.

**Systematic fix approach:** For every `row["date"]` access, check if downstream code needs a string. If so, use `.isoformat()` or `str()`. The `RealDictCursor` returns native Python types.

Key sites:
- `server/queries.py` `get_ftp_history_rows()`: `r["month"]` is already a string from `TO_CHAR()`
- `server/coaching/tools.py` `get_pmc_metrics()`: `row["date"]` from `daily_metrics` is now `datetime.date` -- add `.isoformat()` where returned to the agent
- `server/coaching/tools.py` `get_periodization_status()`: `p["start_date"]`, `p["end_date"]` from `periodization_phases` are now `datetime.date` -- the comparison `p["start_date"] <= today` works if `today` is also `datetime.date`. But `user_today()` returns a string. Fix: compare with `str(p["start_date"])` or change `user_today()` to return `datetime.date`.
- `server/routers/rides.py`: All queries now use `::TEXT` cast in SELECT, so the returned `date` is already a string.

> **DECISION NEEDED:** Should `user_today()` return `datetime.date` instead of `str`? Returning `datetime.date` would be more natural for comparisons with DATE columns, but would require updating all callers that use string formatting. Recommendation: keep returning `str` for backward compatibility, and explicitly convert DATE column results to strings where needed.

---

#### Step 3.E -- Add multi-athlete user_id to daily_metrics

**Migration SQL (add to `scripts/migrate_timezone.sql`):**
```sql
ALTER TABLE daily_metrics ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'athlete';
-- Cannot drop PK and recreate atomically; use a single statement:
ALTER TABLE daily_metrics DROP CONSTRAINT IF EXISTS daily_metrics_pkey;
ALTER TABLE daily_metrics ADD PRIMARY KEY (user_id, date);
```

**Update `compute_daily_pmc()` to accept and use `user_id`:**
```python
def compute_daily_pmc(conn, since_date: str | None = None, tz_name: str = "UTC", user_id: str = "athlete"):
```

All queries inside `compute_daily_pmc` that touch `daily_metrics` add `WHERE user_id = %s` / include `user_id` in INSERTs.

**Update `_SCHEMA` in `server/database.py`:**
```sql
CREATE TABLE IF NOT EXISTS daily_metrics (
    user_id TEXT NOT NULL DEFAULT 'athlete',
    date DATE NOT NULL,
    total_tss REAL,
    ctl REAL,
    atl REAL,
    tsb REAL,
    weight REAL,
    ftp REAL,
    notes TEXT,
    PRIMARY KEY (user_id, date)
);
```

**Update callers of PMC query functions:**
- `get_current_pmc_row(conn)` -> add optional `user_id` param, filter `WHERE user_id = %s`
- `get_pmc_row_for_date(conn, date)` -> add optional `user_id` param

---

#### Step 3.F -- Run integration tests against migrated schema

```bash
./scripts/run_integration_tests.sh -v
```

The integration test conftest should run the migration SQL before tests. If the test DB is created fresh by the conftest, the updated `_SCHEMA` from Step 3.B handles it.

**Success criterion:** All integration tests pass against the new schema.

---

### Phase 4: Rebuild PMC and Smoke Test

---

#### Step 4.A -- Full ingest + rebuild PMC

**Prerequisite:** Verify local dev DB is running:
```bash
podman ps | grep coach-db
```

**Action 1:** Run full ingest (this will re-run `compute_daily_pmc`):
```bash
source venv/bin/activate && python -m server.ingest
```

**Action 2:** If the DB already has data, manually trigger a PMC rebuild:
```bash
python -c "
from server.database import get_db
from server.ingest import compute_daily_pmc
with get_db() as conn:
    compute_daily_pmc(conn, tz_name='America/Chicago')
print('PMC rebuilt')
"
```

**Success criterion:** Ingest exits 0. `daily_metrics` table has rows. No SQL errors.

---

#### Step 4.B -- End-to-end smoke test with timezone header

**Action 1:** Start backend:
```bash
source venv/bin/activate && uvicorn server.main:app --reload &
```

**Action 2:** Test ride list with timezone:
```bash
curl -s -H "X-Client-Timezone: America/Chicago" \
  http://localhost:8000/api/rides?limit=5 | python3 -m json.tool | head -30
```

**Action 3:** Test daily summary:
```bash
curl -s -H "X-Client-Timezone: America/Chicago" \
  http://localhost:8000/api/rides/summary/daily?days=7 | python3 -m json.tool
```

**Action 4:** Test PMC data:
```bash
curl -s -H "X-Client-Timezone: America/Chicago" \
  http://localhost:8000/api/analysis/ftp-history | python3 -m json.tool | head -20
```

**Action 5:** Verify the same ride appears on different dates for different timezones:
```bash
# Get a ride that was recorded late at night UTC
# Compare the date field between UTC and America/Chicago
curl -s -H "X-Client-Timezone: UTC" \
  http://localhost:8000/api/rides?limit=1 | python3 -m json.tool
curl -s -H "X-Client-Timezone: America/Chicago" \
  http://localhost:8000/api/rides?limit=1 | python3 -m json.tool
```

**Success criteria:**
- All endpoints return valid JSON
- Ride dates reflect the requested timezone
- No 500 errors
- PMC endpoint returns data with valid date keys
- Frontend build completes: `cd frontend && npm run build`

---

## Global Testing Strategy

**Unit Tests** (`tests/unit/`)
- `tests/unit/test_dates.py` -- 7+ tests: ContextVar isolation, user_today with various timezones
- `tests/unit/test_intervals_icu.py` -- 2+ tests: map_activity_to_ride uses UTC start_date
- `tests/unit/test_ingest.py` -- 1+ test: parse_ride_json does not query athlete_settings timezone
- Run: `pytest tests/unit/ -v`

**Integration Tests** (`tests/integration/`)
- `tests/integration/test_timezone_queries.py` -- 4+ tests: AT TIME ZONE pattern, PMC grouping, date filtering
- Run: `./scripts/run_integration_tests.sh -v`

**Frontend Build Verification**
- `cd frontend && npm run build` -- TypeScript must compile cleanly

---

## Success Criteria

1. `pytest tests/unit/` passes with 0 failures
2. `./scripts/run_integration_tests.sh` passes with 0 failures
3. `cd frontend && npm run build` exits 0
4. `grep -rn "rides\.date\|r\.date\|row\[.date.\]" server/` returns ZERO matches referencing the dropped column (planned_workouts.date, daily_metrics.date, power_bests.date are acceptable)
5. `rides` table has no `date` column: `SELECT column_name FROM information_schema.columns WHERE table_name='rides'` does not include `date`
6. `rides.start_time` column type is `TIMESTAMPTZ`
7. `athlete_settings` has no rows with `key = 'timezone'`
8. `grep -rn "datetime.now()" server/` returns ZERO calls without explicit timezone
9. Ride endpoints return different `date` values when called with `X-Client-Timezone: UTC` vs `X-Client-Timezone: America/Chicago` for rides near midnight UTC
10. PMC computation groups rides by the timezone-local date, not UTC date

---

## Dependency Graph

```
Phase 1 (normalize data)
  Step 1.A (intervals.icu UTC)  ----+
  Step 1.B (ingest stop date)  -----+---> Phase 2 (rewrite queries)
  Step 1.C (datetime.now fixes) ----+       |
  Step 1.D (remove tz persistence) -+       |
  Step 1.E (sync.py tz source)  ----+       v
                                        Phase 3 (schema migration)
                                            |
                                            v
                                        Phase 4 (rebuild + smoke test)
```

Phases are sequential. Within Phase 1, steps can be done in any order. Within Phase 2, steps can be done in any order. Phase 3 must come after Phase 2 (all queries rewritten). Phase 4 must come after Phase 3 (schema applied).
