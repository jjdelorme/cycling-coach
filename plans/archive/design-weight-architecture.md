# Weight Architecture Design Document

**Status:** Decision Record — Do Not Implement Without Reading This First  
**Date:** 2026-04-10  
**Author:** Jason + Claude (collaborative design session)

---

## Background

This document captures the architectural decisions and reasoning behind how weight data flows through the cycling coach platform. It was written after an extended research session that explored Withings, Garmin Connect, Intervals.icu, and our own codebase to understand the full picture. The goal is to prevent future confusion about why the system is designed this way.

---

## The Question We Started With

> "The Athlete Weight setting — what does it represent now, and how does it relate to all the W/kg calculations throughout the application?"

That question exposed a more fundamental one: **what is the single source of truth for athlete weight, and how does it stay accurate over time?**

---

## External System Findings

### Garmin

- **FIT files do contain a `user_profile.weight` field.** It is populated from the Garmin device's local athlete profile, which is a snapshot of the profile at the moment recording started. It is NOT read from the cloud during a ride.
- **Garmin Connect → Device sync:** If you update weight in Garmin Connect, the device picks it up on the next Bluetooth sync. The next ride's FIT file then reflects the new weight.
- **Garmin Connect has no public API for writing weight.** Garmin Connect is a closed ecosystem for body composition data. Third-party apps cannot push weight into Garmin Connect programmatically.
- **Garmin Connect does NOT have a native Withings integration.** We confirmed this by checking connect.garmin.com directly. The research agent initially suggested this integration might exist, but hands-on verification showed it does not. This kills one potential data flow path.

### Intervals.icu

- ICU maintains its **own per-day weight time-series** in its wellness log, independent of Garmin.
- When ICU syncs a ride from Garmin, it attaches `icu_weight` to the activity — this is **ICU's own wellness weight for that date**, not the weight from the FIT file.
- ICU's `icu_weight` is what we store in `rides.weight` for ICU-synced rides.
- ICU does **not** have a native Withings integration. Weight must be pushed to ICU explicitly via the wellness endpoint.
- **ICU wellness data does NOT propagate back to Garmin Connect.** The chain is one-way inbound.
- The endpoint: `PUT /api/v1/athlete/{athleteId}/wellness/{YYYY-MM-DD}` with `{"weight": kg}`. Already implemented in our codebase as `intervals_icu.update_weight()`.

### Withings

- Withings provides a fully public OAuth2 API. We've already implemented this integration.
- Measurements are per-timestamp (accurate to the second), stored in our `body_measurements` table as per-date entries.
- Withings does NOT natively sync to Garmin Connect (confirmed hands-on).

---

## The Chain We Hoped For (And Why It Doesn't Work)

We initially explored whether weight could flow automatically through:

```
Withings → Garmin Connect → Garmin FIT file → Intervals.icu → us
```

This breaks in two places:
1. **Withings → Garmin Connect:** No integration exists. Confirmed directly on connect.garmin.com.
2. **Garmin FIT weight → Intervals.icu weight:** Even if the FIT file had correct weight, ICU ignores the FIT-embedded weight for its own W/kg calculations. ICU uses its own wellness time-series.

There is no automatic path through Garmin for weight data. Garmin is effectively a dead end for our weight architecture.

---

## The Architecture We Decided On

```
Withings scale
    ↓  Withings OAuth sync (already implemented)
body_measurements table  ←── Source of truth for measurement history
    ↓  TRIGGER: push per-date to ICU during sync (gap to close)
Intervals.icu wellness/{date}
    ↓  ICU syncs ride from Garmin, attaches icu_weight
ICU activity.icu_weight = our Withings weight ✓
    ↓  Our ICU sync
rides.weight = temporally accurate, Withings-informed ✓
    ↓
W/kg calculations are correct
```

### Key Design Decision: The Trigger Pattern

When Withings sync writes new measurements to `body_measurements`, it **immediately also pushes those weights to Intervals.icu wellness** (one `update_weight(kg, date)` call per measurement). This happens in the same operation — not a separate job, not a scheduled task. Two trigger points exist:

