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
         patch("server.services.sync.fetch_activity_fit_records", return_value=[]), \
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
         patch("server.services.sync.fetch_activity_fit_records", return_value=[]), \
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


# ---------------------------------------------------------------------------
# Phase 6 — FIT-primary GPS write path (Campaign 20 D1)
# ---------------------------------------------------------------------------


def _build_fit_records(n: int, lat: float, lon: float):
    """Build ``n`` flat-shape FIT records spanning ``n`` seconds.

    Mirrors the dict shape returned by ``fetch_activity_fit_records`` after
    Phase 5. Used by the FIT-primary integration test to feed the
    ``_store_records_or_fallback`` helper without requiring a real FIT file.
    """
    base = "2026-04-13T14:30:%02d+00:00"
    records = []
    for i in range(n):
        records.append(
            {
                "timestamp_utc": base % (i % 60),
                "power": 200,
                "heart_rate": 140,
                "cadence": 85,
                "speed": 7.5,
                "altitude": 1500.0 + i,
                "distance": float(i * 7),
                "lat": lat + i * 0.0001,
                "lon": lon + i * 0.0001,
                "temperature": 22,
            }
        )
    return records


def test_store_records_from_fit_writes_one_row_per_record(db_conn):
    """``_store_records_from_fit`` deletes existing rows then inserts per-record."""
    from server.services.sync import _store_records_from_fit

    # Seed a ride row to attach records to.
    res = db_conn.execute(
        """INSERT INTO rides (start_time, filename, sport, duration_s, distance_m)
           VALUES ('2026-04-13T14:30:00', 'icu_fit_primary_test_1', 'ride', 100, 0)
           RETURNING id"""
    ).fetchone()
    ride_id = res["id"]
    try:
        # Pre-populate one bogus row to verify the DELETE-first idempotency.
        db_conn.execute(
            "INSERT INTO ride_records (ride_id, lat, lon) VALUES (%s, 0.0, 0.0)",
            (ride_id,),
        )

        fit_records = _build_fit_records(10, lat=39.31, lon=-108.71)
        count = _store_records_from_fit(ride_id, fit_records, conn=db_conn)
        db_conn.commit()

        assert count == 10
        rows = db_conn.execute(
            "SELECT lat, lon, power FROM ride_records WHERE ride_id = %s ORDER BY id",
            (ride_id,),
        ).fetchall()
        assert len(rows) == 10
        # First row's lat/lon match what we put in (NOT (0, 0) which was the
        # pre-existing bogus row we expected DELETE to have removed).
        assert rows[0]["lat"] == pytest.approx(39.31)
        assert rows[0]["lon"] == pytest.approx(-108.71)
        # Every row's lon is negative (US ride) — a sanity check that
        # FIT lat/lon weren't accidentally swapped or both-set-to-lat.
        assert all(r["lon"] < 0 for r in rows)
    finally:
        db_conn.execute("DELETE FROM ride_records WHERE ride_id = %s", (ride_id,))
        db_conn.execute("DELETE FROM rides WHERE id = %s", (ride_id,))
        db_conn.commit()


def test_fit_primary_overrides_corrupt_streams_latlng(db_conn, monkeypatch):
    """``_store_records_or_fallback`` writes FIT records and ignores the
    streams ``latlng`` even when the streams payload is the lat-only
    Variant B that produced the original Campaign 20 bug."""
    from server.services import sync as sync_module
    from server.services.sync import _store_records_or_fallback

    # Seed the ride row we'll backfill.
    res = db_conn.execute(
        """INSERT INTO rides (start_time, filename, sport, duration_s, distance_m)
           VALUES ('2026-04-13T14:30:00', 'icu_fit_primary_test_2', 'ride', 100, 0)
           RETURNING id"""
    ).fetchone()
    ride_id = res["id"]
    icu_id = "i_fit_primary_test_2"
    try:
        fake_fit_records = _build_fit_records(80, lat=39.75, lon=-108.71)

        # Streams: a lat-only Variant B payload that would corrupt
        # ride_records if it ever reached _store_streams.
        fake_corrupt_streams = {
            "time": list(range(80)),
            "watts": [200] * 80,
            "heartrate": [140] * 80,
            # 160-element flat array of latitudes only — would normalise to
            # (lat, lat) pairs under the existing parser.
            "latlng": [39.75, 39.75] * 80,
        }

        monkeypatch.setattr(
            sync_module,
            "fetch_activity_fit_records",
            lambda i: fake_fit_records,
        )
        monkeypatch.setattr(
            sync_module,
            "fetch_activity_streams",
            lambda i: fake_corrupt_streams,
        )

        gps_source, streams = _store_records_or_fallback(ride_id, icu_id, conn=db_conn)
        db_conn.commit()

        assert gps_source == "fit"
        # Streams dict still returned for the metric pipeline.
        assert streams is not None
        assert "watts" in streams

        rows = db_conn.execute(
            "SELECT lat, lon FROM ride_records WHERE ride_id = %s ORDER BY id",
            (ride_id,),
        ).fetchall()
        assert len(rows) == 80
        # Critically: no row has the (lat, lat) shape that the corrupt
        # streams would have produced.
        for r in rows:
            assert r["lat"] is not None and r["lon"] is not None
            # Lon must be negative (US ride) — proves we didn't accidentally
            # write streams data.
            assert r["lon"] < 0
            # |lat - lon| > 100 → we have a real (lat, lon) pair, not (lat, lat).
            assert abs(r["lat"] - r["lon"]) > 100
    finally:
        db_conn.execute("DELETE FROM ride_records WHERE ride_id = %s", (ride_id,))
        db_conn.execute("DELETE FROM rides WHERE id = %s", (ride_id,))
        db_conn.commit()


