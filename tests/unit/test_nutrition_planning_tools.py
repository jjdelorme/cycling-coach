"""Unit tests for nutritionist meal planning tools.

Tests validation logic and error handling for:
- generate_meal_plan
- replace_planned_meal
- clear_meal_plan
- update_dietary_preferences
- get_planned_meals
- get_dietary_preferences

These are unit tests — no database required. DB calls are mocked.
Do NOT assert specific meal names; the agent decides those at runtime.
"""

from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# generate_meal_plan — validation
# ---------------------------------------------------------------------------

def test_generate_meal_plan_missing_date():
    """generate_meal_plan reports error for meal spec missing 'date'."""
    from server.nutrition.planning_tools import generate_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_meal_plan([
            {"meal_slot": "breakfast", "name": "Oats", "total_calories": 400,
             "total_protein_g": 15, "total_carbs_g": 60, "total_fat_g": 10}
        ])
    assert len(result["errors"]) == 1
    assert result["total_meals"] == 0


def test_generate_meal_plan_invalid_slot():
    """generate_meal_plan rejects invalid meal_slot values."""
    from server.nutrition.planning_tools import generate_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_meal_plan([
            {"date": "2099-01-01", "meal_slot": "midnight_snack", "name": "Pizza",
             "total_calories": 500, "total_protein_g": 20, "total_carbs_g": 50, "total_fat_g": 20}
        ])
    assert len(result["errors"]) == 1
    assert "meal_slot" in result["errors"][0]["error"]
    assert result["total_meals"] == 0


def test_generate_meal_plan_missing_name():
    """generate_meal_plan rejects meal spec missing 'name'."""
    from server.nutrition.planning_tools import generate_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_meal_plan([
            {"date": "2099-01-01", "meal_slot": "breakfast",
             "total_calories": 400, "total_protein_g": 15, "total_carbs_g": 60, "total_fat_g": 10}
        ])
    assert len(result["errors"]) == 1
    assert "name" in result["errors"][0]["error"]


def test_generate_meal_plan_calories_too_low():
    """generate_meal_plan rejects zero calories."""
    from server.nutrition.planning_tools import generate_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_meal_plan([
            {"date": "2099-01-01", "meal_slot": "lunch", "name": "Water",
             "total_calories": 0, "total_protein_g": 0, "total_carbs_g": 0, "total_fat_g": 0}
        ])
    assert len(result["errors"]) == 1
    assert "total_calories" in result["errors"][0]["error"]


def test_generate_meal_plan_calories_too_high():
    """generate_meal_plan rejects calories above 5000."""
    from server.nutrition.planning_tools import generate_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_meal_plan([
            {"date": "2099-01-01", "meal_slot": "dinner", "name": "Feast",
             "total_calories": 6000, "total_protein_g": 200, "total_carbs_g": 500, "total_fat_g": 200}
        ])
    assert len(result["errors"]) == 1
    assert "total_calories" in result["errors"][0]["error"]


def test_generate_meal_plan_negative_macros():
    """generate_meal_plan rejects negative macro values."""
    from server.nutrition.planning_tools import generate_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_meal_plan([
            {"date": "2099-01-01", "meal_slot": "breakfast", "name": "Bad Macros",
             "total_calories": 400, "total_protein_g": -10, "total_carbs_g": 60, "total_fat_g": 10}
        ])
    assert len(result["errors"]) == 1
    assert "non-negative" in result["errors"][0]["error"]


def test_generate_meal_plan_partial_success():
    """generate_meal_plan returns partial status when some specs fail."""
    from server.nutrition.planning_tools import generate_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_meal_plan([
            # Valid
            {"date": "2099-01-01", "meal_slot": "breakfast", "name": "Oats",
             "total_calories": 400, "total_protein_g": 15, "total_carbs_g": 60, "total_fat_g": 10},
            # Invalid (no date)
            {"meal_slot": "lunch", "name": "Salad",
             "total_calories": 350, "total_protein_g": 20, "total_carbs_g": 30, "total_fat_g": 15},
        ])
    assert result["status"] == "partial"
    assert result["total_meals"] == 1
    assert len(result["errors"]) == 1


