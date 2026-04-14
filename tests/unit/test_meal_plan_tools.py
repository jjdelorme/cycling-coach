"""Thorough unit tests for meal plan tools, read-only tools, and router helpers.

Covers:
- planning_tools.py: success paths for save_meal_analysis, update_meal,
  delete_meal, set_macro_targets, generate_meal_plan with items,
  replace_planned_meal replacing existing
- tools.py: read-only tool functions (get_meal_history, get_daily_macros,
  get_weekly_summary, get_macro_targets_tool, get_upcoming_training_load,
  get_recent_workouts, get_planned_meals, get_dietary_preferences,
  get_caloric_balance)
- routers/nutrition.py: _build_meal_plan_day helper
- schemas: MealPlanDay, MealPlanResponse related models

DB calls are mocked. Do NOT assert specific meal names.
"""

import json
from unittest.mock import patch, MagicMock, PropertyMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db():
    """Create a mock get_db context manager."""
    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_db.return_value.__exit__ = MagicMock(return_value=False)
    return mock_db, mock_conn


# ===========================================================================
# save_meal_analysis — success path
# ===========================================================================

class TestSaveMealAnalysisSuccess:
    def test_saves_and_returns_meal_id(self):
        """save_meal_analysis saves to DB and returns meal_id."""
        from server.nutrition.planning_tools import save_meal_analysis

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = {"lastval": 42}

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = save_meal_analysis(
                meal_description="Grilled chicken with rice",
                items=[{"name": "Chicken", "serving_size": "6 oz", "calories": 300,
                        "protein_g": 40, "carbs_g": 0, "fat_g": 8}],
                total_calories=500,
                total_protein_g=45.0,
                total_carbs_g=50.0,
                total_fat_g=12.0,
                confidence="high",
                meal_type="lunch",
            )

        assert result["status"] == "saved"
        assert result["meal_id"] == 42
        assert result["total_calories"] == 500
        assert result["items_count"] == 1

    def test_saves_multiple_items(self):
        """save_meal_analysis inserts all items."""
        from server.nutrition.planning_tools import save_meal_analysis

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = {"lastval": 99}

        items = [
            {"name": "Rice", "calories": 200, "protein_g": 4, "carbs_g": 45, "fat_g": 1},
            {"name": "Chicken", "calories": 250, "protein_g": 35, "carbs_g": 0, "fat_g": 10},
            {"name": "Broccoli", "calories": 50, "protein_g": 5, "carbs_g": 8, "fat_g": 1},
        ]

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = save_meal_analysis(
                meal_description="Bowl",
                items=items,
                total_calories=500,
                total_protein_g=44,
                total_carbs_g=53,
                total_fat_g=12,
                confidence="medium",
            )

        assert result["items_count"] == 3
        # 1 meal_logs INSERT + 1 lastval SELECT + 3 meal_items INSERTs = 5 calls
        assert mock_conn.execute.call_count == 5

    def test_accepts_all_confidence_levels(self):
        """save_meal_analysis accepts high, medium, and low confidence."""
        from server.nutrition.planning_tools import save_meal_analysis

        for level in ("high", "medium", "low"):
            mock_db, mock_conn = _make_mock_db()
            mock_conn.execute.return_value.fetchone.return_value = {"lastval": 1}

            with patch("server.nutrition.planning_tools.get_db", mock_db):
                result = save_meal_analysis(
                    "test", [{"name": "x"}], 200, 10, 20, 5, level,
                )
            assert result["status"] == "saved", f"Failed for confidence={level}"

    def test_optional_fields_default_to_empty(self):
        """save_meal_analysis works without optional meal_type, photo_gcs_path, agent_notes."""
        from server.nutrition.planning_tools import save_meal_analysis

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = {"lastval": 5}

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = save_meal_analysis(
                "Simple meal", [{"name": "Food"}], 300, 20, 30, 10, "high",
            )

        assert result["status"] == "saved"
        assert result["confidence"] == "high"

    def test_boundary_calories_1(self):
        """save_meal_analysis accepts calories = 1 (lower boundary)."""
        from server.nutrition.planning_tools import save_meal_analysis

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = {"lastval": 1}

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = save_meal_analysis("Min", [{"name": "x"}], 1, 0, 0, 0, "low")
        assert result["status"] == "saved"

    def test_boundary_calories_10000(self):
        """save_meal_analysis accepts calories = 10000 (upper boundary)."""
        from server.nutrition.planning_tools import save_meal_analysis

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = {"lastval": 1}

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = save_meal_analysis("Max", [{"name": "x"}], 10000, 100, 200, 100, "high")
        assert result["status"] == "saved"

    def test_rejects_calories_10001(self):
        """save_meal_analysis rejects calories just above boundary."""
        from server.nutrition.planning_tools import save_meal_analysis
        result = save_meal_analysis("Over", [{"name": "x"}], 10001, 10, 10, 10, "high")
        assert "error" in result


# ===========================================================================
# update_meal — success path
# ===========================================================================

