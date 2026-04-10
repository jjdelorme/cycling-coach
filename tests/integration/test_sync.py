"""Tests for the sync service and API endpoints."""

import pytest
from unittest.mock import patch, MagicMock

from server.database import get_db


def test_sync_tables_created():
    """Verify sync tables exist in the schema."""
    with get_db() as conn:
        tables = [
            row["tablename"]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ).fetchall()
        ]
    assert "sync_runs" in tables
    assert "sync_watermarks" in tables


def test_sync_watermarks():
    """Test watermark get/set operations."""
    from server.services.sync import get_watermark, set_watermark

    # Use a unique key to avoid conflicts with real data
    assert get_watermark("test_watermark_key") is None

    set_watermark("test_watermark_key", "2026-03-20")
    assert get_watermark("test_watermark_key") == "2026-03-20"

    # Update existing watermark
    set_watermark("test_watermark_key", "2026-03-25")
    assert get_watermark("test_watermark_key") == "2026-03-25"

    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM sync_watermarks WHERE key = 'test_watermark_key'")


def test_sync_overview_not_configured(client):
    """Test overview endpoint when intervals.icu is not configured."""
    with patch("server.services.intervals_icu.is_configured", return_value=False), \
         patch("server.services.sync.is_configured", return_value=False):
        resp = client.get("/api/sync/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert data["running_sync_id"] is None


def test_sync_start_not_configured(client):
    """Test that starting sync fails when not configured."""
    with patch("server.services.intervals_icu.is_configured", return_value=False), \
         patch("server.routers.sync.is_configured", return_value=False):
        resp = client.post("/api/sync/start")
        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"]


def test_sync_status_not_found(client):
    """Test polling a non-existent sync run."""
    resp = client.get("/api/sync/status/nonexistent")
    assert resp.status_code == 404


def test_sync_history_empty(client):
    """Test history endpoint with no sync runs."""
    resp = client.get("/api/sync/history")
    assert resp.status_code == 200
    # May have runs from other tests, just check it's a list
    assert isinstance(resp.json(), list)


def test_map_activity_to_ride():
    """Test mapping intervals.icu activity to our ride schema."""
    from server.services.intervals_icu import map_activity_to_ride

    activity = {
        "id": "i12345_abc",
        "start_date_local": "2026-03-24T08:30:00",
        "type": "Ride",
        "moving_time": 3600,
        "distance": 30000,
        "average_watts": 180,
        "icu_weighted_avg_watts": 200,
        "max_watts": 500,
        "average_heartrate": 140,
        "max_heartrate": 175,
        "average_cadence": 85,
        "total_elevation_gain": 500,
        "calories": 800,
        "icu_training_load": 85.0,
        "icu_intensity": 0.77,
        "icu_ftp": 261,
        "icu_weight": 74.0,
    }

    ride = map_activity_to_ride(activity)
    assert ride is not None
    assert ride["start_time"] == "2026-03-24T08:30:00"
    assert ride["filename"] == "icu_i12345_abc"
    assert ride["duration_s"] == 3600
    assert ride["avg_power"] == 180
    assert ride["normalized_power"] == 200
    assert ride["tss"] == 85.0
    assert ride["ftp"] == 261
    assert ride["variability_index"] == round(200 / 180, 3)


def test_map_activity_to_ride_missing_data():
    """Test mapping with minimal data."""
    from server.services.intervals_icu import map_activity_to_ride

    assert map_activity_to_ride({}) is None
    assert map_activity_to_ride({"start_date_local": "2026-03-24"}) is None
    assert map_activity_to_ride({"id": "abc"}) is None


def test_sync_run_persistence():
    """Test creating and querying sync runs in the database."""
    from server.services.sync import _create_sync_run, get_sync_run, get_sync_history, _update_sync_run

    _create_sync_run("test-123")

    run = get_sync_run("test-123")
    assert run is not None
    assert run["status"] == "running"
    assert run["rides_downloaded"] == 0

    _update_sync_run("test-123", status="completed", rides_downloaded=5)
    run = get_sync_run("test-123")
    assert run["status"] == "completed"
    assert run["rides_downloaded"] == 5

    history = get_sync_history()
    assert len(history) >= 1

    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM sync_runs WHERE id = 'test-123'")

@pytest.mark.asyncio
async def test_sync_generates_power_bests():
    """Verify that a sync run calculates and persists power bests."""
    from server.services.sync import _download_rides
    
    # Mock data for a single ride
    mock_activity = {
        "id": "icu_999",
        "start_date_local": "2026-03-24T08:30:00",
        "type": "Ride",
        "moving_time": 3600,
        "distance": 30000,
        "average_watts": 200,
        "icu_ftp": 200,
    }
    
    # Mock streams: 1 hour of 200W
    mock_streams = {
        "time": list(range(3600)),
        "watts": [200.0] * 3600,
        "heartrate": [150.0] * 3600,
        "cadence": [90.0] * 3600
    }
    
    with patch("server.services.sync.fetch_activities", return_value=[mock_activity]), \
         patch("server.services.sync.fetch_activity_streams", return_value=mock_streams), \
         patch("server.services.sync.fetch_activity_fit_laps", return_value=[]), \
         patch("server.services.sync.get_watermark", return_value=None), \
         patch("server.services.sync.set_watermark"), \
         patch("server.services.sync._broadcast"):
        
        sync_id = "test-pb-1"
        log_lines = []
        
        with get_db() as conn:
            # Clear existing data for this mock ride if it exists
            conn.execute("DELETE FROM power_bests WHERE ride_id IN (SELECT id FROM rides WHERE filename = 'icu_icu_999')")
            conn.execute("DELETE FROM ride_records WHERE ride_id IN (SELECT id FROM rides WHERE filename = 'icu_icu_999')")
            conn.execute("DELETE FROM rides WHERE filename = 'icu_icu_999'")
            
            # Run the download
            downloaded, skipped, earliest = await _download_rides(sync_id, log_lines, conn)
            assert downloaded == 1
            
            # Get the inserted ride's ID
            ride_row = conn.execute("SELECT id FROM rides WHERE filename = 'icu_icu_999'").fetchone()
            assert ride_row is not None
            ride_db_id = ride_row["id"]
            
            # Verify power_bests were created for THIS ride
            rows = conn.execute("SELECT * FROM power_bests WHERE ride_id = %s", (ride_db_id,)).fetchall()
            assert len(rows) > 0, "No power bests were created for the synced ride!"
            
            # Check for specific durations (e.g., 60s, 300s, 1200s, 3600s)
            durations = [r["duration_s"] for r in rows]
            assert 60 in durations
            assert 300 in durations
            assert 1200 in durations
            assert 3600 in durations
            
            # Check power value
            for row in rows:
                assert row["power"] == pytest.approx(200.0)
                
            # Cleanup for this test
            conn.execute("DELETE FROM power_bests WHERE ride_id IN (SELECT id FROM rides WHERE filename = 'icu_icu_999')")
            conn.execute("DELETE FROM ride_records WHERE ride_id IN (SELECT id FROM rides WHERE filename = 'icu_icu_999')")
            conn.execute("DELETE FROM rides WHERE filename = 'icu_icu_999'")

@pytest.mark.asyncio
async def test_sync_processes_fit_laps():
    """Verify that a sync run fetches and persists FIT laps."""
    from server.services.sync import _download_rides
    
    # Mock data for a single ride
    mock_activity = {
        "id": "icu_888",
        "start_date_local": "2026-03-25T09:00:00",
        "type": "Ride",
        "moving_time": 1800,
        "distance": 15000,
        "average_watts": 250,
        "icu_ftp": 250,
    }
    
    # Mock streams
    mock_streams = {
        "time": list(range(1800)),
        "watts": [250.0] * 1800,
    }
    
    # Mock laps
    mock_laps = [
        {
            "lap_index": 0,
            "start_time": "2026-03-25T09:00:00Z",
            "total_timer_time": 900.0,
            "total_elapsed_time": 905.0,
            "total_distance": 7500.0,
            "avg_power": 240.0,
            "normalized_power": 245.0,
            "max_power": 400.0,
            "avg_hr": 150.0,
            "max_hr": 160.0,
            "avg_cadence": 90.0,
            "max_cadence": 100.0,
            "avg_speed": 8.33,
            "max_speed": 12.0,
            "total_ascent": 50.0,
            "total_descent": 10.0,
            "total_calories": 400,
            "total_work": 216000,
            "intensity": 0.96,
            "lap_trigger": "manual",
            "wkt_step_index": None,
            "start_lat": 45.0,
            "start_lon": -122.0,
            "end_lat": 45.1,
            "end_lon": -122.1,
            "avg_temperature": 20.0,
        },
        {
            "lap_index": 1,
            "start_time": "2026-03-25T09:15:05Z",
            "total_timer_time": 900.0,
            "total_elapsed_time": 900.0,
            "total_distance": 7500.0,
            "avg_power": 260.0,
            "normalized_power": 265.0,
            "max_power": 450.0,
            "avg_hr": 160.0,
            "max_hr": 170.0,
            "avg_cadence": 95.0,
            "max_cadence": 110.0,
            "avg_speed": 8.33,
            "max_speed": 13.0,
            "total_ascent": 20.0,
            "total_descent": 60.0,
            "total_calories": 450,
            "total_work": 234000,
            "intensity": 1.04,
            "lap_trigger": "manual",
            "wkt_step_index": None,
            "start_lat": 45.1,
            "start_lon": -122.1,
            "end_lat": 45.2,
            "end_lon": -122.2,
            "avg_temperature": 21.0,
        }
    ]
    
    with patch("server.services.sync.fetch_activities", return_value=[mock_activity]), \
         patch("server.services.sync.fetch_activity_streams", return_value=mock_streams), \
         patch("server.services.sync.fetch_activity_fit_laps", return_value=mock_laps), \
         patch("server.services.sync.get_watermark", return_value=None), \
         patch("server.services.sync.set_watermark"), \
         patch("server.services.sync._broadcast"):
        
        sync_id = "test-laps-1"
        log_lines = []
        
        with get_db() as conn:
            # Clear existing data for this mock ride if it exists
            conn.execute("DELETE FROM ride_laps WHERE ride_id IN (SELECT id FROM rides WHERE filename = 'icu_icu_888')")
            conn.execute("DELETE FROM ride_records WHERE ride_id IN (SELECT id FROM rides WHERE filename = 'icu_icu_888')")
            conn.execute("DELETE FROM rides WHERE filename = 'icu_icu_888'")
            
            # Run the download
            downloaded, skipped, earliest = await _download_rides(sync_id, log_lines, conn)
            assert downloaded == 1
            
            # Get the inserted ride's ID
            ride_row = conn.execute("SELECT id FROM rides WHERE filename = 'icu_icu_888'").fetchone()
            assert ride_row is not None
            ride_db_id = ride_row["id"]
            
            # Verify ride_laps were created for THIS ride
            rows = conn.execute("SELECT * FROM ride_laps WHERE ride_id = %s ORDER BY lap_index", (ride_db_id,)).fetchall()
            assert len(rows) == 2, "Laps were not created for the synced ride!"
            
            assert rows[0]["lap_index"] == 0
            assert rows[0]["avg_power"] == 240.0
            assert rows[0]["start_lat"] == 45.0
            
            assert rows[1]["lap_index"] == 1
            assert rows[1]["avg_power"] == 260.0
            assert rows[1]["end_lon"] == -122.2
            
            # Cleanup for this test
            conn.execute("DELETE FROM power_bests WHERE ride_id = %s", (ride_db_id,))
            conn.execute("DELETE FROM ride_laps WHERE ride_id = %s", (ride_db_id,))
            conn.execute("DELETE FROM ride_records WHERE ride_id = %s", (ride_db_id,))
            conn.execute("DELETE FROM rides WHERE id = %s", (ride_db_id,))
