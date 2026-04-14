"""Unit tests for meal user_notes and analyze features."""


def test_meal_summary_has_user_notes_field():
    """MealSummary schema includes user_notes."""
    from server.models.schemas import MealSummary

    s = MealSummary(
        id=1, date="2024-01-01", logged_at="2024-01-01T12:00:00",
        description="test meal", total_calories=500,
        total_protein_g=30, total_carbs_g=50, total_fat_g=20,
        confidence="high", user_notes="my personal note",
    )
    assert s.user_notes == "my personal note"


def test_meal_summary_user_notes_defaults_none():
    """MealSummary.user_notes defaults to None."""
    from server.models.schemas import MealSummary

    s = MealSummary(
        id=1, date="2024-01-01", logged_at="2024-01-01T12:00:00",
        description="test meal", total_calories=500,
        total_protein_g=30, total_carbs_g=50, total_fat_g=20,
        confidence="high",
    )
    assert s.user_notes is None


def test_meal_summary_has_agent_notes_field():
    """MealSummary schema includes agent_notes (promoted from MealDetail)."""
    from server.models.schemas import MealSummary

    s = MealSummary(
        id=1, date="2024-01-01", logged_at="2024-01-01T12:00:00",
        description="test meal", total_calories=500,
        total_protein_g=30, total_carbs_g=50, total_fat_g=20,
        confidence="high", agent_notes="Good protein ratio.",
    )
    assert s.agent_notes == "Good protein ratio."


def test_meal_summary_agent_notes_defaults_none():
    """MealSummary.agent_notes defaults to None."""
    from server.models.schemas import MealSummary

    s = MealSummary(
        id=1, date="2024-01-01", logged_at="2024-01-01T12:00:00",
        description="test meal", total_calories=500,
        total_protein_g=30, total_carbs_g=50, total_fat_g=20,
        confidence="high",
    )
    assert s.agent_notes is None


def test_meal_detail_inherits_user_and_agent_notes():
    """MealDetail inherits user_notes and agent_notes from MealSummary."""
    from server.models.schemas import MealDetail

    d = MealDetail(
        id=1, date="2024-01-01", logged_at="2024-01-01T12:00:00",
        description="test meal", total_calories=500,
        total_protein_g=30, total_carbs_g=50, total_fat_g=20,
        confidence="high", user_notes="note", agent_notes="analysis",
    )
    assert d.user_notes == "note"
    assert d.agent_notes == "analysis"


def test_meal_update_request_accepts_user_notes():
    """MealUpdateRequest includes user_notes field."""
    from server.models.schemas import MealUpdateRequest

    req = MealUpdateRequest(user_notes="updated note")
    assert req.user_notes == "updated note"
    assert req.total_calories is None  # other fields untouched


def test_meal_update_request_user_notes_defaults_none():
    """MealUpdateRequest.user_notes defaults to None."""
    from server.models.schemas import MealUpdateRequest

    req = MealUpdateRequest(total_calories=600)
    assert req.user_notes is None


def test_build_meal_plan_day_includes_user_notes():
    """_build_meal_plan_day includes user_notes and agent_notes in actual meals."""
    from server.routers.nutrition import _build_meal_plan_day

    actual_row = {
        "id": 1, "date": "2024-01-01", "logged_at": "2024-01-01T12:00:00",
        "meal_type": "lunch", "description": "Chicken salad",
        "total_calories": 500, "total_protein_g": 40,
        "total_carbs_g": 30, "total_fat_g": 15,
        "confidence": "high", "photo_gcs_path": None,
        "edited_by_user": False, "user_notes": "Was delicious",
        "agent_notes": "Good balance",
    }

    result = _build_meal_plan_day("2024-01-01", [], [actual_row])

    actual = result["actual"][0]
    assert actual["user_notes"] == "Was delicious"
    assert actual["agent_notes"] == "Good balance"


def test_build_meal_plan_day_handles_missing_notes():
    """_build_meal_plan_day handles meals without user_notes/agent_notes."""
    from server.routers.nutrition import _build_meal_plan_day

    actual_row = {
        "id": 1, "date": "2024-01-01", "logged_at": "2024-01-01T12:00:00",
        "meal_type": None, "description": "Toast",
        "total_calories": 200, "total_protein_g": 5,
        "total_carbs_g": 30, "total_fat_g": 8,
        "confidence": "medium", "photo_gcs_path": None,
        "edited_by_user": False,
    }

    result = _build_meal_plan_day("2024-01-01", [], [actual_row])

    actual = result["actual"][0]
    assert actual["user_notes"] is None
    assert actual["agent_notes"] is None


def test_migration_file_is_idempotent():
    """Migration 0005 uses IF NOT EXISTS for idempotency."""
    with open("migrations/0005_meal_user_notes.sql") as f:
        content = f.read()
    assert "IF NOT EXISTS" in content or "ADD COLUMN IF NOT EXISTS" in content


def test_analyze_endpoint_registered():
    """POST /api/nutrition/meals/{meal_id}/analyze route is registered."""
    from server.routers.nutrition import router

    routes = {(r.path, tuple(sorted(r.methods))) for r in router.routes}
    assert ("/api/nutrition/meals/{meal_id}/analyze", ("POST",)) in routes
