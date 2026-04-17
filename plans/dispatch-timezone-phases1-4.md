# Dispatch Brief: Timezone Awareness Phases 1-4

**Date:** 2026-04-14
**Branch:** `worktree-fix-timezone-awareness`
**Plans:** `plans/timezone-awareness.md` (research), `plans/impl-timezone-awareness.md` (implementation)

---

## 1. Status Assessment

**Phase 0 -- COMPLETE.** All items verified in the codebase:

| Item | Status | Evidence |
|------|--------|----------|
| `server/utils/dates.py` uses `ContextVar` | DONE | Confirmed: `ContextVar("request_tz")` at line 13 |
| `ClientTimezoneMiddleware` as raw ASGI | DONE | `server/main.py:177-215` -- raw `__call__(self, scope, receive, send)`, NOT `BaseHTTPMiddleware` |
| Frontend `X-Client-Timezone` header | DONE | |
| Coaching/nutrition tools use `user_today()` | DONE | |
| Frontend `toISOString()` fixes | DONE | |
| `_get_athlete_tz()` in sync.py returns UTC | DONE | `server/services/sync.py:47-59` |
| `athlete_settings.timezone` persistence removed | DONE | Zero grep results for `athlete_setting.*timezone` |
| intervals.icu uses UTC `start_date` | DONE | `server/services/intervals_icu.py:304-312` |
| `_utc_to_local_date` removed from ingest | DONE | Replaced with `_start_time_to_date` (line 39) |
| intervals_icu.py `datetime.now()` fixed | DONE | Zero matches |
| planning.py `datetime.now()` fixed | DONE | Zero matches |

**Step 0.G (BaseHTTPMiddleware bug) -- CLOSED.** The middleware was already rewritten as raw ASGI. No action needed.

**Remaining naive `datetime.now()` calls outside Phase 0 scope (4 total):**

| File | Line | Context | Fix Phase |
|------|------|---------|-----------|
| `server/coaching/tools.py` | 781 | `get_daily_nutrition_summary()` fallback date | Phase 2 (query rewrite pass) |
| `server/database.py` | 246 | `set_athlete_setting()` date_set default | Phase 2 |
| `server/services/withings.py` | 156-157 | `sync_weight()` API fetch window | Phase 1 (similar to sync.py -- UTC acceptable for API bounds) |
| `server/services/weight.py` | 71 | `get_current_weight()` uses `date.today()` | Phase 2 |

**Phases 1-4 -- ALL PENDING.** No query rewrites, no schema migration, no PMC rebuild have been started.

---

## 2. Phase Ordering

The sequential ordering (1 -> 2 -> 3 -> 4) is correct and necessary:

- **Phase 1 before Phase 2:** The `AT TIME ZONE` query pattern requires `start_time` to be uniformly UTC. Phase 1 normalizes the data source. Most of Phase 1 is already done (intervals_icu, ingest, sync.py). Only the withings.py calls and a few stragglers remain.
- **Phase 2 before Phase 3:** All `rides.date` query references must be rewritten before the column is dropped.
- **Phase 3 before Phase 4:** Schema must be migrated before PMC rebuild uses the new types.

