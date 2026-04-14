# Feature Implementation Plan: Fix Nutrition Timezone Awareness

## Analysis & Context

- **Objective:** Replace all naive `datetime.now()` calls in the nutrition subsystem with timezone-aware equivalents using `get_request_tz()` and `user_today()` from `server/utils/dates.py`, matching the pattern already established in `server/coaching/agent.py` and `server/coaching/tools.py`.

- **Affected Files:**
  1. `server/nutrition/agent.py` (1 fix)
  2. `server/nutrition/tools.py` (7 fixes)
  3. `server/routers/nutrition.py` (2 fixes)
  4. `server/nutrition/planning_tools.py` (1 fix)
  5. `server/nutrition/photo.py` (1 fix)
  6. `tests/unit/test_nutrition_tools.py` (new test cases)

- **Key Dependencies:** `server/utils/dates.py` (`get_request_tz`, `user_today`, `set_request_tz`) -- already implemented and tested in `tests/unit/test_dates.py`. The `ClientTimezoneMiddleware` in `server/main.py` (line 177-219) sets the ContextVar on every HTTP request.

- **Risks/Edge Cases:**
  - Agent tools are called by the ADK framework, which may spawn tasks in a different contextvars context. However, the coaching tools already use `get_request_tz()` successfully (see `server/coaching/tools.py:6,28,154,198,254,306,605,704`), so this is a proven pattern.
  - The `save_meal_analysis` function in `planning_tools.py` uses `datetime.now(timezone.utc)` for `logged_at` (the ISO timestamp). That is correct -- timestamps should be UTC. Only the `date` field (the user-facing calendar date) needs to use `user_today()`.
  - `photo.py` uses `datetime.now()` for building a GCS blob path. This is cosmetic but should use UTC for consistency (file paths are not user-facing).

## Micro-Step Checklist

- [x] Phase 1: Fix `server/nutrition/tools.py` (7 instances -- highest impact, agent tools)
  - [x] Step 1.A: Add import for `get_request_tz` and `user_today` (Status: Implemented)
  - [x] Step 1.B: Fix `get_meal_history` (Status: Implemented)
  - [x] Step 1.C: Fix `get_daily_macros` (Status: Implemented)
  - [x] Step 1.D: Fix `get_weekly_summary` (Status: Implemented)
  - [x] Step 1.E: Fix `get_caloric_balance` (Status: Implemented)
  - [x] Step 1.F: Fix `get_upcoming_training_load` (Status: Implemented)
  - [x] Step 1.G: Fix `get_recent_workouts` (Status: Implemented)
  - [x] Step 1.H: Fix `get_planned_meals` (Status: Implemented)
- [x] Phase 2: Fix `server/nutrition/agent.py` (1 instance -- system instruction)
  - [x] Step 2.A: Fix `_build_system_instruction` (Status: Implemented)
- [x] Phase 3: Fix `server/routers/nutrition.py` (2 instances -- REST endpoints)
  - [x] Step 3.A: Fix `daily_summary` (Status: Implemented)
  - [x] Step 3.B: Fix `get_meal_plan` (Status: Implemented)
- [x] Phase 4: Fix `server/nutrition/planning_tools.py` (1 instance -- date field)
  - [x] Step 4.A: Fix `save_meal_analysis` (Status: Implemented)
- [x] Phase 5: Fix `server/nutrition/photo.py` (1 instance -- GCS path)
  - [x] Step 5.A: Fix `upload_meal_photo` (Status: Implemented)
- [x] Phase 6: Add unit tests
  - [x] Step 6.A: Add timezone-aware tests to `tests/unit/test_nutrition_tools.py` (Status: Implemented)

## Step-by-Step Implementation Details

### Prerequisites

None. `server/utils/dates.py` with `get_request_tz()` and `user_today()` is already implemented and tested. The `ClientTimezoneMiddleware` is already wired in `server/main.py`.

---

### Phase 1: Fix `server/nutrition/tools.py`

This file has 7 instances of naive `datetime.now()`. All of them compute "today" or a cutoff date for database queries. The fix pattern is identical to `server/coaching/tools.py`.

#### Step 1.A: Add import

*Target File:* `server/nutrition/tools.py`

**Before (line 2):**
```python
from datetime import datetime, timedelta
```

**After:**
```python
from datetime import datetime, timedelta
from server.utils.dates import get_request_tz, user_today
```

This import is added below the existing `datetime` import, before the `server.database` import on line 4.

#### Step 1.B: Fix `get_meal_history` (line 17)

*Target File:* `server/nutrition/tools.py`

**Before:**
```python
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
```

**After:**
```python
    cutoff = (datetime.now(get_request_tz()) - timedelta(days=days_back)).strftime("%Y-%m-%d")
```

#### Step 1.C: Fix `get_daily_macros` (line 41)

*Target File:* `server/nutrition/tools.py`

**Before:**
```python
        date = datetime.now().strftime("%Y-%m-%d")
```