def test_store_records_or_fallback_uses_streams_when_fit_unavailable(db_conn, monkeypatch):
    """When FIT returns ``[]`` (e.g. 404 from /file), fall back to the
    streams writer, which produces per-record rows from streams data."""
    from server.services import sync as sync_module
    from server.services.sync import _store_records_or_fallback

    res = db_conn.execute(
        """INSERT INTO rides (start_time, filename, sport, duration_s, distance_m)
           VALUES ('2026-04-13T14:30:00', 'icu_fit_primary_test_3', 'ride', 100, 0)
           RETURNING id"""
    ).fetchone()
    ride_id = res["id"]
    icu_id = "i_fit_primary_test_3"
    try:
        clean_streams = {
            "time": list(range(5)),
            "watts": [200, 210, 220, 230, 240],
            # Flat alternating lat/lon (the simple, correct shape).
            "latlng": [39.75, -108.71, 39.751, -108.711, 39.752, -108.712,
                       39.753, -108.713, 39.754, -108.714],
        }

        monkeypatch.setattr(sync_module, "fetch_activity_fit_records", lambda i: [])
        monkeypatch.setattr(sync_module, "fetch_activity_streams", lambda i: clean_streams)

        gps_source, streams = _store_records_or_fallback(ride_id, icu_id, conn=db_conn)
        db_conn.commit()

        assert gps_source == "fallback_streams"
        assert streams is not None
        rows = db_conn.execute(
            "SELECT lat, lon FROM ride_records WHERE ride_id = %s ORDER BY id",
            (ride_id,),
        ).fetchall()
        assert len(rows) == 5
        assert rows[0]["lat"] == pytest.approx(39.75)
        assert rows[0]["lon"] == pytest.approx(-108.71)
    finally:
        db_conn.execute("DELETE FROM ride_records WHERE ride_id = %s", (ride_id,))
        db_conn.execute("DELETE FROM rides WHERE id = %s", (ride_id,))
        db_conn.commit()


def test_store_records_or_fallback_returns_none_when_both_fail(db_conn, monkeypatch):
    """No FIT, no streams → ('none', None); no rows written, no exception."""
    from server.services import sync as sync_module
    from server.services.sync import _store_records_or_fallback

    res = db_conn.execute(
        """INSERT INTO rides (start_time, filename, sport, duration_s, distance_m)
           VALUES ('2026-04-13T14:30:00', 'icu_fit_primary_test_4', 'ride', 100, 0)
           RETURNING id"""
    ).fetchone()
    ride_id = res["id"]
    icu_id = "i_fit_primary_test_4"
    try:
        monkeypatch.setattr(sync_module, "fetch_activity_fit_records", lambda i: [])
        monkeypatch.setattr(sync_module, "fetch_activity_streams", lambda i: {})

        gps_source, streams = _store_records_or_fallback(ride_id, icu_id, conn=db_conn)
        db_conn.commit()

        assert gps_source == "none"
        assert streams is None
        rows = db_conn.execute(
            "SELECT * FROM ride_records WHERE ride_id = %s",
            (ride_id,),
        ).fetchall()
        assert len(rows) == 0
    finally:
        db_conn.execute("DELETE FROM ride_records WHERE ride_id = %s", (ride_id,))
        db_conn.execute("DELETE FROM rides WHERE id = %s", (ride_id,))
        db_conn.commit()