class TestUpdateMeal:
    def test_updates_calories(self):
        """update_meal updates calories and sets edited_by_user."""
        from server.nutrition.planning_tools import update_meal

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = update_meal(meal_id=10, total_calories=600)

        assert result["status"] == "updated"
        assert result["meal_id"] == 10
        # Should have called execute with UPDATE query
        call_args = mock_conn.execute.call_args
        assert "total_calories" in call_args[0][0]
        assert "edited_by_user" in call_args[0][0]

    def test_updates_multiple_fields(self):
        """update_meal updates multiple fields at once."""
        from server.nutrition.planning_tools import update_meal

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = update_meal(
                meal_id=10,
                total_calories=700,
                total_protein_g=45.0,
                total_carbs_g=80.0,
                total_fat_g=20.0,
                meal_type="dinner",
            )

        assert result["status"] == "updated"
        sql = mock_conn.execute.call_args[0][0]
        assert "total_calories" in sql
        assert "total_protein_g" in sql
        assert "total_carbs_g" in sql
        assert "total_fat_g" in sql
        assert "meal_type" in sql

    def test_updates_meal_type_only(self):
        """update_meal can update just the meal_type."""
        from server.nutrition.planning_tools import update_meal

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = update_meal(meal_id=5, meal_type="breakfast")

        assert result["status"] == "updated"


# ===========================================================================
# delete_meal
# ===========================================================================

class TestDeleteMeal:
    def test_deletes_existing_meal(self):
        """delete_meal deletes a meal that exists."""
        from server.nutrition.planning_tools import delete_meal

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = {"id": 5, "description": "Lunch"}

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = delete_meal(5)

        assert result["status"] == "deleted"
        assert result["meal_id"] == 5

    def test_returns_error_for_missing_meal(self):
        """delete_meal returns error if meal not found."""
        from server.nutrition.planning_tools import delete_meal

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = delete_meal(999)

        assert "error" in result
        assert "999" in result["error"]


# ===========================================================================
# set_macro_targets — success path
# ===========================================================================

class TestSetMacroTargets:
    def test_updates_targets(self):
        """set_macro_targets saves valid targets."""
        from server.nutrition.planning_tools import set_macro_targets

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = set_macro_targets(2800, 180.0, 350.0, 90.0)

        assert result["status"] == "updated"
        assert result["calories"] == 2800
        assert result["protein_g"] == 180.0
        assert result["carbs_g"] == 350.0
        assert result["fat_g"] == 90.0

    def test_boundary_calories_1(self):
        """set_macro_targets accepts calories = 1."""
        from server.nutrition.planning_tools import set_macro_targets

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = set_macro_targets(1, 0, 0, 0)
        assert result["status"] == "updated"

    def test_boundary_calories_10000(self):
        """set_macro_targets accepts calories = 10000."""
        from server.nutrition.planning_tools import set_macro_targets

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = set_macro_targets(10000, 300, 500, 200)
        assert result["status"] == "updated"

    def test_uses_upsert(self):
        """set_macro_targets uses ON CONFLICT for upsert."""
        from server.nutrition.planning_tools import set_macro_targets

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            set_macro_targets(2500, 150, 300, 80)

        sql = mock_conn.execute.call_args[0][0]
        assert "ON CONFLICT" in sql


# ===========================================================================
# generate_meal_plan — additional tests
# ===========================================================================

class TestGenerateMealPlanExtended:
    def test_items_serialized_as_json(self):
        """generate_meal_plan serializes items to JSON."""
        from server.nutrition.planning_tools import generate_meal_plan

        mock_db, mock_conn = _make_mock_db()
        items = [{"name": "Oats", "calories": 300}, {"name": "Berries", "calories": 50}]

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = generate_meal_plan([{
                "date": "2099-01-01",
                "meal_slot": "breakfast",
                "name": "Overnight Oats",
                "total_calories": 350,
                "total_protein_g": 12,
                "total_carbs_g": 55,
                "total_fat_g": 8,
                "items": items,
            }])

        assert result["status"] == "success"
        # Find the INSERT call and check items param
        insert_calls = [c for c in mock_conn.execute.call_args_list if "INSERT INTO planned_meals" in str(c)]
        assert len(insert_calls) == 1
        insert_params = insert_calls[0][0][1]
        # items_json is the 10th param (index 9)
        items_param = insert_params[9]
        assert items_param is not None
        parsed = json.loads(items_param)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Oats"

    def test_empty_items_stored_as_none(self):
        """generate_meal_plan stores empty items as None."""
        from server.nutrition.planning_tools import generate_meal_plan

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = generate_meal_plan([{
                "date": "2099-01-01",
                "meal_slot": "lunch",
                "name": "Salad",
                "total_calories": 300,
                "total_protein_g": 20,
                "total_carbs_g": 30,
                "total_fat_g": 10,
            }])

        assert result["status"] == "success"
        insert_calls = [c for c in mock_conn.execute.call_args_list if "INSERT INTO planned_meals" in str(c)]
        insert_params = insert_calls[0][0][1]
        assert insert_params[9] is None  # items_json

    def test_deletes_before_inserting(self):
        """generate_meal_plan deletes existing meal for same slot before inserting."""
        from server.nutrition.planning_tools import generate_meal_plan

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            generate_meal_plan([{
                "date": "2099-01-01",
                "meal_slot": "dinner",
                "name": "Pasta",
                "total_calories": 600,
                "total_protein_g": 25,
                "total_carbs_g": 80,
                "total_fat_g": 15,
            }])

        calls = mock_conn.execute.call_args_list
        # Should have DELETE before INSERT
        delete_calls = [i for i, c in enumerate(calls) if "DELETE FROM planned_meals" in str(c)]
        insert_calls = [i for i, c in enumerate(calls) if "INSERT INTO planned_meals" in str(c)]
        assert len(delete_calls) == 1
        assert len(insert_calls) == 1
        assert delete_calls[0] < insert_calls[0]

    def test_multi_day_plan(self):
        """generate_meal_plan handles multiple days."""
        from server.nutrition.planning_tools import generate_meal_plan

        mock_db, mock_conn = _make_mock_db()

        meals = []
        for day in range(1, 4):
            meals.append({
                "date": f"2099-01-0{day}",
                "meal_slot": "breakfast",
                "name": f"Day {day} Breakfast",
                "total_calories": 400,
                "total_protein_g": 15,
                "total_carbs_g": 55,
                "total_fat_g": 10,
            })

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = generate_meal_plan(meals)

        assert result["status"] == "success"
        assert result["total_meals"] == 3
        dates = {c["date"] for c in result["created"]}
        assert dates == {"2099-01-01", "2099-01-02", "2099-01-03"}

    def test_empty_list(self):
        """generate_meal_plan with empty list returns success with 0 meals."""
        from server.nutrition.planning_tools import generate_meal_plan

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = generate_meal_plan([])

        assert result["status"] == "success"
        assert result["total_meals"] == 0


