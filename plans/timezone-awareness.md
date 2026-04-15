# Timezone Awareness — Research Report

**Status:** Architecture finalized — Phase 0 partially implemented in worktree (needs revision), Phases 1–4 pending
**Branch:** `worktree-fix-timezone-awareness`
**Date:** 2026-04-10

---

## Executive Summary

The platform has **zero timezone awareness** for any calendar-date computation. Every call to `datetime.now()`, `datetime.today()`, and `date.today()` in the backend returns the server's UTC wall clock. On Cloud Run the server is always UTC. A user in UTC-6 who uses the app after 6 PM local time will see the server treating tomorrow's date as "today" — breaking the AI coach's day references, upcoming workout lookups, weekly summaries, PMC chart endpoints, Garmin sync windows, and the Dashboard "today" highlight.

There is no mechanism for the browser to communicate the user's timezone to the backend. No `X-Timezone` header, no stored timezone field on the athlete, no `pytz`/`zoneinfo`/`dateutil` usage for business-logic dates anywhere in `server/`.

---

## Root Causes

### RC-1 — No athlete timezone stored
There is no `timezone` column on the `users` table, `coach_settings`, or `athlete_settings`. The system has no persistent knowledge of where the athlete is located.

### RC-2 — No timezone propagated from client to server
`lib/api.ts` (`authHeaders()`) sends only the `Authorization: Bearer` header. No timezone offset or IANA timezone name is sent with any request. The coaching chat request body (`ChatRequest` schema) has no timezone field.

### RC-3 — All date columns are TEXT
Every date/timestamp column in the schema is `TEXT` (plain `YYYY-MM-DD` or ISO8601 string). PostgreSQL cannot perform timezone conversion on text columns. `psycopg2` returns raw Python `str` objects. There is no `TIMESTAMPTZ` or `DATE` column for any athlete-facing data.

### RC-4 — Frontend uses `toISOString()` for "today"
Two critical components compute "today" via `new Date().toISOString().slice(0, 10)`, which always yields the UTC date. Calendar and Analysis range computations (the majority of the codebase) correctly use local date getters, creating an inconsistency within the same app.

---

## Affected Files — Full Inventory

### Backend — Critical (wrong day shown/used)

| File | Line(s) | Call | Impact |
|------|---------|------|--------|
| `server/coaching/agent.py` | 95–97 | `datetime.now()` | LLM system prompt "today" is UTC. All natural-language day resolution ("next Tuesday") and 7-day training context are anchored to the wrong date for any user past their local 6 PM. |
| `server/coaching/agent.py` | 146 | `datetime.now()` | `seven_days_ago` for recent training context uses UTC. |
| `server/coaching/tools.py` | 189–190 | `datetime.now()` × 2 | `get_upcoming_workouts()`: "today" window starts on UTC date. Evening users see no workout for "today." |
| `server/coaching/tools.py` | 294 | `datetime.now()` | `get_periodization_status()`: phase lookup `start ≤ today ≤ end` may return the wrong phase at day boundaries. |
| `server/routers/rides.py` | 92 | `date.today()` | `GET /api/rides/summary/daily` — "last N days" window is UTC-anchored; dashboard strip covers wrong days. |

### Backend — High (query windows off by one day)

| File | Line(s) | Call | Impact |
|------|---------|------|--------|
| `server/coaching/tools.py` | 149 | `datetime.now()` | `get_recent_rides()` cutoff is UTC; evening rides may be excluded from coaching context. |
| `server/coaching/tools.py` | 244 | `datetime.now()` | `get_training_summary()` cutoff. |
| `server/coaching/tools.py` | 593–594 | `datetime.now()` × 2 | `get_power_curve()` date range with `last_n_days`. |
| `server/coaching/planning_tools.py` | 394 | `datetime.now()` | `get_week_summary()` default date: wrong week computed in the evening. |
| `server/coaching/planning_tools.py` | 469–470 | `datetime.now()` × 2 | `sync_workouts_to_garmin()`: "current week" window uses UTC; Garmin sync covers wrong days. |
| `server/services/sync.py` | 370–372 | `datetime.now()` × 2 | Ride download oldest/newest bounds are UTC. |
| `server/services/sync.py` | 639–640, 708–713 | `datetime.now()` × 4 | Planned workout download/upload windows. |

