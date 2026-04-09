"""Tests for planning tools."""

import pytest

from server.database import get_db
from server.coaching.planning_tools import (
    set_workout_coach_notes,
    replace_workout,
    generate_week_from_spec,
)


# Tests for generate_week_from_spec
def test_generate_week_from_spec_template_mode(db_conn):
    """Template mode creates a workout with agent-provided coach_notes."""
    result = generate_week_from_spec([
        {
            "date": "2099-09-01",
            "workout_type": "z2_endurance",
            "duration_minutes": 60,
            "coach_notes": "TSB is +8 — good form. Keep HR under 135, cadence 90+.",
        }
    ])
    assert result["status"] == "success"
    assert result["total_workouts"] == 1
    row = db_conn.execute(
        "SELECT name, workout_xml, coach_notes FROM planned_workouts WHERE date = '2099-09-01'"
    ).fetchone()
    assert row is not None
    assert row["workout_xml"] is not None
    assert row["coach_notes"] == "TSB is +8 — good form. Keep HR under 135, cadence 90+."


def test_generate_week_from_spec_custom_mode(db_conn):
    """Custom mode creates a workout from steps with agent-provided coach_notes."""
    steps = [
        {"type": "Warmup", "duration_seconds": 600, "power_low": 0.40, "power_high": 0.75},
        {"type": "SteadyState", "duration_seconds": 1800, "power": 0.90},
        {"type": "Cooldown", "duration_seconds": 300, "power_low": 0.65, "power_high": 0.40},
    ]
    result = generate_week_from_spec([
        {
            "date": "2099-09-02",
            "name": "Sweet Spot Block",
            "steps": steps,
            "coach_notes": "After 3 easy days, TSB at -5. This is your only quality session this week.",
        }
    ])
    assert result["status"] == "success"
    assert result["total_workouts"] == 1
    row = db_conn.execute(
        "SELECT name, coach_notes FROM planned_workouts WHERE date = '2099-09-02'"
    ).fetchone()
    assert row is not None
    assert row["coach_notes"] == "After 3 easy days, TSB at -5. This is your only quality session this week."


def test_generate_week_from_spec_rest_day(db_conn):
    """A rest-day spec (no workout_type, name, or steps) clears that date."""
    # Pre-insert a workout so we can verify it gets cleared
    db_conn.execute(
        "INSERT INTO planned_workouts (date, name, sport, total_duration_s) VALUES (%s, %s, %s, %s)",
        ("2099-09-03", "Old Workout", "bike", 3600),
    )
    db_conn.commit()
    result = generate_week_from_spec([{"date": "2099-09-03"}])
    assert result["status"] == "success"
    assert "2099-09-03" in result["rest_days"]
    row = db_conn.execute(
        "SELECT id FROM planned_workouts WHERE date = '2099-09-03'"
    ).fetchone()
    assert row is None


def test_generate_week_from_spec_mixed(db_conn):
    """Mixed week: template + custom + rest returns correct counts."""
    steps = [
        {"type": "Warmup", "duration_seconds": 600, "power_low": 0.40, "power_high": 0.75},
        {"type": "SteadyState", "duration_seconds": 2400, "power": 0.75},
        {"type": "Cooldown", "duration_seconds": 300, "power_low": 0.65, "power_high": 0.40},
    ]
    result = generate_week_from_spec([
        {"date": "2099-10-06", "workout_type": "recovery", "duration_minutes": 45, "coach_notes": "TSB -22, keep it truly easy."},
        {"date": "2099-10-07", "name": "Z2 Long", "steps": steps, "coach_notes": "Aerobic base work."},
        {"date": "2099-10-08"},  # rest
        {"date": "2099-10-09", "workout_type": "z2_endurance", "duration_minutes": 90, "coach_notes": "Back-to-back Z2."},
    ])
    assert result["total_workouts"] == 3
    assert len(result["rest_days"]) == 1
    assert len(result["errors"]) == 0


def test_generate_week_from_spec_unknown_type(db_conn):
    """Unknown workout_type goes into errors; other specs still succeed."""
    result = generate_week_from_spec([
        {"date": "2099-11-01", "workout_type": "totally_fake_workout"},
        {"date": "2099-11-02", "workout_type": "z2_endurance", "duration_minutes": 60, "coach_notes": "Good aerobic day."},
    ])
    assert result["status"] == "partial"
    assert result["total_workouts"] == 1
    assert len(result["errors"]) == 1
    assert "2099-11-01" in result["errors"][0]["error"] or "totally_fake_workout" in result["errors"][0]["error"]


def test_replan_missed_day():
    from server.coaching.planning_tools import replan_missed_day

    # Set up a workout to move
    generate_week_from_spec([
        {"date": "2026-06-09", "workout_type": "z2_endurance", "duration_minutes": 60, "coach_notes": "Endurance work."},
    ])

    # Replan the workout to Wednesday
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
            "UPDATE periodization_phases SET end_date = %s WHERE name = 'Base Rebuild'",
            (original_end,),
        )


def test_adjust_phase_not_found():
    from server.coaching.planning_tools import adjust_phase

    result = adjust_phase("Nonexistent Phase", "2026-06-01", "test")
    assert result["status"] == "error"


def test_get_week_summary():
    from server.coaching.planning_tools import get_week_summary

    result = get_week_summary("2026-03-16")
    assert "planned_workouts" in result
    assert "actual_rides" in result
    assert result["rides_count"] > 0  # Should have rides in this week


