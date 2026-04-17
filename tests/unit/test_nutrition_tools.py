"""Unit tests for nutrition tool logic."""


def test_estimate_daily_bmr_defaults():
    """BMR returns 1750 when athlete settings are incomplete."""
    from server.nutrition.tools import _estimate_daily_bmr
    # With no DB, this will use defaults (weight_kg=0) -> 1750
    result = _estimate_daily_bmr()
    assert result == 1750


def test_photo_validation():
    """Photo module rejects invalid MIME types."""
    from server.nutrition.photo import ALLOWED_MIME_TYPES
    assert "image/jpeg" in ALLOWED_MIME_TYPES
    assert "image/png" in ALLOWED_MIME_TYPES
    assert "image/webp" in ALLOWED_MIME_TYPES
    assert "image/gif" not in ALLOWED_MIME_TYPES
    assert "application/pdf" not in ALLOWED_MIME_TYPES


def test_save_meal_validation_calories_zero():
    """save_meal_analysis rejects zero calories."""
    from server.nutrition.planning_tools import save_meal_analysis
    result = save_meal_analysis("test", [{"name": "x"}], 0, 10, 10, 10, "high")
    assert "error" in result


def test_save_meal_validation_calories_too_high():
    """save_meal_analysis rejects absurdly high calories."""
    from server.nutrition.planning_tools import save_meal_analysis
    result = save_meal_analysis("test", [{"name": "x"}], 15000, 10, 10, 10, "high")
    assert "error" in result


def test_save_meal_validation_negative_macros():
    """save_meal_analysis rejects negative macro values."""
    from server.nutrition.planning_tools import save_meal_analysis
    result = save_meal_analysis("test", [{"name": "x"}], 500, -10, 10, 10, "high")
    assert "error" in result


def test_save_meal_validation_invalid_confidence():
    """save_meal_analysis rejects invalid confidence level."""
    from server.nutrition.planning_tools import save_meal_analysis
    result = save_meal_analysis("test", [{"name": "x"}], 500, 10, 10, 10, "unknown")
    assert "error" in result
    assert "confidence" in result["error"]


def test_save_meal_validation_empty_items():
    """save_meal_analysis rejects empty items list."""
    from server.nutrition.planning_tools import save_meal_analysis
    result = save_meal_analysis("test", [], 500, 10, 10, 10, "high")
    assert "error" in result
    assert "items" in result["error"]


def test_set_macro_targets_validation():
    """set_macro_targets rejects invalid input."""
    from server.nutrition.planning_tools import set_macro_targets
    result = set_macro_targets(0, 150, 300, 80)
    assert "error" in result
    result = set_macro_targets(15000, 150, 300, 80)
    assert "error" in result
    result = set_macro_targets(2500, -10, 300, 80)
    assert "error" in result


def test_update_meal_no_values():
    """update_meal rejects empty updates."""
    from server.nutrition.planning_tools import update_meal
    result = update_meal(1)
    assert "error" in result
    assert "No values" in result["error"]


def test_ask_clarification_returns_question():
    """ask_clarification echoes the question back."""
    from server.nutrition.planning_tools import ask_clarification
    result = ask_clarification("Is that grilled or fried chicken?", "cooking method")
    assert result["status"] == "clarification_needed"
    assert "grilled" in result["question"]
    assert result["context"] == "cooking method"


def test_photo_constants():
    """Photo module constants are set correctly."""
    from server.nutrition.photo import MAX_IMAGE_SIZE_MB, MAX_IMAGE_DIMENSION
    assert MAX_IMAGE_SIZE_MB == 10
    assert MAX_IMAGE_DIMENSION == 1200


def test_nutrition_schemas():
    """Nutrition Pydantic schemas validate correctly."""
    from server.models.schemas import (
        MealItem, MealSummary, MacroTargets,
        NutritionChatRequest, NutritionChatResponse,
        MealUpdateRequest,
    )

    # MealItem
    item = MealItem(name="Chicken", calories=200, protein_g=30, carbs_g=0, fat_g=8)
    assert item.name == "Chicken"
    assert item.serving_size is None

    # MacroTargets
    targets = MacroTargets(calories=2500, protein_g=150, carbs_g=300, fat_g=80)
    assert targets.calories == 2500

    # NutritionChatRequest
    req = NutritionChatRequest(message="What should I eat?")
    assert req.session_id is None
    assert req.image_data is None

    # MealUpdateRequest
    update = MealUpdateRequest(total_calories=600)
    assert update.total_calories == 600
    assert update.total_protein_g is None


def test_agent_app_name():
    """Nutritionist agent has correct app name."""
    from server.nutrition.agent import APP_NAME
    assert APP_NAME == "nutrition-coach"


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

    with patch("server.utils.dates.user_today", return_value="2026-04-13") as mock_today, \
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


# ---------------------------------------------------------------------------
# Tests for rides.date -> start_time AT TIME ZONE conversion (Phase 2)
# ---------------------------------------------------------------------------