### Backend — Medium (data integrity, historical records)

| File | Line(s) | Call | Impact |
|------|---------|------|--------|
| `server/queries.py` | 37 | `datetime.now()` | `get_current_ftp()` "as of today" lookup uses UTC date. |
| `server/queries.py` | 72 | `datetime.now()` | `get_power_bests_rows()` default end date. |
| `server/database.py` | 456 | `datetime.now()` | `set_athlete_setting()` stamps FTP/weight changes with UTC date. Updates made in the evening are recorded as tomorrow. |
| `server/ingest.py` | 404 | `datetime.today()` | `compute_daily_pmc()` loop end. PMC includes a phantom future row from the user's perspective. |
| `server/services/intervals_icu.py` | 171–173, 414 | `datetime.now()` × 3 | Fetch window and weight update date default. |

### Ingestion Inconsistency

| File | Line(s) | Behavior |
|------|---------|----------|
| `server/ingest.py` | 84, 178 | Raw FIT/JSON ingest slices `start_time[:10]` — FIT timestamps are UTC. A ride at 11:30 PM local (UTC-5) gets tomorrow's date. |
| `server/services/intervals_icu.py` | 304–309 | intervals.icu sync uses `start_date_local` (a pre-localized date). **This is wrong — see architecture below.** |

### Frontend — Critical / High

| File | Line(s) | Issue |
|------|---------|-------|
| `frontend/src/pages/Dashboard.tsx` | 250 | `new Date().toISOString().slice(0, 10)` — UTC date used as "today" for the daily-summary API call. |
| `frontend/src/pages/Analysis.tsx` | 116 | `today.toISOString().slice(0, 10)` — same UTC-date pattern for the analysis range. |
| `frontend/src/pages/Dashboard.tsx` | 89–91 | `SevenDayStrip` iterates over dates derived from the UTC "today", so the 7-day window is UTC-anchored. |
| `frontend/src/lib/api.ts` | `authHeaders()` | No `X-Client-Timezone` or date offset is ever sent to the backend. |
| `frontend/src/components/CoachPanel.tsx` | — | `calendarDate` from context is sent in the chat message body as plain text; no timezone metadata included. |

### Frontend — Correct (no action needed)

| File | Lines | Why it's fine |
|------|-------|---------------|
| `frontend/src/components/Calendar.tsx` | 46–68, 84, 170 | All week/day boundaries use `getFullYear()/getMonth()/getDate()` (local methods). `toDateStr()` builds local YYYY-MM-DD. |
| `frontend/src/pages/Dashboard.tsx` | 224–227 | `planMondays`/`thisMonday` computed with local constructors — correct. |
| `frontend/src/pages/Analysis.tsx` | 71–83 | `rangeToDates()` uses local date methods — correct. |
| `frontend/src/utils/chart-helpers.ts` | 4–23 | `isoWeekToMonday()` uses local constructors — correct. |
| `frontend/src/pages/Rides.tsx` | 244–251 | Display formatting uses `toLocaleTimeString()` — correct. |

---

## Existing Correct Usage (backend)

These are the only timezone-aware calls in the server codebase. They are correct for their purpose (audit/system timestamps, not calendar dates) and should be preserved:

| File | Lines | Usage |
|------|-------|-------|
| `server/services/sync.py` | 12, 39 | `datetime.now(timezone.utc)` — `started_at`, `completed_at`, `synced_at` on sync runs |
| `server/coaching/session_service.py` | 4, 27, 124 | `datetime.now(timezone.utc)` — chat session created/updated timestamps |
| `server/coaching/memory_service.py` | 4, 26 | `datetime.now(timezone.utc)` — coach memory entry timestamps |
| `server/auth.py` | 39, 41, 49 | `datetime.datetime.now(datetime.timezone.utc)` — JWT `exp`/`iat` claims |