# Tests for set_workout_coach_notes
def test_set_workout_coach_notes_success(db_conn):
    """set_workout_coach_notes persists notes to the DB."""
    db_conn.execute(
        "INSERT INTO planned_workouts (date, name, sport, total_duration_s) VALUES (%s, %s, %s, %s)",
        ("2099-06-01", "Test Ride", "bike", 3600),
    )
    result = set_workout_coach_notes("2099-06-01", "Focus on Z2 cadence, RPE 3")
    assert result["status"] == "success"
    row = db_conn.execute(
        "SELECT coach_notes FROM planned_workouts WHERE date = '2099-06-01'"
    ).fetchone()
    assert row["coach_notes"] == "Focus on Z2 cadence, RPE 3"


def test_set_workout_coach_notes_no_workout(db_conn):
    """set_workout_coach_notes returns error for missing workout."""
    result = set_workout_coach_notes("2099-12-31", "some notes")
    assert result["status"] == "error"
    assert "No planned workout" in result["message"]


def test_set_workout_coach_notes_overwrites_existing(db_conn):
    """set_workout_coach_notes overwrites, not appends."""
    db_conn.execute(
        "INSERT INTO planned_workouts (date, name, sport, total_duration_s, coach_notes) VALUES (%s, %s, %s, %s, %s)",
        ("2099-06-02", "Test Ride", "bike", 3600, "old note"),
    )
    set_workout_coach_notes("2099-06-02", "new note")
    row = db_conn.execute(
        "SELECT coach_notes FROM planned_workouts WHERE date = '2099-06-02'"
    ).fetchone()
    assert row["coach_notes"] == "new note"


# Tests for replace_workout
def test_replace_workout_template_mode(db_conn):
    """replace_workout template mode creates a workout; coach_notes are NULL (agent sets them separately)."""
    result = replace_workout("2099-07-01", workout_type="z2_endurance", duration_minutes=60)
    assert result["status"] == "success"
    assert "coach_notes_hint" in result  # agent is told to call set_workout_coach_notes
    row = db_conn.execute(
        "SELECT name, workout_xml, coach_notes FROM planned_workouts WHERE date = '2099-07-01'"
    ).fetchone()
    assert row is not None
    assert row["workout_xml"] is not None
    assert row["coach_notes"] is None  # notes are NOT auto-populated; agent must set them


def test_replace_workout_custom_mode_stores_description_as_coach_notes(db_conn):
    """replace_workout custom mode stores description as coach_notes."""
    steps = [
        {"type": "Warmup", "duration_seconds": 600, "power_low": 0.40, "power_high": 0.75},
        {"type": "SteadyState", "duration_seconds": 1800, "power": 0.90},
        {"type": "Cooldown", "duration_seconds": 300, "power_low": 0.65, "power_high": 0.40},
    ]
    result = replace_workout(
        "2099-07-02",
        name="3x8 Threshold",
        description="Hold 90% FTP, cadence 85-90",
        steps=steps,
    )
    assert result["status"] == "success"
    row = db_conn.execute(
        "SELECT coach_notes FROM planned_workouts WHERE date = '2099-07-02'"
    ).fetchone()
    assert row["coach_notes"] == "Hold 90% FTP, cadence 85-90"


def test_replace_workout_rest_mode(db_conn):
    """replace_workout rest mode removes the workout."""
    db_conn.execute(
        "INSERT INTO planned_workouts (date, name, sport, total_duration_s) VALUES (%s, %s, %s, %s)",
        ("2099-07-03", "Existing Workout", "bike", 3600),
    )
    db_conn.commit()
    result = replace_workout("2099-07-03", workout_type="rest")
    assert result["status"] == "success"
    assert result["action"] == "removed"
    assert result["previous_workout"] == "Existing Workout"
    row = db_conn.execute(
        "SELECT id FROM planned_workouts WHERE date = '2099-07-03'"
    ).fetchone()
    assert row is None


def test_replace_workout_unknown_type(db_conn):
    """replace_workout returns error for unknown workout type."""
    result = replace_workout("2099-07-04", workout_type="totally_fake_workout")
    assert result["status"] == "error"
    assert "Unknown workout type" in result["message"]


# Tests for generate_week_from_spec coach_notes
def test_generate_week_from_spec_coach_notes_persisted(db_conn):
    """generate_week_from_spec persists agent-provided coach_notes to the DB."""
    result = generate_week_from_spec([
        {
            "date": "2099-08-04",
            "workout_type": "z2_endurance",
            "duration_minutes": 90,
            "coach_notes": "TSB is +5 — legs are fresh. Aim for HR 125-135, cadence 90+.",
        },
        {
            "date": "2099-08-05",
            "workout_type": "recovery",
            "duration_minutes": 45,
            "coach_notes": "Easy flush after yesterday. No power targets — just spin.",
        },
    ])
    assert result["status"] == "success"
    rows = db_conn.execute(
        "SELECT date, name, coach_notes FROM planned_workouts WHERE date >= '2099-08-04' AND date <= '2099-08-05'"
    ).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["coach_notes"] is not None, f"coach_notes is NULL for {row['date']} {row['name']}"
        assert len(row["coach_notes"]) > 10, f"coach_notes too short for {row['date']}"