# ===========================================================================
# replace_planned_meal — additional tests
# ===========================================================================

class TestReplacePlannedMealExtended:
    def test_replaces_existing_meal(self):
        """replace_planned_meal reports 'replaced' when previous meal exists."""
        from server.nutrition.planning_tools import replace_planned_meal

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = {"name": "Old Oatmeal"}

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = replace_planned_meal(
                date="2099-01-01",
                meal_slot="breakfast",
                name="Greek Yogurt Bowl",
                total_calories=400,
                total_protein_g=25,
                total_carbs_g=45,
                total_fat_g=12,
            )

        assert result["status"] == "success"
        assert result["action"] == "replaced"
        assert result["previous_meal"] == "Old Oatmeal"
        assert result["new_meal"] == "Greek Yogurt Bowl"

    def test_serializes_items(self):
        """replace_planned_meal serializes items to JSON."""
        from server.nutrition.planning_tools import replace_planned_meal

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = None

        items = [{"name": "Egg", "calories": 70}, {"name": "Toast", "calories": 100}]

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = replace_planned_meal(
                date="2099-01-01",
                meal_slot="breakfast",
                name="Eggs on Toast",
                total_calories=170,
                total_protein_g=12,
                total_carbs_g=15,
                total_fat_g=8,
                items=items,
            )

        assert result["status"] == "success"
        insert_calls = [c for c in mock_conn.execute.call_args_list if "INSERT INTO planned_meals" in str(c)]
        assert len(insert_calls) == 1

    def test_all_valid_slots(self):
        """replace_planned_meal accepts all valid slot types."""
        from server.nutrition.planning_tools import replace_planned_meal, ALLOWED_MEAL_SLOTS

        for slot in ALLOWED_MEAL_SLOTS:
            mock_db, mock_conn = _make_mock_db()
            mock_conn.execute.return_value.fetchone.return_value = None

            with patch("server.nutrition.planning_tools.get_db", mock_db):
                result = replace_planned_meal(
                    date="2099-01-01",
                    meal_slot=slot,
                    name="Test",
                    total_calories=300,
                    total_protein_g=20,
                    total_carbs_g=30,
                    total_fat_g=10,
                )
            assert result["status"] == "success", f"Failed for slot={slot}"

    def test_boundary_calories_5000(self):
        """replace_planned_meal accepts calories = 5000 (upper boundary)."""
        from server.nutrition.planning_tools import replace_planned_meal

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = replace_planned_meal(
                date="2099-01-01", meal_slot="dinner", name="Feast",
                total_calories=5000, total_protein_g=200,
                total_carbs_g=500, total_fat_g=200,
            )
        assert result["status"] == "success"


# ===========================================================================
# clear_meal_plan — additional tests
# ===========================================================================

class TestClearMealPlanExtended:
    def test_zero_removed(self):
        """clear_meal_plan reports 0 removed when no rows match."""
        from server.nutrition.planning_tools import clear_meal_plan

        mock_db, mock_conn = _make_mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_conn.execute.return_value = mock_result

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = clear_meal_plan(date="2099-12-31")

        assert result["status"] == "success"
        assert result["removed"] == 0

    def test_all_valid_slots(self):
        """clear_meal_plan accepts all valid slot types."""
        from server.nutrition.planning_tools import clear_meal_plan, ALLOWED_MEAL_SLOTS

        for slot in ALLOWED_MEAL_SLOTS:
            mock_db, mock_conn = _make_mock_db()
            mock_result = MagicMock()
            mock_result.rowcount = 1
            mock_conn.execute.return_value = mock_result

            with patch("server.nutrition.planning_tools.get_db", mock_db):
                result = clear_meal_plan(date="2099-01-01", meal_slot=slot)
            assert result["status"] == "success", f"Failed for slot={slot}"

    def test_message_includes_slot(self):
        """clear_meal_plan message mentions specific slot when provided."""
        from server.nutrition.planning_tools import clear_meal_plan

        mock_db, mock_conn = _make_mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result

        with patch("server.nutrition.planning_tools.get_db", mock_db):
            result = clear_meal_plan(date="2099-01-01", meal_slot="lunch")

        assert "lunch" in result["message"]


# ===========================================================================
# Read-only tools (tools.py)
# ===========================================================================

class TestGetMealHistory:
    def test_returns_list_of_dicts(self):
        """get_meal_history returns list of meal records."""
        from server.nutrition.tools import get_meal_history

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "date": "2099-01-01", "logged_at": "2099-01-01T12:00:00",
             "meal_type": "lunch", "description": "Chicken bowl",
             "total_calories": 600, "total_protein_g": 40, "total_carbs_g": 50,
             "total_fat_g": 20, "confidence": "high", "edited_by_user": False},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_meal_history(days_back=7)

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["total_calories"] == 600

    def test_empty_history(self):
        """get_meal_history returns empty list when no meals."""
        from server.nutrition.tools import get_meal_history

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_meal_history(days_back=30)

        assert result == []


