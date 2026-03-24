"""Tests for planning tools."""

import os
import pytest

from server.database import init_db, get_db

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "coach.db")


@pytest.fixture(autouse=True)
def setup_db():
    if not os.path.exists(DB_PATH):
        pytest.skip("Database not found")
    os.environ["COACH_DB_PATH"] = DB_PATH


def test_generate_weekly_plan():
    from server.coaching.planning_tools import generate_weekly_plan

    result = generate_weekly_plan("2026-04-06", focus="base", hours=10)
    assert result["status"] == "success"
    assert len(result["workouts"]) > 0
    assert result["focus"] == "base"

    # Verify workouts were actually saved
    with get_db() as conn:
        saved = conn.execute(
            "SELECT * FROM planned_workouts WHERE date >= '2026-04-06' AND date <= '2026-04-12'"
        ).fetchall()
    assert len(saved) > 0


def test_generate_build_plan():
    from server.coaching.planning_tools import generate_weekly_plan

    result = generate_weekly_plan("2026-05-04", focus="build", hours=13)
    assert result["status"] == "success"
    workouts = result["workouts"]
    names = [w["name"] for w in workouts]
    # Build plan should include threshold and VO2max
    assert "2x20 Threshold" in names
    assert "4x4min VO2max" in names


def test_generate_recovery_plan():
    from server.coaching.planning_tools import generate_weekly_plan

    result = generate_weekly_plan("2026-04-27", focus="recovery", hours=5)
    assert result["status"] == "success"
    assert len(result["workouts"]) <= 4  # Recovery weeks are lighter


def test_replan_missed_day():
    from server.coaching.planning_tools import generate_weekly_plan, replan_missed_day

    # First generate a plan
    generate_weekly_plan("2026-06-08", focus="build", hours=12)

    # Replan Tuesday to Wednesday
    result = replan_missed_day("2026-06-09", "2026-06-10")
    assert result["status"] == "success"
    assert len(result["workouts_moved"]) > 0


def test_replan_no_workout():
    from server.coaching.planning_tools import replan_missed_day

    result = replan_missed_day("2099-01-01", "2099-01-02")
    assert result["status"] == "no_workout"


def test_adjust_phase():
    from server.coaching.planning_tools import adjust_phase

    # Get original end date first
    with get_db() as conn:
        phase = conn.execute(
            "SELECT end_date FROM periodization_phases WHERE name = 'Base Rebuild'"
        ).fetchone()
        original_end = phase["end_date"]

    result = adjust_phase("Base Rebuild", "2026-05-04", "Extended due to illness recovery")
    assert result["status"] == "success"
    assert result["new_end_date"] == "2026-05-04"

    # Restore original
    with get_db() as conn:
        conn.execute(
            "UPDATE periodization_phases SET end_date = ? WHERE name = 'Base Rebuild'",
            (original_end,),
        )


def test_adjust_phase_not_found():
    from server.coaching.planning_tools import adjust_phase

    result = adjust_phase("Nonexistent Phase", "2026-06-01", "test")
    assert result["status"] == "error"


def test_get_week_summary():
    from server.coaching.planning_tools import get_week_summary

    result = get_week_summary("2025-08-15")
    assert "planned_workouts" in result
    assert "actual_rides" in result
    assert result["rides_count"] > 0  # Should have rides in August 2025
