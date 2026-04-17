"""Tests for lap data extraction, GPS conversion, backfill, and API."""

import json
import pytest

from server.database import get_db
from server.ingest import parse_ride_json, _semicircles_to_degrees, ingest_rides, backfill_laps


def _make_ride_json(laps=None, records=None):
    """Build a minimal ride JSON dict with optional laps."""
    data = {
        "session": [{
            "start_time": "2025-06-01T10:00:00",
            "total_timer_time": 3600,
            "avg_power": 200,
            "threshold_power": 250,
        }],
        "sport": [{"sport": "cycling", "sub_sport": "road"}],
        "user_profile": [{"weight": 75.0}],
        "record": records or [{"timestamp": f"2025-06-01T10:00:{i:02d}", "power": 200, "heart_rate": 140} for i in range(60)],
    }
    if laps is not None:
        data["lap"] = laps
    return data


class TestGPSConversion:
    def test_semicircles_to_degrees(self):
        # Known value: ~47.6 degrees N
        semi = 568459880
        deg = _semicircles_to_degrees(semi)
        assert abs(deg - 47.6) < 0.5

    def test_none_passthrough(self):
        assert _semicircles_to_degrees(None) is None

    def test_already_degrees(self):
        assert _semicircles_to_degrees(47.6) == 47.6

    def test_zero(self):
        assert _semicircles_to_degrees(0) == 0


class TestLapExtraction:
    def test_single_lap(self, tmp_path):
        laps = [{
            "message_index": 0,
            "start_time": "2025-06-01T10:00:00",
            "total_timer_time": 3600.0,
            "total_elapsed_time": 3650.0,
            "total_distance": 30000.0,
            "avg_power": 200,
            "normalized_power": 210,
            "max_power": 450,
            "avg_heart_rate": 145,
            "max_heart_rate": 172,
            "avg_cadence": 88,
            "max_cadence": 105,
            "enhanced_avg_speed": 8.3,
            "enhanced_max_speed": 12.5,
            "total_ascent": 300,
            "total_descent": 280,
            "total_calories": 800,
            "total_work": 720000,
            "intensity": "active",
            "lap_trigger": "manual",
        }]
        filepath = tmp_path / "ride.json"
        filepath.write_text(json.dumps(_make_ride_json(laps=laps)))

        _ride, _records, _pb, lap_rows = parse_ride_json(str(filepath))
        assert len(lap_rows) == 1
        lap = lap_rows[0]
        assert lap["lap_index"] == 0
        assert lap["avg_power"] == 200
        assert lap["avg_hr"] == 145
        assert lap["intensity"] == "active"
        assert lap["lap_trigger"] == "manual"
        assert lap["total_timer_time"] == 3600.0

    def test_multiple_laps(self, tmp_path):
        laps = [
            {"message_index": 0, "intensity": "active", "lap_trigger": "manual",
             "total_timer_time": 600, "avg_power": 150, "wkt_step_index": 0},
            {"message_index": 1, "intensity": "active", "lap_trigger": "manual",
             "total_timer_time": 1200, "avg_power": 250, "wkt_step_index": 1},
            {"message_index": 2, "intensity": "active", "lap_trigger": "session_end",
             "total_timer_time": 300, "avg_power": 120, "wkt_step_index": 2},
        ]
        filepath = tmp_path / "ride.json"
        filepath.write_text(json.dumps(_make_ride_json(laps=laps)))

        _ride, _records, _pb, lap_rows = parse_ride_json(str(filepath))
        assert len(lap_rows) == 3
        assert [l["lap_index"] for l in lap_rows] == [0, 1, 2]
        assert lap_rows[1]["avg_power"] == 250
        assert lap_rows[1]["wkt_step_index"] == 1

    def test_no_laps(self, tmp_path):
        filepath = tmp_path / "ride.json"
        filepath.write_text(json.dumps(_make_ride_json()))

        _ride, _records, _pb, lap_rows = parse_ride_json(str(filepath))
        assert lap_rows == []

    def test_numeric_intensity_coerced_to_none(self, tmp_path):
        laps = [{"message_index": 0, "intensity": 5, "total_timer_time": 600}]
        filepath = tmp_path / "ride.json"
        filepath.write_text(json.dumps(_make_ride_json(laps=laps)))

        _ride, _records, _pb, lap_rows = parse_ride_json(str(filepath))
        assert lap_rows[0]["intensity"] is None

    def test_numeric_lap_trigger_coerced_to_none(self, tmp_path):
        laps = [{"message_index": 0, "lap_trigger": 21, "total_timer_time": 600}]
        filepath = tmp_path / "ride.json"
        filepath.write_text(json.dumps(_make_ride_json(laps=laps)))

        _ride, _records, _pb, lap_rows = parse_ride_json(str(filepath))
        assert lap_rows[0]["lap_trigger"] is None

    def test_lap_gps_conversion(self, tmp_path):
        semi_lat = 568459880  # ~47.6 degrees
        semi_lon = -1469380198  # ~-122.3 degrees
        laps = [{
            "message_index": 0,
            "total_timer_time": 600,
            "start_position_lat": semi_lat,
            "start_position_long": semi_lon,
            "end_position_lat": semi_lat + 1000,
            "end_position_long": semi_lon + 1000,
        }]
        filepath = tmp_path / "ride.json"
        filepath.write_text(json.dumps(_make_ride_json(laps=laps)))

        _ride, _records, _pb, lap_rows = parse_ride_json(str(filepath))
        lap = lap_rows[0]
        assert -90 <= lap["start_lat"] <= 90
        assert -180 <= lap["start_lon"] <= 180
        assert -90 <= lap["end_lat"] <= 90
        assert -180 <= lap["end_lon"] <= 180