class TestGetDailyMacros:
    def test_computes_totals_and_remaining(self):
        """get_daily_macros computes totals and remaining from targets."""
        from server.nutrition.tools import get_daily_macros

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "logged_at": "2099-01-01T08:00:00", "meal_type": "breakfast",
             "description": "Oats", "total_calories": 400, "total_protein_g": 15,
             "total_carbs_g": 60, "total_fat_g": 10, "confidence": "high"},
            {"id": 2, "logged_at": "2099-01-01T12:00:00", "meal_type": "lunch",
             "description": "Salad", "total_calories": 500, "total_protein_g": 30,
             "total_carbs_g": 40, "total_fat_g": 15, "confidence": "medium"},
        ]

        with patch("server.nutrition.tools.get_db", mock_db), \
             patch("server.nutrition.tools.get_macro_targets") as mock_targets:
            mock_targets.return_value = {
                "calories": 2500, "protein_g": 150, "carbs_g": 300, "fat_g": 80,
            }
            result = get_daily_macros("2099-01-01")

        assert result["date"] == "2099-01-01"
        assert result["total_calories"] == 900
        assert result["total_protein_g"] == 45.0
        assert result["remaining_calories"] == 1600
        assert result["meal_count"] == 2

    def test_defaults_to_today(self):
        """get_daily_macros uses today's date when empty string passed."""
        from server.nutrition.tools import get_daily_macros

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("server.nutrition.tools.get_db", mock_db), \
             patch("server.nutrition.tools.get_macro_targets") as mock_targets:
            mock_targets.return_value = {
                "calories": 2500, "protein_g": 150, "carbs_g": 300, "fat_g": 80,
            }
            result = get_daily_macros("")

        assert "date" in result
        assert result["meal_count"] == 0


class TestGetWeeklySummary:
    def test_weekly_structure(self):
        """get_weekly_summary returns Mon-Sun structure."""
        from server.nutrition.tools import get_weekly_summary

        mock_db, mock_conn = _make_mock_db()

        # Mock get_daily_meal_totals
        with patch("server.nutrition.tools.get_db", mock_db), \
             patch("server.nutrition.tools.get_daily_meal_totals") as mock_totals:
            mock_totals.return_value = {
                "calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "meal_count": 0,
            }
            mock_conn.execute.return_value.fetchone.return_value = {"ride_cal": 0}

            result = get_weekly_summary("2099-01-05")  # a Monday

        assert result["week_start"] == "2099-01-05"
        assert result["week_end"] == "2099-01-11"
        assert len(result["days"]) == 7

    def test_averages_only_days_with_meals(self):
        """get_weekly_summary averages only days that have meal_count > 0."""
        from server.nutrition.tools import get_weekly_summary

        mock_db, mock_conn = _make_mock_db()

        call_count = [0]

        def mock_totals_fn(conn, date):
            call_count[0] += 1
            if call_count[0] <= 2:  # First 2 days have meals
                return {"calories": 2000, "protein_g": 150, "carbs_g": 250, "fat_g": 70, "meal_count": 3}
            return {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "meal_count": 0}

        with patch("server.nutrition.tools.get_db", mock_db), \
             patch("server.nutrition.tools.get_daily_meal_totals", side_effect=mock_totals_fn):
            mock_conn.execute.return_value.fetchone.return_value = {"ride_cal": 0}

            result = get_weekly_summary("2099-01-05")

        # Average should be 2000 (2 days of 2000 / 2), not 571 (4000/7)
        assert result["avg_daily_calories"] == 2000


class TestGetMacroTargetsTool:
    def test_returns_targets(self):
        """get_macro_targets_tool returns current targets."""
        from server.nutrition.tools import get_macro_targets_tool

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.tools.get_db", mock_db), \
             patch("server.nutrition.tools.get_macro_targets") as mock_targets:
            mock_targets.return_value = {
                "calories": 3000, "protein_g": 200, "carbs_g": 350, "fat_g": 90,
            }
            result = get_macro_targets_tool()

        assert result["calories"] == 3000


class TestGetUpcomingTrainingLoad:
    def test_calculates_estimated_calories(self):
        """get_upcoming_training_load estimates ride calories from duration."""
        from server.nutrition.tools import get_upcoming_training_load

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": "2099-01-02", "name": "Endurance Ride",
             "total_duration_s": 7200, "planned_tss": 120, "coach_notes": "Easy ride"},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_upcoming_training_load(days_ahead=3)

        assert len(result["days"]) == 1
        assert result["days"][0]["duration_h"] == 2.0
        assert result["days"][0]["estimated_calories"] == 1200  # 2h * 600
        assert result["total_planned_tss"] == 120

    def test_empty_schedule(self):
        """get_upcoming_training_load returns empty when no planned workouts."""
        from server.nutrition.tools import get_upcoming_training_load

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_upcoming_training_load()

        assert result["days"] == []
        assert result["total_planned_tss"] == 0
        assert result["total_estimated_calories"] == 0

    def test_date_serialized_as_string_from_date_object(self):
        """get_upcoming_training_load converts datetime.date to string for JSON safety."""
        from datetime import date
        from server.nutrition.tools import get_upcoming_training_load

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": date(2099, 1, 2), "name": "Intervals",
             "total_duration_s": 3600, "planned_tss": 80, "coach_notes": None},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_upcoming_training_load(days_ahead=3)

        assert isinstance(result["days"][0]["date"], str)
        assert result["days"][0]["date"] == "2099-01-02"

    def test_date_serialized_as_string_from_text(self):
        """get_upcoming_training_load keeps string dates as strings."""
        from server.nutrition.tools import get_upcoming_training_load

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": "2099-03-15", "name": "Recovery",
             "total_duration_s": 1800, "planned_tss": 20, "coach_notes": None},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_upcoming_training_load(days_ahead=3)

        assert isinstance(result["days"][0]["date"], str)
        assert result["days"][0]["date"] == "2099-03-15"


