"""Tests for coaching agent tools."""

import pytest


def test_get_pmc_metrics():
    from server.coaching.tools import get_pmc_metrics
    result = get_pmc_metrics()
    assert "ctl" in result
    assert "atl" in result
    assert "tsb" in result
    assert result["ctl"] >= 0


def test_get_pmc_metrics_by_date():
    from server.coaching.tools import get_pmc_metrics
    result = get_pmc_metrics("2026-03-21")
    assert result["ctl"] > 40  # Should have meaningful fitness


def test_get_recent_rides():
    from server.coaching.tools import get_recent_rides
    result = get_recent_rides(days_back=365)
    assert len(result) > 0
    assert "date" in result[0]
    assert "tss" in result[0]


def test_get_upcoming_workouts():
    from server.coaching.tools import get_upcoming_workouts
    # May return empty if no upcoming workouts
    result = get_upcoming_workouts(days_ahead=365)
    assert isinstance(result, list)


def test_get_power_bests():
    from server.coaching.tools import get_power_bests
    result = get_power_bests()
    assert "1min" in result
    assert "5min" in result
    assert "20min" in result
    assert result["20min"]["power"] > 200


def test_get_training_summary():
    from server.coaching.tools import get_training_summary
    result = get_training_summary("season")
    assert result["rides"] > 0
    assert result["hours"] > 0


def test_get_ftp_history():
    from server.coaching.tools import get_ftp_history
    result = get_ftp_history()
    assert len(result) > 0
    assert result[0]["ftp"] > 200


def test_get_periodization_status():
    from server.coaching.tools import get_periodization_status
    result = get_periodization_status()
    assert "current_phase" in result
    assert "all_phases" in result
    assert len(result["all_phases"]) == 5


def test_get_recent_rides_includes_ride_id():
    from server.coaching.tools import get_recent_rides
    result = get_recent_rides(days_back=365)
    assert len(result) > 0
    assert "ride_id" in result[0]
    assert isinstance(result[0]["ride_id"], int)


# --- Ride analysis tools ---

def _get_test_date_with_power():
    """Find a date where the longest ride has power data and ride_records.

    get_ride_analysis resolves date -> ride_id by picking the longest ride, so
    we must return a date where that longest ride actually has power records.
    """
    from server.database import get_db
    with get_db() as conn:
        # Sub-query finds the longest ride per date; outer filter keeps only
        # dates where that longest ride has power records.
        row = conn.execute(
            """SELECT (r.start_time AT TIME ZONE 'UTC')::DATE::TEXT AS date
               FROM rides r
               WHERE r.avg_power > 0 AND r.duration_s > 1800 AND r.has_power_data = TRUE
                 AND EXISTS (SELECT 1 FROM ride_records rr WHERE rr.ride_id = r.id AND rr.power > 0)
                 AND NOT EXISTS (
                     SELECT 1 FROM rides r2
                     WHERE (r2.start_time AT TIME ZONE 'UTC')::DATE = (r.start_time AT TIME ZONE 'UTC')::DATE
                       AND r2.duration_s > r.duration_s
                 )
               ORDER BY r.start_time DESC LIMIT 1"""
        ).fetchone()
    return row["date"] if row else None


def test_get_ride_analysis_basic():
    from server.coaching.tools import get_ride_analysis
    date = _get_test_date_with_power()
    if not date:
        pytest.skip("No ride with power data available")
    result = get_ride_analysis(date)
    assert "error" not in result
    assert result["has_power"] is True
    assert result["ride_id"] > 0
    assert len(result["best_efforts"]) > 0
    assert result["power_zones"] is not None
    # Zone percentages should sum to ~100%
    pct_sum = sum(z["pct"] for z in result["power_zones"]["zones"])
    assert 95 <= pct_sum <= 105
    assert result["metrics"]["avg_power"] > 0


def test_get_ride_analysis_no_ride():
    from server.coaching.tools import get_ride_analysis
    result = get_ride_analysis("2020-01-01")
    assert "error" in result