class TestBackfillLaps:
    def test_backfill_laps(self, tmp_path):
        """Ingest ride, delete laps, backfill, verify restored."""

        laps = [
            {"message_index": 0, "intensity": "active", "total_timer_time": 600, "avg_power": 150},
            {"message_index": 1, "intensity": "active", "total_timer_time": 1200, "avg_power": 250},
        ]
        fname = "test_backfill_laps_unique.json"
        filepath = tmp_path / fname
        filepath.write_text(json.dumps(_make_ride_json(laps=laps)))

        with get_db() as conn:
            # Ingest (creates ride + laps)
            count = ingest_rides(conn, rides_dir=str(tmp_path))
            assert count == 1

            ride_id = conn.execute("SELECT id FROM rides WHERE filename = ?", (fname,)).fetchone()["id"]
            lap_count = conn.execute("SELECT COUNT(*) as cnt FROM ride_laps WHERE ride_id = ?", (ride_id,)).fetchone()["cnt"]
            assert lap_count == 2

            # Delete laps
            conn.execute("DELETE FROM ride_laps WHERE ride_id = ?", (ride_id,))
            lap_count = conn.execute("SELECT COUNT(*) as cnt FROM ride_laps WHERE ride_id = ?", (ride_id,)).fetchone()["cnt"]
            assert lap_count == 0

            # Backfill
            backfilled = backfill_laps(conn, rides_dir=str(tmp_path))
            assert backfilled == 1

            # Verify restored
            restored = conn.execute(
                "SELECT * FROM ride_laps WHERE ride_id = ? ORDER BY lap_index", (ride_id,)
            ).fetchall()
            assert len(restored) == 2
            assert restored[0]["avg_power"] == 150
            assert restored[1]["avg_power"] == 250

            # Cleanup
            conn.execute("DELETE FROM ride_laps WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM ride_records WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM power_bests WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM rides WHERE id = ?", (ride_id,))


class TestAPILaps:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from server.main import app
        yield TestClient(app)

    def test_ride_detail_includes_laps(self, client, tmp_path):
        """GET /api/rides/{id} returns laps."""
        laps = [
            {"message_index": 0, "intensity": "active", "total_timer_time": 600, "avg_power": 150},
            {"message_index": 1, "intensity": "active", "total_timer_time": 1200, "avg_power": 250},
        ]
        fname = "test_api_laps_unique.json"
        filepath = tmp_path / fname
        filepath.write_text(json.dumps(_make_ride_json(laps=laps)))

        with get_db() as conn:
            ingest_rides(conn, rides_dir=str(tmp_path))
            ride = conn.execute("SELECT id FROM rides WHERE filename = ?", (fname,)).fetchone()
            ride_id = ride["id"]

        resp = client.get(f"/api/rides/{ride_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "laps" in data
        assert len(data["laps"]) == 2
        assert data["laps"][0]["avg_power"] == 150
        assert data["laps"][1]["avg_power"] == 250

        # Cleanup
        with get_db() as conn:
            conn.execute("DELETE FROM ride_laps WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM ride_records WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM power_bests WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM rides WHERE id = ?", (ride_id,))

    def test_ride_detail_no_laps_returns_empty_list(self, client, tmp_path):
        """Rides without laps return empty list."""
        fname = "test_api_no_laps_unique.json"
        filepath = tmp_path / fname
        filepath.write_text(json.dumps(_make_ride_json()))

        with get_db() as conn:
            ingest_rides(conn, rides_dir=str(tmp_path))
            ride = conn.execute("SELECT id FROM rides WHERE filename = ?", (fname,)).fetchone()
            ride_id = ride["id"]

        resp = client.get(f"/api/rides/{ride_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["laps"] == []

        # Cleanup
        with get_db() as conn:
            conn.execute("DELETE FROM ride_records WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM power_bests WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM rides WHERE id = ?", (ride_id,))
