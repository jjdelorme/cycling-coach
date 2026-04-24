# Plan Validation Report: Campaign 23 — Data Migrations Framework

## Summary
*   **Overall Status:** PASS
*   **Completion Rate:** 17/17 actionable checklist items verified (1 explicitly deferred per plan policy)
*   **Branch / worktree:** `feat/data-migrations-framework` at `.claude/worktrees/data-migrations` (based on `main@6c7c6fb` = v1.13.2)

## Detailed Audit (Evidence-Based)

### Phase 1: Build the runner

#### 1.A — `data_migrations/` package
*   **Status:** Verified
*   **Evidence:** `data_migrations/__init__.py` exists (empty file, 1 line). `data_migrations/0001_backfill_ride_start_geo.py` is the first migration. Directory listed as untracked in git.
*   **Notes:** Empty `__init__.py` is fine — runner uses `importlib.util.spec_from_file_location` not package imports, so no side-effects matter.

#### 1.B — `server/data_migrate.py` mirroring `server/migrate.py`
*   **Status:** Verified
*   **Evidence:** Side-by-side comparison of `server/data_migrate.py` and `server/migrate.py`:
    - Same `CREATE TABLE IF NOT EXISTS` bootstrap pattern (lines 36–45 vs 26–34).
    - Same applied-set query, same sorted-glob iteration, same `INSERT INTO ... VALUES` pattern (line 73 vs 55).
    - Same `print(... , flush=True)` logging style.
    - Same `_DEFAULT_URL` constant and `if __name__ == "__main__"` shape.
    - Same `dotenv` lazy-import for env loading.
    - Adds `result JSONB` column on the tracking table (per plan).
*   **Dynamic Check:** Hard-fails on missing `run` (line 66) and on `run()` raising — verified by `test_missing_run_function_raises` and `test_run_failure_propagates_and_does_not_record`. Inserts happen **after** successful `run()` so partial-fail leaves no row, allowing retry.
*   **Notes:** `migrations_dir` is parameterized for testability — clean.

#### 1.C — CLI entry `python -m server.data_migrate`
*   **Status:** Verified
*   **Evidence:** `if __name__ == "__main__"` at line 88. Reads `CYCLING_COACH_DATABASE_URL` with the same default URL constant as `server/migrate.py`.
*   **Dynamic Check:**
    ```
    INTERVALS_ICU_DISABLED=1 CYCLING_COACH_DATABASE_URL="postgresql://postgres@localhost:5433/coach_test" python3 -m server.data_migrate
    First run: "Applying 0001_backfill_ride_start_geo.py ..." → "Done: ... -> {'skipped': True, 'reason': 'icu_disabled'}" → "Data migrations applied: 1"
    Second run: "No pending data migrations." → "Data migrations applied: 0"
    ```
    Re-verified DB state: `data_migrations` row persisted with JSONB result `{"reason": "icu_disabled", "skipped": true}`.

#### 1.D — Wired into `server/main.py` lifespan
*   **Status:** Verified (with sanctioned scope-clarification)
*   **Evidence:** `server/main.py:62–72`: lifespan calls `run_data_migrations()` inside a try/except that logs but does not raise. Engineer's deviation note is correct: `grep -n "run_migrations" server/main.py` returns only the comment reference at line 60 — `run_migrations()` is **not** called at startup. Plan's claim about `run_migrations()` being in startup was simply wrong; engineer rightly chose not to expand scope by also wiring SQL migrations into startup.
*   **Notes:** Resilient try/except is appropriate for boot — production runs migrations explicitly via Cloud Build before traffic flips. This is consistent with the deferred runtime-resilience pattern.

#### 1.E — Unit tests for runner contract
*   **Status:** Verified
*   **Evidence:** `tests/unit/test_data_migrate.py` — 8 tests covering: no-pending zero return, filename ordering, skip-already-applied, dunder-file exclusion, missing-`run` raises, run-failure propagates without recording, checksum + JSONB result persisted, None-result stored as NULL.
*   **Dynamic Check:** `pytest tests/unit/test_data_migrate.py -v` → **8 passed**.