def test_get_ride_analysis_short_ride():
    """Verify 60min best effort is omitted for rides shorter than 60 min."""
    from server.coaching.tools import get_ride_analysis
    date = _get_test_date_with_power()
    if not date:
        pytest.skip("No ride with power data available")
    result = get_ride_analysis(date)
    if "error" in result:
        pytest.skip("Could not analyze ride")
    durations = [e["duration_s"] for e in result["best_efforts"]]
    # If ride is < 3600s, 60min should not be present
    if result["duration_s"] < 3600:
        assert 3600 not in durations


def test_get_ride_segments_basic():
    from server.coaching.tools import get_ride_segments
    date = _get_test_date_with_power()
    if not date:
        pytest.skip("No ride with power data available")
    result = get_ride_segments(date)
    assert "error" not in result
    assert result["segment_count"] > 0
    seg = result["segments"][0]
    assert "avg_power" in seg
    assert "avg_hr" in seg
    assert seg["segment"] == 1
    assert seg["start_elapsed_s"] == 0


def test_get_ride_segments_clamps_duration():
    from server.coaching.tools import get_ride_segments
    date = _get_test_date_with_power()
    if not date:
        pytest.skip("No ride with power data available")
    result = get_ride_segments(date, segment_duration_s=10)
    assert result["segment_duration_s"] == 60  # clamped to minimum


def test_get_ride_records_window_basic():
    from server.coaching.tools import get_ride_records_window
    date = _get_test_date_with_power()
    if not date:
        pytest.skip("No ride with power data available")
    result = get_ride_records_window(date, start_s=0, end_s=60)
    assert "error" not in result
    assert result["record_count"] == 60
    assert result["window_start_s"] == 0
    rec = result["records"][0]
    assert "power" in rec
    assert "heart_rate" in rec
    assert rec["elapsed_s"] == 0


def test_get_ride_records_window_caps_at_600():
    from server.coaching.tools import get_ride_records_window
    date = _get_test_date_with_power()
    if not date:
        pytest.skip("No ride with power data available")
    result = get_ride_records_window(date, start_s=0, end_s=5000)
    assert result["record_count"] <= 600


def test_get_ride_records_window_invalid_range():
    from server.coaching.tools import get_ride_records_window
    result = get_ride_records_window("2025-06-01", start_s=100, end_s=50)
    assert "error" in result


def test_get_power_curve_all_time():
    from server.coaching.tools import get_power_curve
    result = get_power_curve()
    assert "bests" in result
    assert len(result["bests"]) > 0
    durations = {b["duration_s"] for b in result["bests"]}
    assert 60 in durations  # 1min should exist
    assert 300 in durations  # 5min should exist


def test_get_power_curve_date_range():
    from server.coaching.tools import get_power_curve
    result = get_power_curve(start_date="2025-06-01", end_date="2025-06-30")
    assert "bests" in result
    for b in result["bests"]:
        assert "2025-06-01" <= b["date"] <= "2025-06-30"


# --- Athlete status tool ---

def test_get_athlete_status_keys():
    from server.coaching.tools import get_athlete_status
    result = get_athlete_status()
    expected_keys = {"ftp", "weight_kg", "weight_lbs", "w_kg", "lthr", "max_hr",
                     "resting_hr", "age", "gender", "ctl", "atl", "tsb", "as_of_date"}
    assert expected_keys == set(result.keys())


def test_get_athlete_status_conversions():
    from server.coaching.tools import get_athlete_status
    result = get_athlete_status()
    if result["weight_kg"] and float(result["weight_kg"]) > 0:
        weight_kg = float(result["weight_kg"])
        assert abs(result["weight_lbs"] - weight_kg * 2.20462) < 0.2
        ftp = result["ftp"]
        if ftp > 0:
            assert abs(result["w_kg"] - ftp / weight_kg) < 0.01


def test_get_athlete_status_pmc_data():
    from server.coaching.tools import get_athlete_status
    result = get_athlete_status()
    # Should have PMC data from the test database
    assert result["ctl"] is not None
    assert result["ctl"] >= 0
    assert result["atl"] is not None
    assert result["tsb"] is not None
    assert result["as_of_date"] is not None


# --- Planned workout comparison tool ---