1. `services/withings.py:sync_weight()` — the manual "Sync Weight" button path
2. `services/withings.py:handle_webhook_notification()` — the Withings push notification path (fires when user steps on the scale and Withings notifies us)

Both already call `store_measurements()`. The ICU push is added after `store_measurements()` in both, wrapped in `try/except` so ICU push failure never breaks the Withings sync.

### Why This Timing Works

The typical sequence is:
1. Athlete weighs in on Withings in the morning
2. Our app receives the Withings webhook notification (or athlete hits "Sync Weight")
3. We store in `body_measurements` AND push to ICU wellness for that date
4. Athlete goes for a ride
5. Garmin records the ride, uploads to Garmin Connect
6. ICU syncs the ride from Garmin, attaches `icu_weight` = our pushed weight ✓
7. Our ICU sync pulls the ride with the correct weight in `icu_weight`

The only edge case: if the athlete syncs a ride to ICU *before* their Withings weigh-in syncs to us. In that case ICU uses whatever stale weight it had. This is an acceptable race condition, not a structural problem.

---

## What `rides.weight` Actually Is

This is a common source of confusion. `rides.weight` is NOT a scale measurement. It is populated differently depending on how the ride was ingested:

| Source | rides.weight value |
|---|---|
| ICU-synced ride | `activity["icu_weight"]` — ICU's wellness weight for that date |
| Locally ingested ride | `get_benchmark_for_date("weight_kg")` — last `athlete_settings.weight_kg` entry before the ride date |
| FIT fallback | `user_profile.weight` from FIT file — Garmin device profile snapshot |

After the trigger is implemented, ICU-synced rides will carry the correct Withings-informed weight via `icu_weight`. Non-ICU rides fall back to `athlete_settings`, which is acceptable.

---

## Three Weight Stores and Their Roles

| Store | Source | Role | Temporal model |
|---|---|---|---|
| `body_measurements` | Withings API | Measurement log, highest-priority source in PMC | Per actual weigh-in date |
| `athlete_settings` (key=`weight_kg`) | Manual UI entry | "Current" athlete profile, fallback for non-ICU rides | Per setting-change date (carry-forward) |
| `rides.weight` | Mixed (see above) | Ride-specific W/kg denominator | Per ride |

---

## Weight Consumption Points and Their Correctness

### PMC pipeline (`compute_daily_pmc`)

Priority chain per day:
1. Withings `body_measurements` for that exact date (scale measurement — most accurate)
2. Most recent `rides.weight` on or before this date (carry-forward)
3. `athlete_settings.weight_kg` active on this date (manual carry-forward)
4. Default 0

**Assessment: Correct.** Withings is highest priority. After the trigger is implemented, the carry-forward source (rides.weight) will also improve.

### FTP history W/kg (`analysis.py`)

Uses `MAX(weight)` per month from `rides` table.

**Assessment: Bug.** `MAX` is wrong — should be `AVG` or end-of-month weight. Also uses raw `rides.weight` which is a hybrid of ICU weights and carry-forward values. This should be fixed to join against `daily_metrics.weight` (which has the correct PMC-priority weight) instead.

### Coaching agent W/kg

Uses current `athlete_settings.weight_kg`.

**Assessment: Acceptable.** The coaching agent prescribes future workouts, so using the current weight is appropriate. Historical accuracy is not needed here.

### Weight chart in Analysis

New endpoint (`/api/analysis/weight-history`) returns only actual measurement dates from:
- `body_measurements` (Withings, most accurate)
- `athlete_settings` entries (manual entries — each is a real data point)

Explicitly excludes `rides.weight` (carry-forward, not real measurements).

**Assessment: Correct.** This is what the weight trend chart should show.

---

## What We Decided NOT To Do

### Push weight to Garmin Connect

**Decision: Do not attempt.**  
Garmin Connect has no public API for writing weight. The only path is via the Garmin Health API (enterprise partner program, not open to individual developers). Not worth pursuing.

### Route through Garmin FIT files

