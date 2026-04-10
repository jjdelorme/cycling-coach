# Feature Implementation Plan: fix-timezone-awareness

> ⚠️ **Note for Phase 1+ executor:** The checklist below is accurate. However, the step-by-step implementation details in Phases 1–4 were drafted against a simplified view of the codebase and do not match the real files. Before executing any Phase 1+ step, read the actual target file first. Key divergences: `server/queries.py` does not contain `get_pmc_data()` or `get_upcoming_workouts()` — the real PMC data comes from `daily_metrics` via `get_current_pmc_row()`; `server/ingest.py` is 700+ lines with timezone logic in `parse_ride_json()` (reads `athlete_settings WHERE key='timezone'`). Treat the step descriptions as intent, not copy-paste instructions.

## 🔍 Analysis & Context

- **Objective:** Complete the timezone-awareness fix by finishing Phase 0 (unit tests + frontend date fixes), then execute Phases 1–4 (switch queries to `start_date_local`, drop `rides.date`, add `user_id` to PMC, rebuild).
- **Affected Files:**
  - `tests/unit/test_dates.py` (create)
  - `tests/integration/test_queries.py` (create)
  - `frontend/src/pages/Dashboard.tsx` (fix `toISOString` calls)
  - `frontend/src/pages/Analysis.tsx` (fix `toISOString` calls)
  - `server/queries.py` (switch to `start_date_local`, add `user_id`)
  - `server/routers/analysis.py` (pass `user_today()` and `user_id`)
  - `server/ingest.py` (stop writing `rides.date`, remove `_utc_to_local_date`)
  - `server/database.py` (remove `date DATE` from `init_db()` schema)
- **Key Dependencies:** `pytz` (already in requirements.txt), `psycopg2`, `contextvars` (stdlib), React `Intl.DateTimeFormat` API (universally available in modern browsers)
- **Risks/Edge Cases:**
  - `get_upcoming_workouts` currently uses `CURRENT_DATE` (PostgreSQL UTC clock). After the fix it must receive `user_today()` as a bound parameter — failing to pass the parameter will silently revert to UTC.
  - `get_pmc_data` has no `user_id` filter today. Phase 3 adds one.
  - `rides.date` may hold NULL for rides ingested between Step 1.E and Phase 2 migration. The DROP is safe because application code will have stopped reading it.
  - `toLocaleDateString` relies on `Date.getFullYear()/getMonth()/getDate()` — these use browser local timezone, which is always correct.

---

## 📋 Audit — What Is Already Done

The following Phase 0 items are **complete** in this worktree. The Engineer must NOT re-implement them:

| Item | File | Status |
|------|------|--------|
| `server/utils/dates.py` uses `ContextVar` | `server/utils/dates.py` | ✅ DONE |
| `ClientTimezoneMiddleware` in `server/main.py` | `server/main.py` | ✅ DONE |
| `server/dependencies.py` with `get_client_tz()` | `server/dependencies.py` | ✅ DONE |
| `authHeaders()` sends `X-Client-Timezone` | `frontend/src/lib/api.ts` | ✅ DONE |
| `server/coaching/agent.py` uses `user_today()` | `server/coaching/agent.py` | ✅ DONE |
| `server/coaching/tools.py` uses `user_today()` | `server/coaching/tools.py` | ✅ DONE |
| `server/nutrition/agent.py` uses `user_today()` | `server/nutrition/agent.py` | ✅ DONE |
| `server/nutrition/tools.py` uses `user_today()` | `server/nutrition/tools.py` | ✅ DONE |
| `server/nutrition/planning_tools.py` uses `user_today()` | `server/nutrition/planning_tools.py` | ✅ DONE |
| `server/routers/settings.py` strips `timezone` key | `server/routers/settings.py` | ✅ DONE |

---

## 📋 Micro-Step Checklist

- [x] Phase 0 Fixes (remaining items)
  - [x] Step 0.A: Write unit tests for `server/utils/dates.py` (7 tests in tests/unit/test_dates.py)
  - [x] Step 0.B: Run unit tests — 88/88 passed (no regressions)
  - [x] Step 0.C: Fix `toISOString()` in `frontend/src/pages/Dashboard.tsx` (done in checkpoint commit)
  - [x] Step 0.D: Fix `toISOString()` in `frontend/src/pages/Analysis.tsx` (done in checkpoint commit)
  - [x] Step 0.E: Fix `server/utils/dates.py` — replaced threading.local with ContextVar
  - [x] Step 0.F: Update ClientTimezoneMiddleware to call set_request_tz() (ContextVar now set on every request)