def test_get_planned_workout_for_ride_no_data():
    from server.coaching.tools import get_planned_workout_for_ride
    result = get_planned_workout_for_ride("2020-01-01")
    assert result["date"] == "2020-01-01"
    assert result["planned"] is None
    assert result["actual"] is None
    assert result["comparison"] is None


def test_get_planned_workout_for_ride_structure():
    from server.coaching.tools import get_planned_workout_for_ride
    # Use a date we know has rides from the test data
    date = _get_test_date_with_power()
    if not date:
        pytest.skip("No ride with power data available")
    result = get_planned_workout_for_ride(date)
    assert result["date"] == date
    assert result["actual"] is not None
    assert "ride_id" in result["actual"]
    assert "duration_min" in result["actual"]
    assert "tss" in result["actual"]


def test_get_upcoming_workouts_returns_coach_notes_field(db_conn):
    """get_upcoming_workouts includes coach_notes in results."""
    from datetime import datetime, timedelta
    from server.coaching.tools import get_upcoming_workouts
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    # Pre-clean any leftover rows from previous test runs for this date+name,
    # then commit so the fresh insert is visible to get_upcoming_workouts's own
    # connection (READ COMMITTED isolation).
    db_conn.execute(
        "DELETE FROM planned_workouts WHERE date = %s AND name = %s",
        (tomorrow, "test_get_upcoming_workouts_coach_notes"),
    )
    db_conn.execute(
        "INSERT INTO planned_workouts (date, name, sport, total_duration_s, coach_notes) VALUES (%s, %s, %s, %s, %s)",
        (tomorrow, "test_get_upcoming_workouts_coach_notes", "bike", 3600, "Ride easy, RPE 3"),
    )
    db_conn.commit()
    results = get_upcoming_workouts(days_ahead=7)
    matching = [r for r in results if str(r["date"]) == tomorrow and r["name"] == "test_get_upcoming_workouts_coach_notes"]
    assert len(matching) == 1
    assert matching[0]["coach_notes"] == "Ride easy, RPE 3"


def test_get_upcoming_workouts_coach_notes_none_when_unset(db_conn):
    """get_upcoming_workouts returns None coach_notes when unset."""
    from datetime import datetime, timedelta
    from server.coaching.tools import get_upcoming_workouts
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    # Pre-clean any leftover rows from previous test runs for this date+name,
    # then commit so the fresh insert is visible to get_upcoming_workouts's own
    # connection (READ COMMITTED isolation).
    db_conn.execute(
        "DELETE FROM planned_workouts WHERE date = %s AND name = %s",
        (day_after, "test_get_upcoming_workouts_no_notes"),
    )
    db_conn.execute(
        "INSERT INTO planned_workouts (date, name, sport, total_duration_s) VALUES (%s, %s, %s, %s)",
        (day_after, "test_get_upcoming_workouts_no_notes", "bike", 3600),
    )
    db_conn.commit()
    results = get_upcoming_workouts(days_ahead=7)
    matching = [r for r in results if str(r["date"]) == day_after and r["name"] == "test_get_upcoming_workouts_no_notes"]
    assert len(matching) == 1
    assert matching[0]["coach_notes"] is None


def test_best_effort_index_tracking():
    """Verify start_offset_s points to the actual best window."""
    from server.coaching.tools import get_ride_analysis, get_ride_records_window
    date = _get_test_date_with_power()
    if not date:
        pytest.skip("No ride with power data available")
    analysis = get_ride_analysis(date)
    if "error" in analysis or not analysis["best_efforts"]:
        pytest.skip("No best efforts available")
    # Check the 1min best effort
    one_min = next((e for e in analysis["best_efforts"] if e["duration_s"] == 60), None)
    if not one_min:
        pytest.skip("No 1min best effort")
    # Fetch raw records at the reported offset
    window = get_ride_records_window(date, start_s=one_min["start_offset_s"],
                                     end_s=one_min["start_offset_s"] + 60)
    if "error" in window:
        pytest.skip("Could not fetch window")
    powers = [r["power"] for r in window["records"] if r["power"] is not None]
    if powers:
        avg = round(sum(powers) / len(powers))
        # Should be close to reported best (within 1W due to rounding)
        assert abs(avg - one_min["avg_power"]) <= 1