**After:**
```python
        date = user_today()
```

#### Step 1.D: Fix `get_weekly_summary` (line 85)

*Target File:* `server/nutrition/tools.py`

**Before:**
```python
        date = datetime.now().strftime("%Y-%m-%d")
```

**After:**
```python
        date = user_today()
```

#### Step 1.E: Fix `get_caloric_balance` (line 130)

*Target File:* `server/nutrition/tools.py`

**Before:**
```python
        date = datetime.now().strftime("%Y-%m-%d")
```

**After:**
```python
        date = user_today()
```

#### Step 1.F: Fix `get_upcoming_training_load` (lines 174-175)

*Target File:* `server/nutrition/tools.py`

**Before:**
```python
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
```

**After:**
```python
    _now = datetime.now(get_request_tz())
    today = _now.strftime("%Y-%m-%d")
    end = (_now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
```

Note: Uses a single `_now` to avoid calling `datetime.now()` twice (avoids edge case where the date rolls over between the two calls).

#### Step 1.G: Fix `get_recent_workouts` (line 215)

*Target File:* `server/nutrition/tools.py`

**Before:**
```python
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
```

**After:**
```python
    cutoff = (datetime.now(get_request_tz()) - timedelta(days=days_back)).strftime("%Y-%m-%d")
```

#### Step 1.H: Fix `get_planned_meals` (line 253)

*Target File:* `server/nutrition/tools.py`

**Before:**
```python
        date = datetime.now().strftime("%Y-%m-%d")
```

**After:**
```python
        date = user_today()
```

---

### Phase 2: Fix `server/nutrition/agent.py`

The system instruction builder uses naive `datetime.now()` to tell the LLM what today's date is. This must match the user's local date.

#### Step 2.A: Fix `_build_system_instruction` (lines 80, 86-88, 101)

*Target File:* `server/nutrition/agent.py`

**Before (line 80):**
```python
    from datetime import datetime, timedelta
    from server.database import get_all_athlete_settings, get_db
    from server.queries import get_current_pmc_row, get_macro_targets
    from server.services.weight import get_current_weight

    settings = get_all_athlete_settings()
    today = datetime.now()
    today_str = today.strftime("%A, %B %d, %Y")
    today_iso = today.strftime("%Y-%m-%d")
```

**After:**
```python
    from datetime import datetime, timedelta
    from server.database import get_all_athlete_settings, get_db
    from server.queries import get_current_pmc_row, get_macro_targets
    from server.services.weight import get_current_weight
    from server.utils.dates import get_request_tz

    settings = get_all_athlete_settings()
    tz = get_request_tz()
    today = datetime.now(tz)
    today_str = today.strftime("%A, %B %d, %Y")
    today_iso = today.strftime("%Y-%m-%d")
```

This is the exact same pattern used in `server/coaching/agent.py:96-104`. The `three_days_ago` calculation on line 101 already derives from `today`, so it will automatically become timezone-aware with no further changes.

---

### Phase 3: Fix `server/routers/nutrition.py`

Two REST endpoints default to "today" using naive `datetime.now()`.

#### Step 3.A: Fix `daily_summary` endpoint (lines 387-389)

*Target File:* `server/routers/nutrition.py`

**Before:**
```python
    from datetime import datetime
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
```

**After:**
```python
    from server.utils.dates import user_today
    if not date:
        date = user_today()
```

The `datetime` import is no longer needed here since `user_today()` encapsulates the full operation. The function-local import is replaced with `user_today`.

#### Step 3.B: Fix `get_meal_plan` endpoint (lines 522-524)

*Target File:* `server/routers/nutrition.py`

**Before:**
```python
    from datetime import datetime, timedelta
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
```

**After:**
```python
    from datetime import datetime, timedelta
    from server.utils.dates import user_today
    if not date:
        date = user_today()
```

Note: `datetime` and `timedelta` are still needed on lines 527-528 for `datetime.fromisoformat(date)` and `timedelta(days=days - 1)`.

---

### Phase 4: Fix `server/nutrition/planning_tools.py`

#### Step 4.A: Fix `save_meal_analysis` date derivation (lines 68-69)

*Target File:* `server/nutrition/planning_tools.py`

The `logged_at` timestamp correctly uses UTC. But `date_str` (the user-facing calendar date) is derived from UTC, which is wrong for users west of UTC late at night.

**Before:**
```python
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    logged_at = now.isoformat()
```

**After:**
```python
    from server.utils.dates import user_today
    now = datetime.now(timezone.utc)
    date_str = user_today()
    logged_at = now.isoformat()
```

The `user_today()` import is function-local to avoid a circular import risk and to match the existing pattern in this file of using function-local imports. The `logged_at` field remains UTC, which is correct for a timestamp.

---

### Phase 5: Fix `server/nutrition/photo.py`

#### Step 5.A: Fix `upload_meal_photo` GCS path timestamp (line 56)

*Target File:* `server/nutrition/photo.py`

