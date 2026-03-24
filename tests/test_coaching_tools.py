"""Tests for coaching agent tools."""

import os
import pytest

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "coach.db")


@pytest.fixture(autouse=True)
def setup_db():
    if not os.path.exists(DB_PATH):
        pytest.skip("Database not found")
    os.environ["COACH_DB_PATH"] = DB_PATH


def test_get_pmc_metrics():
    from server.coaching.tools import get_pmc_metrics
    result = get_pmc_metrics()
    assert "ctl" in result
    assert "atl" in result
    assert "tsb" in result
    assert result["ctl"] >= 0


def test_get_pmc_metrics_by_date():
    from server.coaching.tools import get_pmc_metrics
    result = get_pmc_metrics("2025-10-26")
    assert result["ctl"] > 80  # Should be near peak


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
    assert result["rides"] > 200
    assert result["hours"] > 400


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