- [ ] Phase 1: Remove `rides.date` from application queries
  - [ ] Step 1.A: Write integration tests for `get_pmc_data` and `get_upcoming_workouts`
  - [ ] Step 1.B: Rewrite `get_pmc_data` — use `start_date_local`, accept `user_id`
  - [ ] Step 1.C: Rewrite `get_upcoming_workouts` — use `start_date_local`, accept `today: date`
  - [ ] Step 1.D: Update `server/routers/analysis.py` to pass `user_today()` and `user_id`
  - [ ] Step 1.E: Stop writing `rides.date` in `server/ingest.py`; remove `_utc_to_local_date`
  - [ ] Step 1.F: Run unit tests — verify no regressions
- [ ] Phase 2: Schema migration — drop `rides.date`
  - [ ] Step 2.A: Run migration SQL against local dev DB
  - [ ] Step 2.B: Remove `date DATE` column from `init_db()` in `server/database.py`
  - [ ] Step 2.C: Re-ingest data and verify PMC endpoint responds correctly
- [ ] Phase 3: Multi-athlete PMC `user_id` filter
  - [ ] Step 3.A: Verify `user_id` wired end-to-end (already done via Steps 1.B/1.D); wire auth dependency if present
- [ ] Phase 4: Rebuild PMC
  - [ ] Step 4.A: Full ingest + smoke-test `/analysis/pmc` with `X-Client-Timezone` header

---

## 📝 Step-by-Step Implementation Details

### Phase 0 Fixes: Remaining Items

#### Step 0.A — Create `tests/unit/test_dates.py`

- **Target File:** `tests/unit/test_dates.py` (create new file)
- **Exact content to write:**

```python
from __future__ import annotations
from contextvars import copy_context
from datetime import date

import pytest

from server.utils.dates import _tz_ctx, user_today


def test_user_today_default_utc_returns_date():
    """With no timezone set, user_today() must return a date object (UTC)."""
    ctx = copy_context()
    result = ctx.run(user_today)
    assert isinstance(result, date)


def test_user_today_us_central_returns_date():
    """With America/Chicago set, user_today() must return a date object."""
    def _run():
        _tz_ctx.set("America/Chicago")
        return user_today()

    ctx = copy_context()
    result = ctx.run(_run)
    assert isinstance(result, date)


def test_user_today_context_isolation():
    """Two concurrent contexts must each see their own timezone value."""
    results: dict[str, date] = {}

    def _run_utc():
        _tz_ctx.set("UTC")
        results["utc"] = user_today()

    def _run_chicago():
        _tz_ctx.set("America/Chicago")
        results["chicago"] = user_today()

    copy_context().run(_run_utc)
    copy_context().run(_run_chicago)

    # Both must be valid dates; contextvar isolation ensures they don't bleed
    assert isinstance(results["utc"], date)
    assert isinstance(results["chicago"], date)


def test_tz_ctx_default_is_utc():
    """The ContextVar default must be the string 'UTC'."""
    ctx = copy_context()
    result = ctx.run(_tz_ctx.get)
    assert result == "UTC"
```

#### Step 0.B — Run unit tests

- **Action:** From the worktree root (`/home/workspace/cycling-coach/.claude/worktrees/fix-timezone-awareness/`):
  ```bash
  source venv/bin/activate && pytest tests/unit/test_dates.py -v
  ```
- **Success criterion:** All 4 tests pass, no import errors.

#### Step 0.C — Fix `toISOString()` in `frontend/src/pages/Dashboard.tsx`

- **Target File:** `frontend/src/pages/Dashboard.tsx`
- **Problem:** The `useEffect` block uses `.toISOString().slice(0,10)` which is UTC-anchored.
- **Add this helper function** at the top of the file, before the component declaration:
  ```typescript
  /** Format a Date as YYYY-MM-DD in the browser's local timezone. */
  function toLocalDateString(d: Date): string {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  ```
- **Then replace the offending lines** in `useEffect`:
  ```typescript
  // Before
  api.get(`/analysis/pmc?start=${start.toISOString().slice(0,10)}&end=${end.toISOString().slice(0,10)}`)
  // After
  api.get(`/analysis/pmc?start=${toLocalDateString(start)}&end=${toLocalDateString(end)}`)
  ```

