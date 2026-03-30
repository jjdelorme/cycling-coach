"""Tests for data ingestion."""

import json
import os
import tempfile

from server.database import init_db, get_db
from server.ingest import (
    parse_ride_json,
    parse_zwo,
    ingest_rides,
    ingest_workouts,
    compute_daily_pmc,
    compute_rolling_best,
)


def test_compute_rolling_best():
    powers = [100] * 60 + [200] * 60
    assert compute_rolling_best(powers, 60)["power"] == 200
    assert compute_rolling_best(powers, 120)["power"] == 150
    assert compute_rolling_best(powers, 200) is None


def test_parse_ride_json(tmp_path):
    ride_data = {
        "session": [
            {
                "start_time": "2025-06-01T10:00:00",
                "total_timer_time": 3600,
                "total_distance": 30000,
                "avg_power": 180,
                "normalized_power": 195,
                "max_power": 500,
                "avg_heart_rate": 145,
                "max_heart_rate": 175,
                "total_ascent": 500,
                "total_descent": 480,
                "total_calories": 800,
                "training_stress_score": 85.5,
                "intensity_factor": 0.78,
                "threshold_power": 250,
                "total_work": 648000,
            }
        ],
        "sport": [{"sport": "cycling", "sub_sport": "mountain", "name": "MTB"}],
        "user_profile": [{"weight": 75.0}],
        "record": [{"timestamp": f"2025-06-01T10:00:{i:02d}", "power": 180, "heart_rate": 145} for i in range(120)],
    }

    filepath = tmp_path / "test_ride.json"
    filepath.write_text(json.dumps(ride_data))

    ride, records, power_bests, laps = parse_ride_json(str(filepath))

    assert ride is not None
    assert ride["date"] == "2025-06-01"
    assert ride["avg_power"] == 180
    assert ride["weight"] == 75.0
    assert len(records) == 120
    assert ride["best_1min_power"] is not None
    assert laps == []


def test_parse_zwo(tmp_path):
    zwo_content = """<?xml version="1.0"?>
<workout_file>
    <name>Z2 Endurance</name>
    <sportType>bike</sportType>
    <workout>
        <Warmup Duration="600" PowerLow="0.4" PowerHigh="0.65"/>
        <SteadyState Duration="2400" Power="0.65"/>
        <Cooldown Duration="300" PowerLow="0.65" PowerHigh="0.4"/>
    </workout>
</workout_file>"""
    filepath = tmp_path / "2025-06-01_z2_endurance.zwo"
    filepath.write_text(zwo_content)

    workout = parse_zwo(str(filepath))
    assert workout is not None
    assert workout["name"] == "Z2 Endurance"
    assert workout["total_duration_s"] == 3300


def test_ingest_rides(tmp_path):
    init_db()
    test_fname = "test_ingest_unique_abc123.json"
    ride_data = {
        "session": [
            {
                "start_time": "2025-06-01T10:00:00",
                "total_timer_time": 3600,
                "avg_power": 180,
                "training_stress_score": 85,
                "threshold_power": 250,
            }
        ],
        "sport": [{"sport": "cycling", "sub_sport": "road"}],
        "user_profile": [{}],
        "record": [{"power": 180, "heart_rate": 145} for _ in range(60)],
    }

    (tmp_path / test_fname).write_text(json.dumps(ride_data))

    with get_db() as conn:
        count = ingest_rides(conn, str(tmp_path))

    assert count == 1

    with get_db() as conn:
        rides = conn.execute("SELECT * FROM rides WHERE filename = %s", (test_fname,)).fetchall()
        assert len(rides) == 1
        assert rides[0]["avg_power"] == 180

    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM ride_records WHERE ride_id IN (SELECT id FROM rides WHERE filename = %s)", (test_fname,))
        conn.execute("DELETE FROM power_bests WHERE ride_id IN (SELECT id FROM rides WHERE filename = %s)", (test_fname,))
        conn.execute("DELETE FROM rides WHERE filename = %s", (test_fname,))


def test_incremental_ingestion(tmp_path):
    """Verify re-running ingestion doesn't create duplicates."""
    init_db()
    ride_data = {
        "session": [{"start_time": "2025-06-01T10:00:00", "total_timer_time": 3600, "avg_power": 180, "threshold_power": 250}],
        "sport": [{"sport": "cycling", "sub_sport": "road"}],
        "user_profile": [{}],
        "record": [],
    }
    (tmp_path / "ride_incr.json").write_text(json.dumps(ride_data))

    with get_db() as conn:
        count1 = ingest_rides(conn, str(tmp_path))
    with get_db() as conn:
        count2 = ingest_rides(conn, str(tmp_path))

    assert count1 == 1
    assert count2 == 0

    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM ride_records WHERE ride_id IN (SELECT id FROM rides WHERE filename = 'ride_incr.json')")
        conn.execute("DELETE FROM power_bests WHERE ride_id IN (SELECT id FROM rides WHERE filename = 'ride_incr.json')")
        conn.execute("DELETE FROM rides WHERE filename = 'ride_incr.json'")


def test_compute_daily_pmc():
    """Verify compute_daily_pmc produces results from existing ride data."""
    init_db()
    with get_db() as conn:
        compute_daily_pmc(conn)
        metrics = conn.execute("SELECT * FROM daily_metrics ORDER BY date LIMIT 5").fetchall()

    assert len(metrics) > 0
    assert metrics[0]["ctl"] >= 0
    assert metrics[0]["atl"] >= 0
