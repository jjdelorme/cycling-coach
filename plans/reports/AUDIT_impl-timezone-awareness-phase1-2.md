# Plan Validation Report: impl-timezone-awareness (Phase 1 stragglers + Phase 2)

## Summary

* **Overall Status:** FAIL
* **Completion Rate:** 5/6 checks passed; 1 CRITICAL blocker

## CRITICAL: `_adapt_sql` Regex Destroys All `AT TIME ZONE` Queries

**File:** `server/database.py` line 41
**Regex:** `re.sub(r":([a-zA-Z_]\w*)", r"%(\1)s", sql)`

This regex converts `:name` named parameters (SQLite style) to `%(name)s` (psycopg2 style). However, it also matches the second colon of Postgres cast syntax `::TYPE`. The result:

| Input | Output (broken) |
|-------|-----------------|
| `::TIMESTAMPTZ` | `:%(TIMESTAMPTZ)s` |
| `::DATE` | `:%(DATE)s` |
| `::TEXT` | `:%(TEXT)s` |

Every `AT TIME ZONE` query in the codebase passes through `_adapt_sql` and will fail at runtime with `TypeError: tuple indices must be integers or slices, not str` because psycopg2 tries to find a parameter named `TIMESTAMPTZ` in the params tuple.

**Proof:** Unit test `test_coach_system_prompt_includes_nutrition_section` FAILS with exactly this error (see test output below). The test hits a real DB connection path and the mangled SQL reaches psycopg2.

**Fix:** Add a negative lookbehind to exclude `::` casts:
```python
sql = re.sub(r"(?<!:):([a-zA-Z_]\w*)", r"%(\1)s", sql)
```
Verified this fix preserves `::TIMESTAMPTZ`, `::DATE`, `::TEXT` while still converting `:ride_date` to `%(ride_date)s`.

## Detailed Audit

### Check 1: `_adapt_sql` Showstopper
* **Status:** FAILED
* **Evidence:** `server/database.py` line 41, regex `r":([a-zA-Z_]\w*)"` matches `::TIMESTAMPTZ`, `::DATE`, `::TEXT`
* **Dynamic Check:** `pytest tests/unit/ -v` -- 1 failure in `test_agent_tool_wiring.py::test_coach_system_prompt_includes_nutrition_section` with `TypeError: tuple indices must be integers or slices, not str`
* **Impact:** All ~40 `AT TIME ZONE` queries across 12 files will crash at runtime

### Check 2: Zero `rides.date` in Active Queries
* **Status:** PASS
* **Evidence:** `grep` for `rides.date` / `r.date` returns only 2 hits, both in TODO comments:
  - `server/ingest.py:40` -- docstring for `_start_time_to_date` helper
  - `server/services/sync.py:419` -- TODO Phase 3 comment about fingerprint
* **Notes:** All active WHERE/SELECT/ORDER clauses use `start_time::TIMESTAMPTZ AT TIME ZONE` pattern

### Check 3: Zero Naive `datetime.now()` / `date.today()`
* **Status:** PASS
* **Evidence:** `grep -rn "datetime.now()" server/` returns 0 results. `grep -rn "date.today()" server/` returns 0 results.

### Check 4: No File Conflicts Between Engineers
* **Status:** PASS
* **Evidence:** `git diff --stat` shows 14 server/test files modified. Cross-referencing engineer assignments:
  - Engineer A files: `routers/rides.py`, `routers/analysis.py`, `routers/planning.py`, `routers/sync.py` -- no overlap
  - Engineer B files: `coaching/tools.py`, `nutrition/agent.py`, `nutrition/tools.py` -- no overlap
  - Engineer C files: `database.py`, `ingest.py`, `services/sync.py`, `services/single_sync.py`, `services/weight.py`, `services/withings.py` -- no overlap
* **Notes:** `server/database.py` was only touched by Engineer C (the `set_athlete_setting` change, not the `_adapt_sql` regex -- that regex is pre-existing)

### Check 5: Test Suite Health
* **Status:** PARTIAL (275 passed, 1 failed)
* **Dynamic Check:** `pytest tests/unit/ -v` = 275 passed, 1 failed
* **Failed test:** `test_coach_system_prompt_includes_nutrition_section` -- fails due to the `_adapt_sql` bug, not due to engineer error. This test exercises a code path that hits the DB with an `AT TIME ZONE` query.
* **Notes:** The 275 passing tests include new tests: `test_nutrition_tools.py` (Engineer B), `test_withings.py` additions (Engineer C), `test_weight_service.py` updates (Engineer C)

### Check 6: Router `tz` Dependency Coverage
* **Status:** PASS
* **Evidence:** Every ride-querying endpoint has `tz: ZoneInfo = Depends(get_client_tz)`:
  - `rides.py`: `list_rides` (L32), `daily_summary` (L97), `weekly_summary` (L119), `monthly_summary` (L181), `get_ride` (L213), `delete_ride` (L267)
  - `analysis.py`: `zone_distribution` (L59), `efficiency_factor` (L121), `route_matches` (L219)
  - `planning.py`: `get_activity_dates` (L32), `get_week_plan` (L61), `get_week_plans_batch` (L83), `weekly_overview` (L109), `plan_compliance` (L209)

## Anti-Shortcut & Quality Scan
* **Placeholders/TODOs:** 5 found, all legitimate Phase 3 deferral markers:
  - `server/ingest.py:68` -- Phase 3 TODO for `get_benchmark_for_date`
  - `server/ingest.py:338` -- Phase 3 TODO for `backfill_hr_tss`
  - `server/services/single_sync.py:39,144` -- Phase 3 TODOs for target_date and power_bests
  - `server/services/sync.py:419,595` -- Phase 3 TODOs for fingerprint and power_bests
* **Test Integrity:** Tests are genuine. New tests in `test_nutrition_tools.py` (132 lines) mock DB calls and verify actual timezone-aware behavior. No skipped/gutted tests found.

## Conclusion

**FAIL** -- The `_adapt_sql` regex in `server/database.py` line 41 is a pre-existing bug that becomes a showstopper now that `::TIMESTAMPTZ`, `::DATE`, and `::TEXT` casts are used in ~40 queries. Every AT TIME ZONE query will crash at runtime.

**Required fix (1 line):**
```
server/database.py line 41:
- sql = re.sub(r":([a-zA-Z_]\w*)", r"%(\1)s", sql)
+ sql = re.sub(r"(?<!:):([a-zA-Z_]\w*)", r"%(\1)s", sql)
```

After this fix, re-run `pytest tests/unit/ -v` to confirm 276/276 pass.