def test_generate_meal_plan_success():
    """generate_meal_plan returns success when all specs are valid."""
    from server.nutrition.planning_tools import generate_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_meal_plan([
            {"date": "2099-01-01", "meal_slot": "breakfast", "name": "Oats",
             "total_calories": 400, "total_protein_g": 15, "total_carbs_g": 60, "total_fat_g": 10},
            {"date": "2099-01-01", "meal_slot": "lunch", "name": "Salad",
             "total_calories": 500, "total_protein_g": 30, "total_carbs_g": 40, "total_fat_g": 20},
        ])
    assert result["status"] == "success"
    assert result["total_meals"] == 2
    assert len(result["errors"]) == 0
    assert len(result["created"]) == 2


def test_generate_meal_plan_all_valid_slots():
    """generate_meal_plan accepts all valid meal slots."""
    from server.nutrition.planning_tools import generate_meal_plan, ALLOWED_MEAL_SLOTS

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        meals = [
            {"date": "2099-02-01", "meal_slot": slot, "name": f"Meal {slot}",
             "total_calories": 300, "total_protein_g": 20, "total_carbs_g": 30, "total_fat_g": 10}
            for slot in sorted(ALLOWED_MEAL_SLOTS)
        ]
        result = generate_meal_plan(meals)
    assert result["status"] == "success"
    assert result["total_meals"] == len(ALLOWED_MEAL_SLOTS)


# ---------------------------------------------------------------------------
# replace_planned_meal — validation
# ---------------------------------------------------------------------------

def test_replace_planned_meal_invalid_slot():
    """replace_planned_meal rejects invalid meal_slot."""
    from server.nutrition.planning_tools import replace_planned_meal

    result = replace_planned_meal(
        date="2099-01-01", meal_slot="brunch",
        name="Eggs", total_calories=400,
        total_protein_g=25, total_carbs_g=10, total_fat_g=20,
    )
    assert result["status"] == "error"
    assert "meal_slot" in result["message"]


def test_replace_planned_meal_calories_too_low():
    """replace_planned_meal rejects zero calories."""
    from server.nutrition.planning_tools import replace_planned_meal

    result = replace_planned_meal(
        date="2099-01-01", meal_slot="breakfast",
        name="Nothing", total_calories=0,
        total_protein_g=0, total_carbs_g=0, total_fat_g=0,
    )
    assert result["status"] == "error"
    assert "total_calories" in result["message"]


def test_replace_planned_meal_calories_too_high():
    """replace_planned_meal rejects calories above 5000."""
    from server.nutrition.planning_tools import replace_planned_meal

    result = replace_planned_meal(
        date="2099-01-01", meal_slot="dinner",
        name="Feast", total_calories=5001,
        total_protein_g=200, total_carbs_g=500, total_fat_g=200,
    )
    assert result["status"] == "error"
    assert "total_calories" in result["message"]


def test_replace_planned_meal_negative_macros():
    """replace_planned_meal rejects negative macro values."""
    from server.nutrition.planning_tools import replace_planned_meal

    result = replace_planned_meal(
        date="2099-01-01", meal_slot="lunch",
        name="Bad", total_calories=500,
        total_protein_g=30, total_carbs_g=-10, total_fat_g=15,
    )
    assert result["status"] == "error"
    assert "non-negative" in result["message"]


def test_replace_planned_meal_success():
    """replace_planned_meal returns success for valid input."""
    from server.nutrition.planning_tools import replace_planned_meal

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None  # no previous meal
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = replace_planned_meal(
            date="2099-01-01", meal_slot="breakfast",
            name="Oatmeal", total_calories=350,
            total_protein_g=12, total_carbs_g=55, total_fat_g=8,
            description="With berries and honey",
        )
    assert result["status"] == "success"
    assert result["action"] == "created"
    assert result["previous_meal"] is None
    assert result["total_calories"] == 350


# ---------------------------------------------------------------------------
# clear_meal_plan — validation
# ---------------------------------------------------------------------------

def test_clear_meal_plan_invalid_slot():
    """clear_meal_plan rejects invalid meal_slot."""
    from server.nutrition.planning_tools import clear_meal_plan

    result = clear_meal_plan(date="2099-01-01", meal_slot="elevenses")
    assert result["status"] == "error"
    assert "meal_slot" in result["message"]


def test_clear_meal_plan_by_date():
    """clear_meal_plan clears all meals for a date."""
    from server.nutrition.planning_tools import clear_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_conn.execute.return_value = mock_result
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = clear_meal_plan(date="2099-01-01")
    assert result["status"] == "success"
    assert result["meal_slot"] == "all"
    assert result["removed"] == 3