def test_get_weekly_summary_ride_calories_uses_start_time():
    """get_weekly_summary ride calorie query uses AT TIME ZONE, not rides.date."""
    from unittest.mock import patch, MagicMock, call
    from zoneinfo import ZoneInfo

    with patch("server.nutrition.tools.user_today", return_value="2026-04-14"), \
         patch("server.nutrition.tools.get_request_tz", return_value=ZoneInfo("America/Chicago")), \
         patch("server.nutrition.tools.get_db") as mock_db, \
         patch("server.nutrition.tools.get_daily_meal_totals", return_value={
             "calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "meal_count": 0,
         }):
        mock_conn = MagicMock()
        mock_ride_row = MagicMock()
        mock_ride_row.__getitem__ = lambda self, key: 0
        mock_conn.execute.return_value.fetchone.return_value = mock_ride_row
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.nutrition.tools import get_weekly_summary
        get_weekly_summary()

        # Check that AT TIME ZONE appears in the SQL for rides queries
        ride_queries = [
            c for c in mock_conn.execute.call_args_list
            if "rides" in str(c).lower()
        ]
        assert len(ride_queries) > 0, "Expected at least one rides query"
        for c in ride_queries:
            sql = str(c[0][0])
            assert "AT TIME ZONE" in sql, f"Expected AT TIME ZONE in rides query: {sql}"
            assert "rides.date" not in sql and "WHERE date" not in sql, (
                f"Should not reference rides.date directly: {sql}"
            )


def test_get_caloric_balance_ride_calories_uses_start_time():
    """get_caloric_balance ride calorie query uses AT TIME ZONE, not rides.date."""
    from unittest.mock import patch, MagicMock
    from zoneinfo import ZoneInfo

    with patch("server.nutrition.tools.user_today", return_value="2026-04-14"), \
         patch("server.nutrition.tools.get_request_tz", return_value=ZoneInfo("America/Chicago")), \
         patch("server.nutrition.tools.get_db") as mock_db, \
         patch("server.nutrition.tools.get_daily_meal_totals", return_value={
             "calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "meal_count": 0,
         }), \
         patch("server.services.weight.get_weight_for_date", return_value=75.0):
        mock_conn = MagicMock()
        mock_ride_row = MagicMock()
        mock_ride_row.__getitem__ = lambda self, key: 0
        mock_conn.execute.return_value.fetchone.return_value = mock_ride_row
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.nutrition.tools import get_caloric_balance
        get_caloric_balance()

        # Check that AT TIME ZONE appears in the SQL for rides queries
        ride_queries = [
            c for c in mock_conn.execute.call_args_list
            if "rides" in str(c).lower()
        ]
        assert len(ride_queries) > 0, "Expected at least one rides query"
        for c in ride_queries:
            sql = str(c[0][0])
            assert "AT TIME ZONE" in sql, f"Expected AT TIME ZONE in rides query: {sql}"


def test_get_recent_workouts_uses_start_time():
    """get_recent_workouts queries rides using AT TIME ZONE, not rides.date."""
    from unittest.mock import patch, MagicMock
    from zoneinfo import ZoneInfo

    with patch("server.nutrition.tools.get_request_tz", return_value=ZoneInfo("America/Chicago")) as mock_tz, \
         patch("server.nutrition.tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.nutrition.tools import get_recent_workouts
        get_recent_workouts(days_back=3)

        # Verify AT TIME ZONE is in the SQL
        ride_queries = [
            c for c in mock_conn.execute.call_args_list
            if "rides" in str(c).lower()
        ]
        assert len(ride_queries) == 1
        sql = str(ride_queries[0][0][0])
        assert "AT TIME ZONE" in sql, f"Expected AT TIME ZONE in rides query: {sql}"
        assert "ORDER BY start_time" in sql, f"Expected ORDER BY start_time: {sql}"


def test_get_athlete_nutrition_status_uses_timezone():
    """get_athlete_nutrition_status uses user_today and AT TIME ZONE for rides."""
    from unittest.mock import patch, MagicMock
    from zoneinfo import ZoneInfo

    with patch("server.coaching.tools.user_today", return_value="2026-04-14") as mock_today, \
         patch("server.coaching.tools.get_request_tz", return_value=ZoneInfo("America/Chicago")), \
         patch("server.coaching.tools.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []  # meals
        mock_ride_row = MagicMock()
        mock_ride_row.__getitem__ = lambda self, key: 0
        mock_conn.execute.return_value.fetchone.return_value = mock_ride_row
        mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        from server.coaching.tools import get_athlete_nutrition_status
        result = get_athlete_nutrition_status()

        # Should use user_today() not naive datetime.now()
        mock_today.assert_called_once()
        assert result["date"] == "2026-04-14"

        # Verify ride calorie query uses AT TIME ZONE
        ride_queries = [
            c for c in mock_conn.execute.call_args_list
            if "rides" in str(c).lower() and "total_calories" in str(c).lower()
        ]
        assert len(ride_queries) == 1
        sql = str(ride_queries[0][0][0])
        assert "AT TIME ZONE" in sql, f"Expected AT TIME ZONE in rides query: {sql}"