This is a low-priority cosmetic fix. The timestamp is used only in the GCS blob path for uniqueness. Using UTC makes the path deterministic regardless of timezone.

**Before:**
```python
from datetime import datetime
```
```python
    now = datetime.now()
```

**After:**
```python
from datetime import datetime, timezone
```
```python
    now = datetime.now(timezone.utc)
```

No need for `get_request_tz()` here -- file paths should use UTC for consistency. This just makes the naive call explicitly UTC.

---

### Phase 6: Add Unit Tests

#### Step 6.A: Add timezone-aware tests to `tests/unit/test_nutrition_tools.py`

*Target File:* `tests/unit/test_nutrition_tools.py`

Add tests that verify the nutrition tools correctly use `get_request_tz()` / `user_today()` instead of naive `datetime.now()`. The tests use `unittest.mock.patch` to mock `get_request_tz` and verify the mocked timezone is used.

**Append the following test cases after the existing tests:**

```python
def test_get_meal_history_uses_request_tz():
    """get_meal_history uses get_request_tz() for cutoff calculation."""
    from unittest.mock import patch, MagicMock
    from zoneinfo import ZoneInfo

    with patch("server.nutrition.tools.get_request_tz", return_value=ZoneInfo("America/Los_Angeles")) as mock_tz, \
         patch("server.nutrition.tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.nutrition.tools import get_meal_history
        get_meal_history(days_back=7)
        mock_tz.assert_called_once()


def test_get_daily_macros_uses_user_today():
    """get_daily_macros defaults to user_today() when no date given."""
    from unittest.mock import patch, MagicMock

    with patch("server.nutrition.tools.user_today", return_value="2026-04-14") as mock_today, \
         patch("server.nutrition.tools.get_db") as mock_db, \
         patch("server.nutrition.tools.get_macro_targets", return_value={"calories": 2500, "protein_g": 150, "carbs_g": 300, "fat_g": 80}):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.nutrition.tools import get_daily_macros
        result = get_daily_macros()
        mock_today.assert_called_once()
        assert result["date"] == "2026-04-14"


def test_get_upcoming_training_load_uses_request_tz():
    """get_upcoming_training_load uses get_request_tz() for today/end."""
    from unittest.mock import patch, MagicMock
    from zoneinfo import ZoneInfo

    with patch("server.nutrition.tools.get_request_tz", return_value=ZoneInfo("America/New_York")) as mock_tz, \
         patch("server.nutrition.tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.nutrition.tools import get_upcoming_training_load
        get_upcoming_training_load(days_ahead=3)
        mock_tz.assert_called()


def test_get_planned_meals_uses_user_today():
    """get_planned_meals defaults to user_today() when no date given."""
    from unittest.mock import patch, MagicMock

    with patch("server.nutrition.tools.user_today", return_value="2026-04-14") as mock_today, \
         patch("server.nutrition.tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.nutrition.tools import get_planned_meals
        result = get_planned_meals()
        mock_today.assert_called_once()
        assert result["start_date"] == "2026-04-14"


def test_save_meal_analysis_uses_user_today_for_date():
    """save_meal_analysis uses user_today() for the date field, not UTC."""
    from unittest.mock import patch, MagicMock

    with patch("server.nutrition.planning_tools.user_today", return_value="2026-04-13") as mock_today, \
         patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: 42  # mock lastval
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.nutrition.planning_tools import save_meal_analysis
        result = save_meal_analysis(
            "Test meal", [{"name": "Item"}],
            500, 30.0, 50.0, 15.0, "high"
        )
        mock_today.assert_called_once()
        assert result["date"] == "2026-04-13"
```

---

### Testing Strategy

- **Unit Tests:** Run `pytest tests/unit/test_nutrition_tools.py -v` to verify the new timezone-aware tests pass. Also run `pytest tests/unit/test_dates.py -v` to confirm the existing dates utility tests still pass.
- **Full Unit Suite:** Run `pytest tests/unit/ -v` to verify no regressions across all unit tests.
- **Integration Tests:** Run `./scripts/run_integration_tests.sh -v` to verify the nutrition API endpoints work correctly end-to-end with the test database.
- **Manual Smoke Test:** If a local dev environment is available, start the app with `./scripts/dev.sh`, open browser DevTools, verify the `X-Client-Timezone` header is sent on nutrition API calls, and confirm that the daily summary endpoint returns the correct local date.

---

## Success Criteria

1. Zero instances of naive `datetime.now()` remain in `server/nutrition/` (agent.py, tools.py, planning_tools.py, photo.py) and `server/routers/nutrition.py`.
2. All existing unit tests pass: `pytest tests/unit/ -v`.
3. New unit tests confirm that `get_request_tz()` / `user_today()` are called by the nutrition tools.
4. Integration tests pass: `./scripts/run_integration_tests.sh -v`.
5. A user in a US Pacific timezone logging a meal at 11pm local time sees the meal assigned to the correct local date (not the next UTC day).