**Parallelism within phases:**
- Phase 1 steps are independent -- all can run in parallel.
- Phase 2 steps are independent (each file's queries are self-contained) -- all can run in parallel. This is the biggest win: Steps 2.A through 2.I can be split across engineers.
- Phase 3 steps are mostly sequential (migration first, then code fixes).

---

## 3. Risk Assessment -- Phase 1

**Risk:** LOW. Phase 1 is largely already done. The remaining work is 4 `datetime.now()` fixes.

**Rollback strategy:** Phase 1 changes are backward-compatible. The `rides.date` column still exists and is still written (with `_start_time_to_date`). If `start_time` storage breaks, the old `date` column is still there as a fallback. No schema changes in Phase 1.

---

## 4. Risk Assessment -- Phase 3 (Schema Migration)

**Risk:** HIGH. Dropping `rides.date` is irreversible. Promoting TEXT to TIMESTAMPTZ is destructive if any values fail to parse.

**Required safeguards:**
1. **Pre-migration data audit:** Run `SELECT COUNT(*) FROM rides WHERE start_time NOT LIKE '%Z' AND start_time NOT LIKE '%+%' AND LENGTH(start_time) > 10` to count non-UTC timestamps. These need the `+00:00` append step before the TIMESTAMPTZ cast.
2. **Migration must go through `migrations/` system** (not a standalone script). Create `migrations/NNNN_timezone_schema.sql` and apply via `python -m server.migrate`. The impl plan proposes a standalone script -- this violates the project's migration conventions.
3. **Backup before deploy:** `pg_dump` the production database before the tag push that includes this migration.
4. **Test against a clone:** Run the migration against a copy of production data before deploying.
5. **Phase 2 must be 100% verified** before Phase 3 deploys. No `rides.date` references may remain in query paths.

---

## 5. Scope Recommendation

**Split into 3 PRs, not 1.**

| PR | Content | Risk | Independently deployable? |
|----|---------|------|--------------------------|
| **PR 1** | Phase 1 (remaining `datetime.now()` fixes) + Phase 2 (all query rewrites) | Medium | YES -- `rides.date` still exists, old queries gone, new queries work with existing TEXT `start_time` via `::TIMESTAMPTZ` cast |
| **PR 2** | Phase 3 (schema migration + SUBSTR fixes + Python type handling) | High | YES -- but only after PR 1 is deployed and verified |
| **PR 3** | Phase 4 (PMC rebuild + smoke test) | Low | YES -- operational step after schema is stable |

**Rationale:** PR 1 is the bulk of the work (~12 files, ~30 query rewrites) but is non-destructive. PR 2 is the irreversible schema change -- it deserves its own deploy cycle with a production backup. PR 3 is operational cleanup.

The nutrition module (`nutrition/agent.py`, `nutrition/tools.py`, `nutrition/planning_tools.py`) has `rides WHERE date = %s` queries that the impl plan does NOT cover. These must be added to Phase 2.

---

## 6. Open Decisions

| Decision | Location | Recommendation |
|----------|----------|----------------|
| **D1: Is intervals.icu `start_date` truly UTC?** | Step 1.A | CLOSED -- code already treats it as UTC with fallback (line 312). The comment at line 305 confirms Strava convention. Verify empirically with one API call during Phase 1 testing. |
| **D2: Historical non-UTC `start_time` values** | Step 2 preamble | Recommend option (A): write a one-time data fix in the Phase 3 migration SQL that appends `+00:00` to non-UTC timestamps before the TIMESTAMPTZ cast. The impl plan already includes this SQL. |
| **D3: `user_today()` return type** | Step 3.D | Keep returning `str`. Converting to `datetime.date` touches too many callers for marginal benefit. Explicitly call `.isoformat()` on DATE column results where needed. |
| **D4: PMC end date in background jobs** | Step 2.G | Accept UTC for background jobs. For request-triggered PMC recomputation (delete_ride), pass the user's timezone. |
| **D5: Phase 3E (multi-athlete `user_id`)** | Step 3.E | DEFER to a separate work item as already decided in the peer review. Remove from this branch entirely. It is not timezone-related and adds scope risk. |

---

## 7. Dispatch Instructions

### What to implement next

**Phase 1 remainder first** (30 minutes of work), then immediately into **Phase 2** (the main effort). Phase 1 is nearly complete -- only 4 naive datetime calls remain.

### Work split for engineer agents

**Engineer A -- Query Rewrites (request-context files):**
- Step 2.B: `server/routers/rides.py` (6 query changes)
- Step 2.C: `server/routers/analysis.py` (4 query changes)
- Step 2.B2: `server/routers/planning.py` (rides.date references)
- Step 2.H2: `server/routers/sync.py`

**Engineer B -- Query Rewrites (coaching + service files):**
- Step 2.A: `server/queries.py`
- Step 2.D: `server/coaching/tools.py` (including the `datetime.now()` on line 781)
- Step 2.E: `server/coaching/planning_tools.py`
- Step 2.F: `server/coaching/agent.py`
- **NEW:** `server/nutrition/agent.py`, `server/nutrition/tools.py` -- rides.date queries not in the impl plan

**Engineer C -- Data pipeline + tests:**
- Phase 1 stragglers: `server/database.py:246`, `server/services/withings.py:156-157`, `server/services/weight.py:71`
- Step 2.G: `server/ingest.py` (compute_daily_pmc signature change)
- Step 2.H: `server/services/sync.py`
- Step 2.I: `server/services/single_sync.py`
- Step 2.J: Integration tests
- Step 1.F/1.G: Unit tests for Phase 1 changes

### Auditor verification checklist (after Phase 2)

1. `grep -rn "datetime\.now()" server/` -- zero results without explicit timezone arg
2. `grep -rn "date\.today()" server/` -- zero results
3. `grep -rn "FROM rides.*WHERE.*[^_]date " server/` -- zero results referencing `rides.date` in WHERE clauses (planned_workouts.date, meal_logs.date, daily_metrics.date are acceptable)
4. All 88+ unit tests pass: `pytest tests/unit/ -v`
5. Integration tests pass: `./scripts/run_integration_tests.sh`
6. Frontend builds: `cd frontend && npm run build`
7. Every router endpoint that filters rides accepts `tz: ZoneInfo = Depends(get_client_tz)` and passes it to queries