---

## Architectural Design — Correct Approach

**Core principle (engineering lead):** Store everything in UTC. FIT files already contain UTC timestamps — store them as-is. intervals.icu provides UTC timestamps — use them, not the pre-localized `start_date_local`. When presenting dates to the user, derive local dates using the `X-Client-Timezone` browser header. No timezone is ever stored on the athlete. No timezone conversion at write time.

---

### The Two Classes of Temporal Data

**Moments-in-time** — when something physically happened. Store as `TIMESTAMPTZ` (UTC). Never convert at write time.
- `rides.start_time` — FIT UTC timestamp, stored as-is
- `ride_records.timestamp_utc` — per-second recording
- Audit fields: `chat_sessions.created_at`, `sync_runs.started_at`, etc.

**Calendar-day intentions** — a named day the athlete plans around, with no "when exactly" component. Store as `DATE`. These are already correct — no UTC issue applies.
- `planned_workouts.date` — "do this workout on April 9"
- `periodization_phases.start_date / end_date` — phase boundaries
- `daily_metrics.date` — the athlete's local training day (PK), derived at PMC compute time from ride timestamps using the client timezone

### `rides.date` — Remove It

`rides.date` is a pre-computed local date derived from `start_time`. It is wrong by design: it bakes in a timezone at write time and cannot be corrected for travelers or multi-timezone riders (e.g., a ride done in Mountain Time being dated in Eastern Time).

**Remove `rides.date` entirely.** All queries that need a ride's local date compute it at query time using the athlete's current timezone:
```sql
WHERE (r.start_time AT TIME ZONE %(tz)s)::DATE BETWEEN %(start)s AND %(end)s
```
The `%(tz)s` parameter is the IANA timezone string from the `X-Client-Timezone` header, passed through from the HTTP request.

### intervals.icu — Use UTC, Not `start_date_local`

`server/services/intervals_icu.py` currently uses `start_date_local` (a date pre-localized by intervals.icu). This bakes in a timezone at storage time — wrong for the same reason as `rides.date`. Switch to the raw UTC `start_date` / `start_time` timestamp. Store as `TIMESTAMPTZ`. Local date is derived at query time like any other ride.

### Timezone Transport — Header Only, No Storage

- **Frontend:** `authHeaders()` sends `X-Client-Timezone: Intl.DateTimeFormat().resolvedOptions().timeZone` on every request (the browser provides the IANA name automatically — one line of code, no library needed)
- **Backend middleware:** reads `X-Client-Timezone`, validates as IANA name, falls back to `"UTC"`, stores in `request.state.client_tz_str`
- **No `athlete_settings` timezone storage.** The header is the only source. Background sync jobs write UTC — no timezone needed at write time.
- **`ContextVar`, not `threading.local`** — `threading.local` is unsafe in FastAPI's async context (not isolated across concurrent requests). Use `contextvars.ContextVar`:

```python
# server/utils/dates.py — correct implementation
from contextvars import ContextVar
from datetime import datetime
from zoneinfo import ZoneInfo

_request_tz: ContextVar[ZoneInfo] = ContextVar('request_tz', default=ZoneInfo("UTC"))

def set_request_tz(tz: ZoneInfo) -> None:
    _request_tz.set(tz)

def get_request_tz() -> ZoneInfo:
    return _request_tz.get()

def user_today(tz: ZoneInfo | None = None) -> str:
    """Return the user's local date as YYYY-MM-DD."""
    if tz is None:
        tz = _request_tz.get()
    return datetime.now(tz).strftime("%Y-%m-%d")
```

---

## Column Type Migration Plan