#### Step 0.D — Fix `toISOString()` in `frontend/src/pages/Analysis.tsx`

- **Target File:** `frontend/src/pages/Analysis.tsx`
- **Problem:** The `initialize` callback uses `.toISOString().slice(0, 10)` (UTC-anchored).
- **Add the same `toLocalDateString` helper** at the top of the file (before the component):
  ```typescript
  /** Format a Date as YYYY-MM-DD in the browser's local timezone. */
  function toLocalDateString(d: Date): string {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  ```
- **Replace the offending lines inside `initialize`:**
  ```typescript
  // Before
  setStartDate(start.toISOString().slice(0, 10));
  setEndDate(end.toISOString().slice(0, 10));
  // After
  setStartDate(toLocalDateString(start));
  setEndDate(toLocalDateString(end));
  ```

#### Step 0.E — Verify frontend build

- **Action:** From the worktree root:
  ```bash
  cd frontend && npm run build
  ```
- **Success criterion:** Build exits 0 with no TypeScript errors.

---

### Phase 1: Remove `rides.date` from Application Queries

#### Step 1.A — Write integration tests for `get_pmc_data` and `get_upcoming_workouts`

- **Target File:** `tests/integration/test_queries.py` (create new file)
- **Note:** These tests document the new expected contract (using `start_date_local` and explicit params).

```python
"""
Integration tests for server/queries.py.
Requires the test database (coach-test-db on port 5433).
Run via: ./scripts/run_integration_tests.sh
"""
from __future__ import annotations
from datetime import date

import pytest


def _insert_ride(conn, start_date_local: str, tss: float, user_id: int = 1) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rides (user_id, start_date_local, tss, duration_seconds)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, start_date_local, tss, 3600),
        )
    conn.commit()


def test_get_pmc_data_groups_by_start_date_local(db_conn):
    """get_pmc_data must return rows keyed by start_date_local."""
    from server.queries import get_pmc_data

    _insert_ride(db_conn, "2024-06-15", 80.0, user_id=1)
    _insert_ride(db_conn, "2024-06-16", 60.0, user_id=1)

    rows = get_pmc_data(db_conn, user_id=1)
    dates = [str(r["date"]) for r in rows]
    assert "2024-06-15" in dates


def test_get_pmc_data_filters_by_user_id(db_conn):
    """get_pmc_data must only return rows for the given user_id."""
    from server.queries import get_pmc_data

    _insert_ride(db_conn, "2024-06-15", 80.0, user_id=1)
    _insert_ride(db_conn, "2024-06-15", 90.0, user_id=2)

    rows_user1 = get_pmc_data(db_conn, user_id=1)
    rows_user2 = get_pmc_data(db_conn, user_id=2)

    tss_user1 = sum(r["tss"] for r in rows_user1 if r["tss"] is not None)
    tss_user2 = sum(r["tss"] for r in rows_user2 if r["tss"] is not None)
    # Users' data must differ — same date, different tss values
    assert abs(tss_user1 - tss_user2) > 0


def test_get_upcoming_workouts_uses_today_param(db_conn):
    """get_upcoming_workouts must use the supplied today date, not CURRENT_DATE."""
    from server.queries import get_upcoming_workouts

    _insert_ride(db_conn, "2030-01-01", 50.0, user_id=1)
    _insert_ride(db_conn, "2020-01-01", 50.0, user_id=1)

    # With future today — 2030 ride is in the past
    future_today = date(2030, 12, 31)
    rows = get_upcoming_workouts(db_conn, today=future_today)
    dates = [str(r["start_date_local"]) for r in rows]
    assert "2030-01-01" not in dates
    assert "2020-01-01" not in dates

    # With a past today — 2030 ride is upcoming
    past_today = date(2020, 1, 1)
    rows = get_upcoming_workouts(db_conn, today=past_today)
    dates = [str(r["start_date_local"]) for r in rows]
    assert "2030-01-01" in dates
```

**Note:** This test file requires a `db_conn` fixture. Check `tests/integration/conftest.py` for the fixture definition — use whatever fixture name is defined there.

#### Step 1.B — Rewrite `get_pmc_data` in `server/queries.py`

- **Target File:** `server/queries.py`
- **Replace the entire `get_pmc_data` function** with:

```python
def get_pmc_data(conn, user_id: int) -> list[dict]:
    """
    Fetch PMC data for a single athlete, grouped by start_date_local.
    The `date` key in results maps from start_date_local (preserving downstream compatibility).
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                start_date_local  AS date,
                SUM(tss)          AS tss,
                AVG(ctl)          AS ctl,
                AVG(atl)          AS atl,
                AVG(tsb)          AS tsb
            FROM rides
            WHERE user_id = %s
            GROUP BY start_date_local
            ORDER BY start_date_local
            """,
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]
```

The `AS date` alias preserves the response key that callers (PMC chart) already expect.

#### Step 1.C — Rewrite `get_upcoming_workouts` in `server/queries.py`

- **Target File:** `server/queries.py`
- **Replace the entire `get_upcoming_workouts` function** with:

```python
def get_upcoming_workouts(conn, today: date) -> list[dict]:
    """
    Return planned workouts that are today or in the future.
    `today` must be supplied by the caller (from user_today()) — never use CURRENT_DATE.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT *
            FROM rides
            WHERE start_date_local >= %s
            ORDER BY start_date_local
            """,
            (today,),
        )
        return [dict(r) for r in cur.fetchall()]
```

Ensure `from datetime import date` is at the top of `server/queries.py` (already present per audit).

#### Step 1.D — Update `server/routers/analysis.py`

- **Target File:** `server/routers/analysis.py`
- **Replace the entire file** with:

```python
"""
Analysis router — exposes PMC and ride analysis endpoints.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends

from server.database import get_db
from server.dependencies import get_client_tz
from server.queries import get_pmc_data, get_upcoming_workouts
from server.utils.dates import user_today

router = APIRouter(prefix="/analysis")


@router.get("/pmc")
def pmc(conn=Depends(get_db), _tz: str = Depends(get_client_tz)):
    """
    Return PMC data for the authenticated user.
    user_id is hardcoded to 1 until full auth is wired (Phase 3 prerequisite).
    """
    # TODO: replace hardcoded user_id=1 with user.id from auth dependency
    return get_pmc_data(conn, user_id=1)


@router.get("/upcoming")
def upcoming(conn=Depends(get_db), _tz: str = Depends(get_client_tz)):
    """Return upcoming planned workouts using the client's local today."""
    return get_upcoming_workouts(conn, today=user_today())
```

**Why inject `_tz`:** The `get_client_tz` dependency call ensures the middleware's ContextVar is readable. `user_today()` reads it implicitly. The explicit dependency makes the timezone contract visible.

#### Step 1.E — Stop writing `rides.date` in `server/ingest.py`

- **Target File:** `server/ingest.py`
- **Remove:** The entire `_utc_to_local_date` function.
- **Remove:** The `ride_date` variable and the `date` column from the INSERT.
- **Replace the `ingest_ride` function** with:

```python
def ingest_ride(conn, ride_json: dict) -> None:
    """Ingest a single ride JSON record into the database."""
    session = ride_json.get("session", {})
    start_date_local = session.get("start_date_local")  # already correct local date

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rides (start_date_local, tss, duration_seconds)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                start_date_local,
                session.get("tss"),
                session.get("duration_seconds"),
            ),
        )
    conn.commit()
```

Also remove `from datetime import datetime, timezone` if `datetime` and `timezone` are no longer used anywhere else in the file.

#### Step 1.F — Run unit tests

- **Action:** From the worktree root:
  ```bash
  source venv/bin/activate && pytest tests/unit/ -v
  ```
- **Success criterion:** All unit tests pass (including `test_dates.py`). No import errors.

---

### Phase 2: Schema Migration — Drop `rides.date`

#### Step 2.A — Run the migration SQL against the local dev DB

- **Prerequisite:** Verify `DATABASE_URL` points to localhost (NOT production):
  ```bash
  echo $DATABASE_URL
  ```
- **Action:**
  ```bash
  source venv/bin/activate
  python -c "import os, psycopg2; conn = psycopg2.connect(os.environ['DATABASE_URL']); cur = conn.cursor(); cur.execute('ALTER TABLE rides DROP COLUMN IF EXISTS date'); conn.commit(); print('Done')"
  ```
- **Verify:**
  ```bash
  python -c "import os, psycopg2; conn = psycopg2.connect(os.environ['DATABASE_URL']); cur = conn.cursor(); cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='rides'\"); print([r[0] for r in cur.fetchall()])"
  ```
- **Success criterion:** `date` does not appear in the column list.

#### Step 2.B — Remove `date DATE` column from `init_db()` in `server/database.py`