#### 1.F — Integration test against real Postgres
*   **Status:** Verified
*   **Evidence:** `tests/integration/test_data_migrate.py` uses bare `psycopg2` (matches runner's connection model), self-cleaning `ittest_*` prefix prevents pollution of the tmpfs DB across runs. Covers: ordered apply, idempotent re-run, JSONB persistence, failure-not-recorded.
*   **Dynamic Check:** **4/4 pass** (see Build & Test Results).

### Phase 2: Migrate the geo backfill

#### 2.A — `data_migrations/0001_backfill_ride_start_geo.py` exports `run(conn) -> dict`
*   **Status:** Verified
*   **Evidence:** Line 37: `def run(conn, *, sleep_seconds: float = 0.5) -> dict:`. Returns counts dict (line 126) with `total/backfilled/no_streams/no_gps_in_streams/already_populated/errors`.
*   **Notes:** Optional `sleep_seconds` keyword arg is a clean test seam (used by `test_data_migration_0001_geo.py` to set 0.0).

#### 2.B — Inlined logic; argparse machinery dropped
*   **Status:** Verified
*   **Evidence:** No `argparse`, no `--allow-remote`, no `--dry-run` in the migration module. Direct calls to `sync_module.fetch_activity_streams` and `_backfill_start_location` (verified to exist at `server/services/sync.py:357` and re-exported at line 23).

#### 2.C — Honors both `INTERVALS_ICU_DISABLED` and `INTERVALS_ICU_DISABLE`
*   **Status:** Verified (engineer-flagged spelling concern resolved)
*   **Evidence:** `_icu_disabled()` function (lines 29–34) iterates over both env-var names and returns True for `1/true/yes`. The existing `server/config.py:24` constant `INTERVALS_ICU_DISABLED` is itself sourced from env `INTERVALS_ICU_DISABLE` (singular) — so historically the codebase has had a Python-name vs env-name asymmetry. Honoring both spellings in the migration is a robust accommodation.
*   **Dynamic Check:** Independently verified BOTH spellings work end-to-end against the test DB:
    - `INTERVALS_ICU_DISABLED=1` → applies, records `{"skipped": true, "reason": "icu_disabled"}`.
    - `INTERVALS_ICU_DISABLE=1` → applies, records `{"skipped": true, "reason": "icu_disabled"}`.

#### 2.D — Old script + tests deleted
*   **Status:** Verified
*   **Evidence:** `git status` shows `deleted: scripts/backfill_ride_start_geo.py`, `deleted: tests/integration/test_backfill_ride_start_geo.py`, `deleted: tests/unit/test_backfill_ride_start_geo.py`. `ls scripts/ | grep backfill_ride` returns nothing.

#### 2.E — Roadmap updated
*   **Status:** Verified
*   **Evidence:** `git diff plans/00_MASTER_ROADMAP.md` shows the "Pending operator action" line replaced with: "GPS backfill now auto-applies via Campaign 23's data-migration framework... no operator follow-up required."

#### 2.F — Integration test for migration 0001
*   **Status:** Verified
*   **Evidence:** `tests/integration/test_data_migration_0001_geo.py` — 3 tests covering happy-path backfill (ride A populated, ride B left null, ride C untouched), idempotence (second run leaves state unchanged), ICU-disabled short-circuit returns `{"skipped": True, "reason": "icu_disabled"}`. Stream HTTP layer monkey-patched — no network. Self-cleaning teardown deletes only fixture rows by filename.
*   **Dynamic Check:** **3/3 pass**.

### Phase 3: Cloud Build

#### 3.A — `cloudbuild.yaml` merged step
*   **Status:** Verified
*   **Evidence:** `cloudbuild.yaml:50–94`: single step `id: 'migrate'` with `timeout: '1200s'`, single Cloud SQL Proxy lifecycle (start → wait socket → run → kill). The `docker run` invocation now uses `bash -c "python -m server.migrate && python -m server.data_migrate"` (line 89). `secretEnv: ['CYCLING_COACH_DATABASE_URL']` unchanged. Header comment explains the merge rationale.
*   **Notes:** Structurally identical to the pre-existing migrate step shape — same proxy URL, same socket path `/workspace/cloudsql/$$CLOUD_SQL_INSTANCE/.s.PGSQL.5432`, same exit-code propagation.

#### 3.B — `cloudbuild-test.yaml` mirror
*   **Status:** Verified
*   **Evidence:** `cloudbuild-test.yaml:50–94` is byte-for-byte equivalent to the prod `migrate` step (modulo the surrounding deploy step using `--tag test --no-traffic` and `CYCLING_COACH_DATABASE_URL_TEST`). Diff shows only the merged-command and updated comments.

#### 3.C — Secret bindings unchanged
*   **Status:** Verified
*   **Evidence:** `availableSecrets` in both files unchanged from baseline. ICU credentials live in the `athlete_settings` DB table (per plan), accessible once the Cloud SQL Proxy is up — no new Secret Manager bindings required.

### Phase 4: Documentation

#### 4.A — `AGENTS.md` "Data Migrations" subsection
*   **Status:** Verified
*   **Evidence:** `git diff AGENTS.md` shows a new ~30-line "Data Migrations" subsection inserted directly after "Database Migrations". Mirrors the source subsection's structure: How it works / Adding / Conventions / When NOT to use. Calls out the merged Cloud Build step, the lifespan resilience semantics, the JSONB result column, and the `INTERVALS_ICU_DISABLED`/`INTERVALS_ICU_DISABLE` parity.
*   **Notes:** "When NOT to use" guidance is exactly the differentiator a future contributor needs.

#### 4.B — Add Campaign 23 to Archived
*   **Status:** Deferred (per plan policy)
*   **Evidence:** Plan explicitly defers this to release-time. Not a regression.

## Anti-Shortcut & Quality Scan

*   **Placeholders / TODOs / FIXMEs / HACK markers:** **None found.** `grep -rn "TODO\|FIXME\|HACK\|XXX"` across all new/modified files returned zero hits.
*   **Test integrity:** **Robust.** No skipped tests, no commented-out tests, no `xfail`. Both new integration test files tear down their own fixtures by prefix/filename rather than truncating, so they're safe against a shared tmpfs DB. Stream layer is monkey-patched — no real network calls in tests.
*   **No fake implementations:** The runner genuinely loads modules dynamically, calls `run()`, persists JSONB results, and propagates errors. The migration genuinely walks `start_lat IS NULL` rides and calls the existing production `_backfill_start_location` helper.
*   **No new dependencies:** `git diff requirements.txt` is empty.
*   **No frontend touches:** Backend-only campaign — verified.
*   **Print vs logger:** `server/data_migrate.py` uses `print(... flush=True)` matching `server/migrate.py`'s convention exactly. The migration module uses `logging` for forensic detail. Both choices match the existing pattern.

## Build & Test Results

| Suite | Command | Result |
|---|---|---|
| Unit (full) | `python3 -m pytest tests/unit/ -q` | **387 passed**, 2 warnings, 9.91s |
| Unit (new only) | `pytest tests/unit/test_data_migrate.py -v` | **8 passed**, 0.06s |
| Integration (new only) | `CYCLING_COACH_DATABASE_URL=... pytest tests/integration/test_data_migrate.py tests/integration/test_data_migration_0001_geo.py -v` | **7 passed**, 1.73s |
| CLI (apply path) | `INTERVALS_ICU_DISABLED=1 python3 -m server.data_migrate` | "Applying ..." → "Done: ... -> {'skipped': True, 'reason': 'icu_disabled'}" → "Data migrations applied: 1" |
| CLI (no-op path) | `python3 -m server.data_migrate` (after first run) | "No pending data migrations." → "Data migrations applied: 0" |
| CLI (singular spelling) | `INTERVALS_ICU_DISABLE=1 python3 -m server.data_migrate` | Records `{"skipped": true, "reason": "icu_disabled"}` |

**Math check on the 387 unit count:** main worktree baseline today shows 390 unit tests. Worktree drops 11 (deleted backfill tests across unit) but adds 8 (new `test_data_migrate.py`). 390 − 11 + 8 = 387. Engineer's stated baseline of 398 is off by 8 in absolute terms, but the delta arithmetic (−11 + 8 = −3) is internally consistent and the final 387 matches reality. Minor reporting nit, not a substantive issue.

**Pre-existing failures ignored** per audit instructions: known coach_test schema drift in `test_meal_plan.py`, `test_nutrition_api.py`, `test_timezone_queries.py`, `test_withings_integration.py`. Not regressions from this campaign.

## Engineer-Deviation Assessment

1.  **`run_migrations()` not in `server/main.py` lifespan.** ✅ Sound. Independently confirmed by reading `server/main.py` — only `run_data_migrations()` is wired in. Plan's prior claim was incorrect. Engineer correctly resisted scope creep; expanding SQL-migration auto-apply on boot would have been a separate (and arguably riskier) change.
2.  **`INTERVALS_ICU_DISABLED` vs `INTERVALS_ICU_DISABLE` spelling.** ✅ Sound. The repo's historical Python const is `INTERVALS_ICU_DISABLED` but the env-var name is `INTERVALS_ICU_DISABLE` (`server/config.py:24`). Honoring both in the migration is a strict superset of correct behavior. Verified both spellings work end-to-end. Resolved — no concern.
3.  **Merged Cloud Build step.** ✅ Sound. The merged step is structurally consistent with the pre-existing migrate step (same proxy lifecycle, same socket path, same secretEnv binding, `timeout: '1200s'`). Single proxy = no second startup race, no second container pull. The merged shape is the plan's explicitly endorsed "cleaner refactor" path.

## Findings

*   None blocking. All success criteria from the plan are met.
*   Cosmetic / reporting nit: engineer's stated baseline of 398 unit tests is 8 high vs the actual 390 baseline I measured at `main`. Final count of 387 still matches expectations. Worth noting in the merge commit / release-notes if precision matters; not a code defect.

## Conclusion

Campaign 23 is implementation-complete, tested, idempotent, and structurally consistent with the existing schema-migration pattern. The runner contract is enforced; the geo migration is correctly ported; Cloud Build wiring matches the plan's preferred merged shape; documentation lands the pattern in the right place in `AGENTS.md`. All three engineer-flagged deviations hold up under independent verification.

**Recommendation:**
*   ✅ **Commit** — green light. The worktree is in a clean, reviewable state.
*   ✅ **Merge to `main`** — green light, pending explicit user approval per project safety mandate.
*   ✅ **Deploy via `/release`** — green light. The first prod run of `data_migrations/0001_backfill_ride_start_geo.py` will execute the long-pending GPS backfill automatically. Watch the Cloud Build log for the `migrate` step to confirm the expected `Done: 0001_backfill_ride_start_geo.py -> {...}` line, since this is the first build to make outbound HTTPS calls to intervals.icu.