| Column | Current | Target | Notes |
|--------|---------|--------|-------|
| `rides.start_time` | TEXT | TIMESTAMPTZ | FIT UTC timestamp; store as-is |
| `rides.date` | TEXT | **DROP** | Derived at query time via `AT TIME ZONE`; remove entirely |
| `ride_records.timestamp_utc` | TEXT | TIMESTAMPTZ | Per-second UTC recording |
| `daily_metrics.date` | TEXT (PK) | DATE (PK) | Local training day, computed at PMC time using client tz |
| `planned_workouts.date` | TEXT | DATE | Calendar intention; no UTC issue |
| `periodization_phases.start_date` | TEXT | DATE | Calendar boundary |
| `periodization_phases.end_date` | TEXT | DATE | Calendar boundary |
| `power_bests.date` | TEXT | DATE | Local date derived from ride at compute time |
| `athlete_settings.date_set` | TEXT | DATE | Calendar day stamp |
| Audit timestamps (chat, sync, memory) | TEXT | TIMESTAMPTZ (defer) | Already written as UTC strings; low priority |

---

## Implementation Phases

**Order matters: fix application code before touching the schema.**

### Phase 0 — Timezone Transport (no schema change)

- `frontend/src/lib/api.ts` — add `X-Client-Timezone` header to `authHeaders()`
- `server/main.py` — `ClientTimezoneMiddleware` validates header, stores in `request.state.client_tz_str`
- `server/utils/dates.py` — `ContextVar`-based `set_request_tz` / `get_request_tz` / `user_today()`
- `server/dependencies.py` — `get_client_tz(request)` FastAPI dependency
- Fix all `datetime.now()` / `date.today()` business-logic calls to use `user_today(tz)`
- Fix frontend `toISOString().slice(0,10)` → local date getters in `Dashboard.tsx` and `Analysis.tsx`

### Phase 1 — Remove `rides.date` from Application Code

Before dropping the column, remove all application references to it:

- **Ingest** (`server/ingest.py`): stop computing and writing `ride_date` / `"date"` field. Store only `start_time` as the raw UTC string (it becomes TIMESTAMPTZ in Phase 2).
- **intervals.icu** (`server/services/intervals_icu.py`): switch from `start_date_local` to the raw UTC `start_date` or `start_time`. Remove the `"date"` field from the ride insert.
- **All queries filtering or selecting `rides.date`**: rewrite to `(start_time AT TIME ZONE %(tz)s)::DATE`. The `tz` parameter flows from `get_client_tz()` / `get_request_tz()`.
- **PMC recomputation** (`compute_daily_pmc()`): accept a timezone parameter. Group rides by `(start_time AT TIME ZONE %(tz)s)::DATE`. Store the resulting local `DATE` in `daily_metrics.date`.
- **Coaching tools, planning tools, sync service**: all date-range queries that referenced `rides.date` now use the `AT TIME ZONE` pattern.

### Phase 2 — Schema Migration

Once the application no longer writes or reads `rides.date`:

```sql
-- Drop the now-unused rides.date column
ALTER TABLE rides DROP COLUMN date;

-- Promote TEXT timestamps to proper types
ALTER TABLE rides ALTER COLUMN start_time TYPE TIMESTAMPTZ USING start_time::TIMESTAMPTZ;
ALTER TABLE ride_records ALTER COLUMN timestamp_utc TYPE TIMESTAMPTZ USING timestamp_utc::TIMESTAMPTZ;

-- Promote TEXT date columns to DATE
ALTER TABLE daily_metrics ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE planned_workouts ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE periodization_phases ALTER COLUMN start_date TYPE DATE USING start_date::DATE;
ALTER TABLE periodization_phases ALTER COLUMN end_date TYPE DATE USING end_date::DATE;
ALTER TABLE power_bests ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE athlete_settings ALTER COLUMN date_set TYPE DATE USING date_set::DATE;
```

Fix two SQL sites that use substring on date columns (breaks on `DATE` type):
- `queries.py: get_ftp_history_rows()` — `SUBSTR(date, 1, 7)` → `TO_CHAR(date, 'YYYY-MM')`
- `routers/rides.py: monthly_summary()` — same change