def test_clear_meal_plan_by_date_and_slot():
    """clear_meal_plan clears a specific slot for a date."""
    from server.nutrition.planning_tools import clear_meal_plan

    with patch("server.nutrition.planning_tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        result = clear_meal_plan(date="2099-01-01", meal_slot="breakfast")
    assert result["status"] == "success"
    assert result["meal_slot"] == "breakfast"
    assert result["removed"] == 1


# ---------------------------------------------------------------------------
# update_dietary_preferences — validation
# ---------------------------------------------------------------------------

def test_update_dietary_preferences_invalid_section():
    """update_dietary_preferences rejects invalid section names."""
    from server.nutrition.planning_tools import update_dietary_preferences

    result = update_dietary_preferences("meal_timing", "- Eat every 3 hours")
    assert result["status"] == "error"
    assert "section" in result["message"]


def test_update_dietary_preferences_dietary():
    """update_dietary_preferences accepts 'dietary_preferences' section."""
    from server.nutrition.planning_tools import update_dietary_preferences

    with patch("server.database.set_setting") as mock_set:
        result = update_dietary_preferences(
            "dietary_preferences",
            "- No restrictions\n- Allergies: none",
        )
    assert result["status"] == "success"
    assert result["section"] == "dietary_preferences"
    mock_set.assert_called_once_with("dietary_preferences", "- No restrictions\n- Allergies: none")


def test_update_dietary_preferences_principles():
    """update_dietary_preferences accepts 'nutritionist_principles' section."""
    from server.nutrition.planning_tools import update_dietary_preferences

    with patch("server.database.set_setting") as mock_set:
        result = update_dietary_preferences(
            "nutritionist_principles",
            "- High carb on hard days\n- Maintain protein",
        )
    assert result["status"] == "success"
    assert result["section"] == "nutritionist_principles"
    mock_set.assert_called_once()


# ---------------------------------------------------------------------------
# get_dietary_preferences — read tool
# ---------------------------------------------------------------------------

def test_get_dietary_preferences_returns_both_keys():
    """get_dietary_preferences returns dietary_preferences and nutritionist_principles."""
    from server.nutrition.tools import get_dietary_preferences

    with patch("server.database.get_setting") as mock_get:
        mock_get.side_effect = lambda k: f"mock_{k}"
        result = get_dietary_preferences()

    assert "dietary_preferences" in result
    assert "nutritionist_principles" in result
    assert result["dietary_preferences"] == "mock_dietary_preferences"
    assert result["nutritionist_principles"] == "mock_nutritionist_principles"


# ---------------------------------------------------------------------------
# ALLOWED_MEAL_SLOTS constant
# ---------------------------------------------------------------------------

def test_allowed_meal_slots_expected_values():
    """ALLOWED_MEAL_SLOTS contains all 7 expected slot types."""
    from server.nutrition.planning_tools import ALLOWED_MEAL_SLOTS

    expected = {"breakfast", "lunch", "dinner", "snack_am", "snack_pm", "pre_workout", "post_workout"}
    assert ALLOWED_MEAL_SLOTS == expected


# ---------------------------------------------------------------------------
# PlannedMeal schema
# ---------------------------------------------------------------------------

def test_planned_meal_schema():
    """PlannedMeal Pydantic model validates correctly."""
    from server.models.schemas import PlannedMeal

    meal = PlannedMeal(
        id=1, date="2099-01-01", meal_slot="breakfast", name="Oats",
        total_calories=400, total_protein_g=15, total_carbs_g=60, total_fat_g=10,
    )
    assert meal.meal_slot == "breakfast"
    assert meal.description is None
    assert meal.agent_notes is None
    assert meal.user_id == "athlete"


def test_meal_plan_day_totals_defaults():
    """MealPlanDayTotals defaults to zeros."""
    from server.models.schemas import MealPlanDayTotals

    totals = MealPlanDayTotals()
    assert totals.planned_calories == 0
    assert totals.actual_calories == 0
    assert totals.planned_protein_g == 0
    assert totals.actual_protein_g == 0


def test_dietary_preferences_update_schema():
    """DietaryPreferencesUpdate Pydantic model validates correctly."""
    from server.models.schemas import DietaryPreferencesUpdate

    update = DietaryPreferencesUpdate(section="dietary_preferences", value="- No restrictions")
    assert update.section == "dietary_preferences"
    assert update.value == "- No restrictions"