class TestGetRecentWorkouts:
    def test_returns_ride_summaries(self):
        """get_recent_workouts returns formatted ride data."""
        from server.nutrition.tools import get_recent_workouts

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": "2099-01-01", "sub_sport": "road", "duration_s": 3600,
             "tss": 80, "total_calories": 700, "avg_power": 200, "normalized_power": 220},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_recent_workouts(days_back=3)

        assert len(result) == 1
        assert result[0]["duration_h"] == 1.0
        assert result[0]["calories_burned"] == 700
        assert result[0]["sport"] == "road"

    def test_date_serialized_as_string_from_date_object(self):
        """get_recent_workouts converts datetime.date to string for JSON safety."""
        from datetime import date
        from server.nutrition.tools import get_recent_workouts

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": date(2099, 1, 5), "sub_sport": "mountain", "duration_s": 5400,
             "tss": 95, "total_calories": 900, "avg_power": 180, "normalized_power": 210},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_recent_workouts(days_back=7)

        assert isinstance(result[0]["date"], str)
        assert result[0]["date"] == "2099-01-05"


class TestGetPlannedMeals:
    def test_organizes_by_date(self):
        """get_planned_meals organizes results by date."""
        from server.nutrition.tools import get_planned_meals

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": "2099-01-01", "meal_slot": "breakfast", "name": "Oats",
             "description": None, "total_calories": 400, "total_protein_g": 15,
             "total_carbs_g": 60, "total_fat_g": 10, "items": None, "agent_notes": None},
            {"date": "2099-01-01", "meal_slot": "lunch", "name": "Salad",
             "description": None, "total_calories": 350, "total_protein_g": 25,
             "total_carbs_g": 30, "total_fat_g": 12, "items": None, "agent_notes": None},
            {"date": "2099-01-02", "meal_slot": "breakfast", "name": "Eggs",
             "description": None, "total_calories": 300, "total_protein_g": 20,
             "total_carbs_g": 5, "total_fat_g": 18, "items": None, "agent_notes": None},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_planned_meals(date="2099-01-01", days_ahead=7)

        assert result["total_days_with_plans"] == 2
        assert len(result["days"]) == 2
        # Day 1 should have 2 meals
        day1 = next(d for d in result["days"] if d["date"] == "2099-01-01")
        assert len(day1["meals"]) == 2
        assert day1["day_calories"] == 750

    def test_parses_items_json(self):
        """get_planned_meals parses items JSON correctly."""
        from server.nutrition.tools import get_planned_meals

        mock_db, mock_conn = _make_mock_db()
        items_json = json.dumps([{"name": "Chicken", "calories": 300}])
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": "2099-01-01", "meal_slot": "dinner", "name": "Dinner",
             "description": None, "total_calories": 500, "total_protein_g": 40,
             "total_carbs_g": 30, "total_fat_g": 15, "items": items_json, "agent_notes": None},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_planned_meals(date="2099-01-01")

        meal = result["days"][0]["meals"][0]
        assert len(meal["items"]) == 1
        assert meal["items"][0]["name"] == "Chicken"

    def test_handles_invalid_items_json(self):
        """get_planned_meals handles invalid JSON in items gracefully."""
        from server.nutrition.tools import get_planned_meals

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": "2099-01-01", "meal_slot": "lunch", "name": "Meal",
             "description": None, "total_calories": 300, "total_protein_g": 20,
             "total_carbs_g": 30, "total_fat_g": 10, "items": "NOT VALID JSON",
             "agent_notes": None},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_planned_meals(date="2099-01-01")

        meal = result["days"][0]["meals"][0]
        assert meal["items"] == []


class TestGetCaloricBalance:
    def test_computes_balance(self):
        """get_caloric_balance computes intake - expenditure."""
        from server.nutrition.tools import get_caloric_balance

        mock_db, mock_conn = _make_mock_db()

        with patch("server.nutrition.tools.get_db", mock_db), \
             patch("server.nutrition.tools.get_daily_meal_totals") as mock_totals, \
             patch("server.services.weight.get_weight_for_date") as mock_weight, \
             patch("server.nutrition.tools._estimate_daily_bmr") as mock_bmr:
            mock_totals.return_value = {"calories": 2200, "protein_g": 150, "carbs_g": 250, "fat_g": 70, "meal_count": 4}
            mock_conn.execute.return_value.fetchone.return_value = {"total": 800}
            mock_weight.return_value = 75.0
            mock_bmr.return_value = 1800

            result = get_caloric_balance("2099-01-01")

        assert result["date"] == "2099-01-01"
        assert result["intake"] == 2200
        assert result["rides"] == 800
        assert result["estimated_bmr"] == 1800
        assert result["total_expenditure"] == 2600  # 800 + 1800
        assert result["net_balance"] == -400  # 2200 - 2600