Fix Python read sites: `row["date"]` now returns `datetime.date`, not `str`. Use `.isoformat()` where a string is needed. `row["start_time"]` returns a timezone-aware `datetime` — handle accordingly.

### Phase 3 — Multi-Athlete PMC (bundle with Phase 2)

`daily_metrics` has no `user_id` column — the PMC is global. Since Phase 2 already touches this table, add `user_id` in the same migration:

```sql
ALTER TABLE daily_metrics ADD COLUMN user_id TEXT NOT NULL DEFAULT 'athlete';
ALTER TABLE daily_metrics DROP CONSTRAINT daily_metrics_pkey;
ALTER TABLE daily_metrics ADD PRIMARY KEY (user_id, date);
```

Update `compute_daily_pmc()` and all PMC queries to scope by `user_id`.

### Phase 4 — Rebuild PMC from Corrected Data

After the schema migration, rebuild `daily_metrics` by re-running `compute_daily_pmc()` with the athlete's current timezone from the `X-Client-Timezone` header. This is safe to re-run any number of times — the function rebuilds from source ride timestamps.

No `rides.date` backfill is needed — that column has been dropped. Historical `rides.start_time` values are already UTC strings; the `TIMESTAMPTZ` cast in Phase 2 promotes them correctly.

---

## Query Pattern Reference

**"Rides in the last N days" (client timezone):**
```sql
SELECT * FROM rides
WHERE (start_time AT TIME ZONE %(tz)s)::DATE
      >= (NOW() AT TIME ZONE %(tz)s)::DATE - INTERVAL '%(n)s days'
ORDER BY start_time DESC
```

**"Rides this week" (week boundaries computed in Python):**
```sql
SELECT * FROM rides
WHERE (start_time AT TIME ZONE %(tz)s)::DATE
      BETWEEN %(week_start)s AND %(week_end)s
```
`week_start` and `week_end` are computed in Python using `user_today(tz)` + `timedelta`.

**PMC group-by:**
```sql
SELECT (start_time AT TIME ZONE %(tz)s)::DATE AS local_date,
       SUM(tss) AS daily_tss
FROM rides
WHERE start_time >= %(earliest)s
GROUP BY local_date
ORDER BY local_date
```

---

## Frontend Display Layer

Date/time formatting is currently scattered across components with no shared utilities. `format.ts` has formatters for duration, distance, elevation — but zero date/time display functions. After Phase 2, `rides.start_time` becomes a full UTC ISO string; components that currently receive a `YYYY-MM-DD` date string will receive a timestamp and must handle it correctly.

### Additions to `frontend/src/lib/format.ts`

```typescript
// For UTC timestamp strings from the server (rides.start_time, sync timestamps, etc.)
// new Date() parses UTC correctly; toLocaleDateString/toLocaleTimeString render in browser timezone.
export function fmtDate(isoUtc: string): string {
  return new Date(isoUtc).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric'
  })
}

export function fmtDateLong(isoUtc: string): string {
  return new Date(isoUtc).toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
  })
}

export function fmtDateTime(isoUtc: string): string {
  return new Date(isoUtc).toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit'
  })
}

export function fmtTime(isoUtc: string): string {
  return new Date(isoUtc).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit'
  })
}

// For date-only strings (YYYY-MM-DD) from planned_workouts, periodization_phases, daily_metrics.
// Appending T00:00:00 forces local midnight — prevents UTC shift turning Apr 9 into Apr 8.
export function fmtDateStr(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric'
  })
}

export function fmtDateStrLong(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
  })
}

// Canonical local YYYY-MM-DD string for use as API query parameters.
// Replaces the scattered getFullYear()/getMonth()/getDate() constructions throughout the codebase.
export function localDateStr(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
```

### Why Two Separate Functions (`fmtDate` vs `fmtDateStr`)