- **Target File:** `server/database.py`
- **Locate** the `CREATE TABLE IF NOT EXISTS rides` block inside `init_db()`.
- **Remove** this line:
  ```sql
  date             DATE,          -- LEGACY: to be dropped in Phase 2
  ```
- This change only affects fresh schema creation (e.g., the integration test DB), not the already-migrated dev DB.

#### Step 2.C — Re-ingest data and verify the PMC endpoint

- **Action 1:** Run full ingest:
  ```bash
  source venv/bin/activate && python -m server.ingest
  ```
- **Action 2:** Start the backend and test the endpoint:
  ```bash
  uvicorn server.main:app &
  curl -s -H "X-Client-Timezone: America/Chicago" http://localhost:8000/analysis/pmc | python3 -m json.tool | head -20
  ```
- **Success criterion:** Ingest exits 0. PMC response is a non-empty JSON array. Each row has a `date` key with a `YYYY-MM-DD` value.

---

### Phase 3: Multi-Athlete PMC `user_id` Filter

#### Step 3.A — Verify `user_id` is wired end-to-end

After Steps 1.B and 1.D, `get_pmc_data` already accepts `user_id` and the router passes `user_id=1`.

- **Check:** Does `server/routers/auth.py` or `server/auth.py` expose a `get_current_user` dependency?
  - **If yes:** Wire it into the `/pmc` and `/upcoming` endpoints:
    ```python
    from server.auth import get_current_user  # adjust import path as needed

    @router.get("/pmc")
    def pmc(conn=Depends(get_db), user=Depends(get_current_user), _tz: str = Depends(get_client_tz)):
        return get_pmc_data(conn, user_id=user.id)
    ```
  - **If no auth dependency exists:** Leave `user_id=1` and the `# TODO` comment in place.

---

### Phase 4: Rebuild PMC

#### Step 4.A — Full ingest and smoke test

- **Action 1:** Ensure local dev DB is running:
  ```bash
  podman ps | grep coach-db
  ```
  If not running:
  ```bash
  podman run -d --name coach-db -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:16-alpine
  ```
- **Action 2:** Run full ingest:
  ```bash
  source venv/bin/activate && python -m server.ingest
  ```
- **Action 3:** Test the endpoint with timezone header:
  ```bash
  uvicorn server.main:app --reload &
  curl -s -H "X-Client-Timezone: America/Chicago" http://localhost:8000/analysis/pmc | python3 -m json.tool | head -30
  ```
- **Success criteria:**
  - Ingest exits 0.
  - PMC response is a non-empty JSON array.
  - Each row has a `date` key with a `YYYY-MM-DD` value matching `start_date_local`.

---

### 🧪 Global Testing Strategy

**Unit Tests** (`tests/unit/`)
- `tests/unit/test_dates.py` — 4 tests: `_tz_ctx` default, `user_today()` with UTC, with `America/Chicago`, context isolation
- Run: `pytest tests/unit/ -v`

**Integration Tests** (`tests/integration/`)
- `tests/integration/test_queries.py` — 3 tests: `get_pmc_data` groups by `start_date_local`, filters by `user_id`; `get_upcoming_workouts` uses `today` param not `CURRENT_DATE`
- Run: `./scripts/run_integration_tests.sh -v`

**Frontend Build Verification**
- `cd frontend && npm run build` — TypeScript must compile cleanly after the `toISOString` fix

---

## 🎯 Success Criteria

1. `pytest tests/unit/` passes with 0 failures, including the new `test_dates.py` tests.
2. `./scripts/run_integration_tests.sh` passes with 0 failures, including `test_queries.py`.
3. `cd frontend && npm run build` exits 0 with no TypeScript errors.
4. `server/queries.py` contains no reference to `rides.date` — all date grouping and filtering uses `start_date_local`.
5. `server/ingest.py` contains no reference to `rides.date` in any INSERT statement and the `_utc_to_local_date` function has been removed.
6. `server/database.py`'s `init_db()` schema contains no `date DATE` column.
7. `ALTER TABLE rides DROP COLUMN IF EXISTS date` has been applied to the local dev database.
8. A `curl` to `/analysis/pmc` with `X-Client-Timezone: America/Chicago` header returns a valid PMC array where each `date` value matches `start_date_local` in the database.
9. `frontend/src/pages/Dashboard.tsx` and `frontend/src/pages/Analysis.tsx` contain no calls to `.toISOString().slice(0, 10)` for date window computation.