**Decision: Ignore FIT file weight.**  
`user_profile.weight` in FIT files is noisy, depends on device sync timing, and is ignored by Intervals.icu for its own calculations anyway. It provides no value in our pipeline and should not be treated as authoritative.

### Rely on any ICU native health integration as a short-circuit

**Decision: Not applicable.**  
Intervals.icu does not have a native Withings integration. We are the only path for getting Withings data into ICU's wellness log. We own the Withings integration and push to ICU from our side.

---

## The Weight Resolver Abstraction

### The Problem

The priority chain (Withings > rides.weight > athlete_settings > default) is implemented in exactly one place: inline inside `compute_daily_pmc()` in `server/ingest.py`. Every other consumer that needs weight reads `athlete_settings.weight_kg` directly — bypassing Withings entirely.

This means: if a user has a Withings scale and syncs it daily, the coaching agent, BMR calculations, ride ingestion, and nutrition context all still use the stale manual weight setting. Only the PMC chart gets the correct Withings weight.

### The Abstraction

A single function in `server/services/weight.py` encapsulates the priority chain. All consumers call this instead of querying `athlete_settings` directly.

```python
# server/services/weight.py

def get_weight_for_date(conn, date: str) -> float:
    """Single source of truth for athlete weight on a given date.

    Priority chain (each level carries forward the most recent value on or before `date`):
    1. Withings body_measurements — most recent measurement on or before date
    2. rides.weight — most recent ride weight on or before date
    3. athlete_settings.weight_kg — most recent manual entry on or before date
    4. Default: 75.0 kg

    Args:
        conn: Active DB connection.
        date: ISO date string (YYYY-MM-DD).

    Returns:
        Weight in kg as float.
    """

def get_current_weight(conn) -> float:
    """Convenience wrapper: today's weight following the full priority chain."""
    from datetime import date
    return get_weight_for_date(conn, date.today().isoformat())
```

`compute_daily_pmc()` is refactored to use this function per day (or its own bulk-prefetch variant for performance — see below).

### Consumers That Must Be Updated

| Consumer | File | Current behavior | Change |
|---|---|---|---|
| Coaching agent context | `coaching/agent.py:108` | `benchmarks.get("weight_kg")` — athlete_settings only | Call `get_current_weight(conn)` |
| Coaching tools | `coaching/tools.py:645` | `settings.get("weight_kg")` — athlete_settings only | Call `get_current_weight(conn)` |
| Nutritionist agent context | `nutrition/agent.py:83` | `settings.get("weight_kg")` — athlete_settings only | Call `get_current_weight(conn)` |
| BMR calculation | `nutrition/tools.py:241` | `settings.get("weight_kg")` — athlete_settings only | Call `get_current_weight(conn)` |
| Ride ingestion | `ingest.py:94` | `get_benchmark_for_date("weight_kg")` — athlete_settings only | Call `get_weight_for_date(conn, ride_date)` |
| PMC pipeline | `ingest.py:458-465` | Correct but inline, unreachable by others | Extract to `get_weight_for_date`, use bulk variant for PMC |
| FTP history W/kg | `queries.py:91` | `MAX(weight) FROM daily_metrics` — uses PMC but MAX is wrong | Use `AVG(weight)` or last-of-month; already uses PMC (correct source) |

### What Stays As-Is

**`analysis.py` weight_history endpoint** — this intentionally returns only actual measurement dates (no carry-forward), for the weight trend chart. It is a display query, not a weight resolver. It should continue querying `body_measurements` and `athlete_settings` directly and should NOT use `get_weight_for_date`.

### Default Weight Fallback

The final fallback (75.0 kg) exists so calculations never divide by zero or produce nonsense, but it is dangerous if silently used — a coaching agent or BMR calculation running on 75 kg for an athlete who actually weighs 60 kg will produce materially wrong prescriptions.

**Decision:** Every time the default is used, emit a `logger.warning` with enough context to diagnose why (date, which sources were checked and found empty). This makes silent fallbacks visible in logs without breaking callers.

```python
logger.warning(
    "weight_resolver_using_default",
    date=date,
    default_kg=75.0,
    reason="no weight found in body_measurements, rides, or athlete_settings",
)
```