The distinction matters permanently — not just during migration:
- **UTC timestamps** (`rides.start_time`, sync events): parse with `new Date(iso)` — the browser converts UTC to local automatically
- **Date-only strings** (`planned_workouts.date`, `periodization_phases.*`): these remain `DATE` columns forever, returned as bare `YYYY-MM-DD`. Parsing with `new Date('2026-04-09')` treats it as UTC midnight and shifts it to Apr 8 at 8 PM EDT. Appending `T00:00:00` forces local midnight interpretation.

### Call Sites to Update

| File | Line | Current | Replace with |
|------|------|---------|-------------|
| `Rides.tsx` | 251 | `new Date(ts).toLocaleTimeString(...)` | `fmtTime(ts)` |
| `Rides.tsx` | 278 | `new Date(currentDate + 'T00:00:00').toLocaleDateString(...)` | `fmtDateStr(currentDate)` |
| `Calendar.tsx` | 218 | `new Date(selectedDay + 'T00:00:00').toLocaleDateString(...)` | `fmtDateStrLong(selectedDay)` |
| `Dashboard.tsx` | 358 | `new Date(nextWorkout.date + 'T00:00:00').toLocaleDateString(...)` | `fmtDateStr(nextWorkout.date)` |
| `UserManagement.tsx` | 152 | `new Date(u.last_login).toLocaleDateString()` | `fmtDate(u.last_login)` |
| `Dashboard.tsx` | 228 | inline `getFullYear()/getMonth()/getDate()` fmt | `localDateStr(d)` |
| `Dashboard.tsx` | 252 | inline `getFullYear()/getMonth()/getDate()` for today | `localDateStr()` |
| Analysis, Calendar | various | inline `getFullYear()/getMonth()/getDate()` constructions | `localDateStr(d)` |

Note: `RideTimelineChart.tsx` uses `new Date(start_time).getTime()` for chart math (millisecond positioning) — this is UTC-based arithmetic, timezone-irrelevant, leave it alone.

---

## What Does NOT Change

- `planned_workouts.date` — calendar intention, no UTC issue, no query change needed
- `periodization_phases.start_date / end_date` — same
- Frontend `Calendar.tsx`, `Analysis.tsx rangeToDates()`, `chart-helpers.ts` — already use local date getters correctly
- The four `datetime.now(timezone.utc)` audit calls in sync, session, memory, auth — correct, do not touch

---

## Current Worktree Status

The worktree (`worktree-fix-timezone-awareness`) contains a **Phase 0 partial implementation** that must be substantially revised:

| Item | Status | Action needed |
|------|--------|---------------|
| `X-Client-Timezone` header in frontend | ✅ Done | Keep |
| Frontend `toISOString` → local date fixes | ✅ Done | Keep |
| `ClientTimezoneMiddleware` in `main.py` | ✅ Done | Keep |
| `server/utils/dates.py` with `user_today()` | ⚠️ Buggy | Replace `threading.local` with `ContextVar` |
| `server/dependencies.py` `get_client_tz()` | ✅ Done | Keep |
| All `datetime.now()` business-logic fixes | ✅ Done | Keep |
| `athlete_settings["timezone"]` persistence | ❌ Remove | Drop entirely — no stored timezone |
| FIT ingest `_utc_to_local_date()` helper | ❌ Remove | Replace with plain UTC storage, no local conversion |
| `rides.date` still written in ingest | ❌ Wrong | Phase 1: stop writing it, then drop the column |
| intervals.icu `start_date_local` → UTC | ❌ Not done | Phase 1 |
| Schema type migrations | ❌ Not done | Phase 2 |
| Multi-athlete PMC `user_id` | ❌ Not done | Phase 3 |

---

## Dependencies

- Python `zoneinfo` (stdlib, Python 3.9+) — no new package
- Python `contextvars` (stdlib, Python 3.7+) — no new package
- Frontend: `Intl.DateTimeFormat` built-in — no new package