class TestEstimateDailyBMR:
    def test_male_bmr(self):
        """BMR calculation for male athlete."""
        from server.nutrition.tools import _estimate_daily_bmr

        with patch("server.nutrition.tools.get_all_athlete_settings") as mock_settings:
            mock_settings.return_value = {"weight_kg": "80", "age": "35", "gender": "male"}
            result = _estimate_daily_bmr(80)

        # Mifflin-St Jeor: 10*80 + 6.25*175 - 5*35 + 5 = 800 + 1093.75 - 175 + 5 = 1723.75
        # * 1.2 = 2068.5 -> 2068
        assert result == 2068

    def test_female_bmr(self):
        """BMR calculation for female athlete."""
        from server.nutrition.tools import _estimate_daily_bmr

        with patch("server.nutrition.tools.get_all_athlete_settings") as mock_settings:
            mock_settings.return_value = {"weight_kg": "60", "age": "30", "gender": "female"}
            result = _estimate_daily_bmr(60)

        # 10*60 + 6.25*165 - 5*30 - 161 = 600 + 1031.25 - 150 - 161 = 1320.25
        # * 1.2 = 1584.3 -> 1584
        assert result == 1584

    def test_unknown_gender(self):
        """BMR uses neutral formula for unspecified gender."""
        from server.nutrition.tools import _estimate_daily_bmr

        with patch("server.nutrition.tools.get_all_athlete_settings") as mock_settings:
            mock_settings.return_value = {"weight_kg": "70", "age": "40", "gender": ""}
            result = _estimate_daily_bmr(70)

        # 10*70 + 6.25*170 - 5*40 - 78 = 700 + 1062.5 - 200 - 78 = 1484.5
        # * 1.2 = 1781.4 -> 1781
        assert result == 1781

    def test_falls_back_to_weight_from_settings(self):
        """BMR reads weight_kg from settings when 0 passed."""
        from server.nutrition.tools import _estimate_daily_bmr

        with patch("server.nutrition.tools.get_all_athlete_settings") as mock_settings:
            mock_settings.return_value = {"weight_kg": "75", "age": "30", "gender": "male"}
            result = _estimate_daily_bmr(0)

        assert result > 0
        assert result != 1750  # not the fallback default


# ===========================================================================
# _build_meal_plan_day helper (routers/nutrition.py)
# ===========================================================================