**Future consideration — in-app notifications:** A log warning is necessary but not sufficient. The user has no visibility into it. A future notifications system (persistent, dismissible alerts surfaced in the UI) would allow the app to say: "No weight data found — your W/kg and caloric balance calculations may be inaccurate. Connect Withings or set your weight in Settings." Filed in backlog below.

### Performance Note

`get_weight_for_date` runs a query per call. For the PMC pipeline (which calls it for every day in the date range), a bulk variant should be used internally that prefetches all three sources once and resolves per-day in memory — exactly as `compute_daily_pmc` does today. The public API remains `get_weight_for_date(conn, date)` and `get_current_weight(conn)`; the bulk prefetch is an implementation detail.

---

## Manual Weight Setting vs Withings

The `athlete_settings` (key=`weight_kg`) is surfaced as an editable field in Settings → Athlete Profile. When Withings is connected and has measurements, this field becomes redundant and creates two problems:

1. **Confusion**: the user sees a manual weight field that has no visible effect (Withings already outranks it in the PMC priority chain).
2. **Conflict**: editing `weight_kg` in Settings triggers a push to ICU wellness for today (`athlete.py:46-50`), which would overwrite the Withings-pushed value for that date.

**Decision:** Disable (make read-only) the manual `weight_kg` field in Settings when Withings is connected AND has at least one measurement.

- **Withings connected + has measurements** → weight field shows latest Withings value, read-only, labeled "Managed by Withings". No ICU push on edit.
- **Withings not connected OR no measurements** → weight field is editable as normal (manual entry + ICU push as before).

**What stays unchanged on the backend:** The `athlete_settings.weight_kg` record is NOT deleted. It continues to serve as a carry-forward fallback in the PMC priority chain for days that have no Withings measurement, and as the benchmark weight for non-ICU rides. The field is only disabled in the UI — the data remains available as a safety net.

---

## Remaining Work (Implementation Gaps)

### Gap 1: Withings → ICU wellness push trigger (not yet implemented)

**Where:** `server/services/withings.py`, in both `sync_weight()` and `handle_webhook_notification()`  
**What:** After `store_measurements(measurements)`, call `update_weight(m["weight_kg"], m["date"])` for each measurement  
**Why:** Closes the loop so ICU's `icu_weight` on future activity syncs reflects real Withings measurements  
**Risk:** ICU push failure must not break Withings sync — wrap in `try/except`

### Gap 2: Manual weight field disabled when Withings is active (Settings UI)

**Where:** `frontend/src/pages/Settings.tsx:466` — the `weight_kg` row in the Athlete Profile settings list  
**What:** When `withingsStatus?.connected && withingsStatus?.latest_weight_kg`, render the field as read-only showing the latest Withings value with a "Managed by Withings" label instead of the editable input  
**Why:** Prevents confusion and avoids conflicting ICU wellness pushes when Withings is the authoritative source  
**Backend change:** None. `athlete_settings.weight_kg` remains as a PMC fallback; only the UI gate changes.

### Gap 3: FTP history W/kg calculation (bug)

**Where:** `server/routers/analysis.py` or `server/queries.py`, FTP history W/kg query  
**What:** Change `MAX(weight)` to use PMC-accurate weight (join `daily_metrics` on date) and use `AVG` or end-of-period weight  
**Why:** `MAX` per month is incorrect; raw `rides.weight` is a hybrid source that does not reflect our PMC priority chain

---

## Related Files

| File | Role |
|---|---|
| `server/services/withings.py` | Withings API client + sync logic |
| `server/routers/withings.py` | Withings HTTP endpoints |
| `server/services/intervals_icu.py` | `update_weight()` at line 400 |
| `server/routers/athlete.py` | Manual weight setting → ICU push |
| `server/ingest.py:compute_daily_pmc()` | PMC weight priority chain |
| `server/routers/analysis.py` | `/api/analysis/weight-history` endpoint |
| `plans/feat_withings_weight.md` | Original Withings implementation plan |
| `plans/feat_withings_webhooks.md` | Webhook subscription implementation |