class TestBuildMealPlanDay:
    def test_empty_day(self):
        """_build_meal_plan_day returns correct structure for empty day."""
        from server.routers.nutrition import _build_meal_plan_day

        result = _build_meal_plan_day("2099-01-01", [], [])

        assert result["date"] == "2099-01-01"
        assert result["planned"] == {}
        assert result["actual"] == []
        assert result["day_totals"]["planned_calories"] == 0
        assert result["day_totals"]["actual_calories"] == 0

    def test_planned_meals_organized_by_slot(self):
        """_build_meal_plan_day organizes planned meals by slot key."""
        from server.routers.nutrition import _build_meal_plan_day

        planned = [
            {"id": 1, "user_id": "athlete", "date": "2099-01-01",
             "meal_slot": "breakfast", "name": "Oats",
             "description": "With berries", "total_calories": 400,
             "total_protein_g": 15, "total_carbs_g": 60, "total_fat_g": 10,
             "items": None, "agent_notes": "Good pre-ride fuel", "created_at": None},
            {"id": 2, "user_id": "athlete", "date": "2099-01-01",
             "meal_slot": "dinner", "name": "Pasta",
             "description": None, "total_calories": 700,
             "total_protein_g": 30, "total_carbs_g": 90, "total_fat_g": 15,
             "items": None, "agent_notes": None, "created_at": None},
        ]

        result = _build_meal_plan_day("2099-01-01", planned, [])

        assert "breakfast" in result["planned"]
        assert "dinner" in result["planned"]
        assert result["planned"]["breakfast"]["name"] == "Oats"
        assert result["planned"]["breakfast"]["description"] == "With berries"
        assert result["planned"]["breakfast"]["agent_notes"] == "Good pre-ride fuel"
        assert result["planned"]["dinner"]["name"] == "Pasta"
        assert result["day_totals"]["planned_calories"] == 1100
        assert result["day_totals"]["planned_protein_g"] == 45.0

    def test_actual_meals_list(self):
        """_build_meal_plan_day builds actual meals list with photo URLs."""
        from server.routers.nutrition import _build_meal_plan_day

        actual = [
            {"id": 10, "date": "2099-01-01", "logged_at": "2099-01-01T08:00:00",
             "meal_type": "breakfast", "description": "Scrambled eggs",
             "total_calories": 350, "total_protein_g": 25, "total_carbs_g": 5,
             "total_fat_g": 22, "confidence": "high", "photo_gcs_path": "meals/abc.jpg",
             "edited_by_user": False},
        ]

        result = _build_meal_plan_day("2099-01-01", [], actual)

        assert len(result["actual"]) == 1
        assert result["actual"][0]["id"] == 10
        assert result["actual"][0]["description"] == "Scrambled eggs"
        assert result["actual"][0]["photo_url"] == "/api/nutrition/photos/10"
        assert result["day_totals"]["actual_calories"] == 350

    def test_no_photo_url_when_no_photo(self):
        """_build_meal_plan_day returns empty photo_url when no photo."""
        from server.routers.nutrition import _build_meal_plan_day

        actual = [
            {"id": 11, "date": "2099-01-01", "logged_at": "2099-01-01T12:00:00",
             "meal_type": "lunch", "description": "Salad",
             "total_calories": 300, "total_protein_g": 20, "total_carbs_g": 30,
             "total_fat_g": 10, "confidence": "medium", "photo_gcs_path": "",
             "edited_by_user": False},
        ]

        result = _build_meal_plan_day("2099-01-01", [], actual)
        assert result["actual"][0]["photo_url"] == ""

    def test_combined_planned_and_actual(self):
        """_build_meal_plan_day computes totals for both planned and actual."""
        from server.routers.nutrition import _build_meal_plan_day

        planned = [
            {"id": 1, "user_id": "athlete", "date": "2099-01-01",
             "meal_slot": "breakfast", "name": "Oats",
             "description": None, "total_calories": 400,
             "total_protein_g": 15, "total_carbs_g": 60, "total_fat_g": 10,
             "items": None, "agent_notes": None, "created_at": None},
        ]
        actual = [
            {"id": 10, "date": "2099-01-01", "logged_at": "2099-01-01T08:00:00",
             "meal_type": "breakfast", "description": "Oatmeal actually eaten",
             "total_calories": 450, "total_protein_g": 18, "total_carbs_g": 65,
             "total_fat_g": 12, "confidence": "high", "photo_gcs_path": None,
             "edited_by_user": True},
        ]

        result = _build_meal_plan_day("2099-01-01", planned, actual)

        assert result["day_totals"]["planned_calories"] == 400
        assert result["day_totals"]["actual_calories"] == 450
        assert result["day_totals"]["planned_protein_g"] == 15.0
        assert result["day_totals"]["actual_protein_g"] == 18.0

    def test_items_json_parsed(self):
        """_build_meal_plan_day parses items JSON in planned meals."""
        from server.routers.nutrition import _build_meal_plan_day

        items_json = json.dumps([{"name": "Chicken", "calories": 300}])
        planned = [
            {"id": 1, "user_id": "athlete", "date": "2099-01-01",
             "meal_slot": "lunch", "name": "Chicken Bowl",
             "description": None, "total_calories": 500,
             "total_protein_g": 40, "total_carbs_g": 30, "total_fat_g": 15,
             "items": items_json, "agent_notes": None, "created_at": None},
        ]

        result = _build_meal_plan_day("2099-01-01", planned, [])
        assert result["planned"]["lunch"]["items"] is not None
        assert len(result["planned"]["lunch"]["items"]) == 1
        assert result["planned"]["lunch"]["items"][0]["name"] == "Chicken"

    def test_invalid_items_json(self):
        """_build_meal_plan_day handles invalid items JSON gracefully."""
        from server.routers.nutrition import _build_meal_plan_day

        planned = [
            {"id": 1, "user_id": "athlete", "date": "2099-01-01",
             "meal_slot": "dinner", "name": "Mystery Meal",
             "description": None, "total_calories": 500,
             "total_protein_g": 30, "total_carbs_g": 50, "total_fat_g": 15,
             "items": "{invalid json", "agent_notes": None, "created_at": None},
        ]

        result = _build_meal_plan_day("2099-01-01", planned, [])
        assert result["planned"]["dinner"]["items"] is None

    def test_multiple_actual_meals(self):
        """_build_meal_plan_day sums multiple actual meals."""
        from server.routers.nutrition import _build_meal_plan_day

        actual = [
            {"id": 10, "date": "2099-01-01", "logged_at": "2099-01-01T08:00:00",
             "meal_type": "breakfast", "description": "Eggs",
             "total_calories": 300, "total_protein_g": 25, "total_carbs_g": 5,
             "total_fat_g": 20, "confidence": "high", "photo_gcs_path": None,
             "edited_by_user": False},
            {"id": 11, "date": "2099-01-01", "logged_at": "2099-01-01T12:00:00",
             "meal_type": "lunch", "description": "Sandwich",
             "total_calories": 500, "total_protein_g": 30, "total_carbs_g": 50,
             "total_fat_g": 15, "confidence": "medium", "photo_gcs_path": None,
             "edited_by_user": False},
        ]

        result = _build_meal_plan_day("2099-01-01", [], actual)
        assert result["day_totals"]["actual_calories"] == 800
        assert result["day_totals"]["actual_protein_g"] == 55.0


# ===========================================================================
# _photo_url helper
# ===========================================================================

class TestPhotoUrl:
    def test_returns_url_when_has_photo(self):
        from server.routers.nutrition import _photo_url
        assert _photo_url(42, True) == "/api/nutrition/photos/42"

    def test_returns_empty_when_no_photo(self):
        from server.routers.nutrition import _photo_url
        assert _photo_url(42, False) == ""

    def test_returns_empty_when_no_meal_id(self):
        from server.routers.nutrition import _photo_url
        assert _photo_url(None, True) == ""


# ===========================================================================
# Pydantic Schemas
# ===========================================================================

class TestSchemas:
    def test_meal_plan_day_schema(self):
        """MealPlanDay schema accepts valid data."""
        from server.models.schemas import MealPlanDay, PlannedMeal, MealPlanDayTotals

        meal = PlannedMeal(
            id=1, date="2099-01-01", meal_slot="breakfast", name="Oats",
            total_calories=400, total_protein_g=15, total_carbs_g=60, total_fat_g=10,
        )
        day = MealPlanDay(
            date="2099-01-01",
            planned={"breakfast": meal},
            actual=[],
            day_totals=MealPlanDayTotals(
                planned_calories=400, actual_calories=0,
                planned_protein_g=15.0, actual_protein_g=0,
                planned_carbs_g=60.0, actual_carbs_g=0,
                planned_fat_g=10.0, actual_fat_g=0,
            ),
        )
        assert day.date == "2099-01-01"
        assert day.planned["breakfast"].name == "Oats"
        assert day.day_totals.planned_calories == 400

    def test_meal_plan_day_empty(self):
        """MealPlanDay with defaults."""
        from server.models.schemas import MealPlanDay

        day = MealPlanDay(date="2099-01-01")
        assert day.planned == {}
        assert day.actual == []
        assert day.day_totals.planned_calories == 0

    def test_planned_meal_with_items(self):
        """PlannedMeal accepts items list."""
        from server.models.schemas import PlannedMeal, MealItem

        items = [
            MealItem(name="Rice", calories=200, protein_g=4, carbs_g=45, fat_g=1),
            MealItem(name="Chicken", calories=300, protein_g=35, carbs_g=0, fat_g=8),
        ]
        meal = PlannedMeal(
            id=1, date="2099-01-01", meal_slot="lunch", name="Rice Bowl",
            total_calories=500, total_protein_g=39, total_carbs_g=45, total_fat_g=9,
            items=items,
        )
        assert len(meal.items) == 2
        assert meal.items[0].name == "Rice"

    def test_dietary_preferences_update(self):
        """DietaryPreferencesUpdate with both sections."""
        from server.models.schemas import DietaryPreferencesUpdate

        for section in ("dietary_preferences", "nutritionist_principles"):
            update = DietaryPreferencesUpdate(section=section, value="- Test value")
            assert update.section == section

    def test_nutrition_chat_request_with_image(self):
        """NutritionChatRequest accepts image data."""
        from server.models.schemas import NutritionChatRequest

        req = NutritionChatRequest(
            message="Analyze this", session_id="abc-123",
            image_data="base64data", image_mime_type="image/jpeg",
        )
        assert req.image_data == "base64data"
        assert req.image_mime_type == "image/jpeg"

    def test_meal_update_request_all_fields(self):
        """MealUpdateRequest can set all fields."""
        from server.models.schemas import MealUpdateRequest, MealItem

        req = MealUpdateRequest(
            total_calories=600,
            total_protein_g=40.0,
            total_carbs_g=50.0,
            total_fat_g=25.0,
            meal_type="dinner",
            date="2099-01-01",
            items=[MealItem(name="Food", calories=600, protein_g=40, carbs_g=50, fat_g=25)],
        )
        assert req.total_calories == 600
        assert req.date == "2099-01-01"
        assert len(req.items) == 1


# ===========================================================================
# ask_clarification edge cases
# ===========================================================================

class TestAskClarification:
    def test_empty_context(self):
        """ask_clarification works with empty context."""
        from server.nutrition.planning_tools import ask_clarification
        result = ask_clarification("How big was the portion?")
        assert result["status"] == "clarification_needed"
        assert result["context"] == ""

    def test_preserves_question_text(self):
        """ask_clarification returns the question exactly."""
        from server.nutrition.planning_tools import ask_clarification
        q = "Was that with dressing or without?"
        result = ask_clarification(q, "salad dressing")
        assert result["question"] == q


# ===========================================================================
# MEAL_SLOT_ORDER constant in router
# ===========================================================================

def test_meal_slot_order():
    """MEAL_SLOT_ORDER contains expected slots in display order."""
    from server.routers.nutrition import MEAL_SLOT_ORDER

    assert MEAL_SLOT_ORDER == [
        "breakfast", "snack_am", "lunch", "snack_pm",
        "pre_workout", "post_workout", "dinner",
    ]


# ===========================================================================
# JSON serializability of tool results (regression: datetime.date crash)
# ===========================================================================

class TestToolResultsJsonSerializable:
    """Tool results must be JSON-serializable because ADK sends them to the
    LLM as part of the next request. A datetime.date object in a tool result
    crashes the ADK with 'TypeError: Object of type date is not JSON
    serializable'. These tests verify the fix: str() conversion on date
    fields returned by tools that query tables which may use DATE column type.
    """

    def test_upcoming_training_load_json_safe(self):
        """get_upcoming_training_load result is JSON-serializable with DATE column."""
        import json
        from datetime import date
        from server.nutrition.tools import get_upcoming_training_load

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": date(2099, 6, 15), "name": "Threshold",
             "total_duration_s": 5400, "planned_tss": 90, "coach_notes": "Hard day"},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_upcoming_training_load(days_ahead=3)

        # Must not raise TypeError
        serialized = json.dumps(result)
        assert "2099-06-15" in serialized

    def test_recent_workouts_json_safe(self):
        """get_recent_workouts result is JSON-serializable with DATE column."""
        import json
        from datetime import date
        from server.nutrition.tools import get_recent_workouts

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": date(2099, 6, 14), "sub_sport": "road", "duration_s": 7200,
             "tss": 110, "total_calories": 1200, "avg_power": 210, "normalized_power": 230},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_recent_workouts(days_back=3)

        # Must not raise TypeError
        serialized = json.dumps(result)
        assert "2099-06-14" in serialized

    def test_get_planned_meals_json_safe(self):
        """get_planned_meals result is JSON-serializable (date column is TEXT, but verify)."""
        import json
        from server.nutrition.tools import get_planned_meals

        mock_db, mock_conn = _make_mock_db()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"date": "2099-01-01", "meal_slot": "lunch", "name": "Salad",
             "description": None, "total_calories": 400, "total_protein_g": 25,
             "total_carbs_g": 35, "total_fat_g": 12, "items": None, "agent_notes": None},
        ]

        with patch("server.nutrition.tools.get_db", mock_db):
            result = get_planned_meals(date="2099-01-01", days_ahead=1)

        serialized = json.dumps(result)
        assert "2099-01-01" in serialized
