"""Tests for the sync service and API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from server.database import init_db, get_db
from server.main import app


@pytest.fixture
def client():
    init_db()
    yield TestClient(app)


@pytest.fixture
def db():
    init_db()
    yield


def test_sync_tables_created(db):
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


def test_sync_watermarks(db):
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
    assert ride["date"] == "2026-03-24"
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


def test_sync_run_persistence(db):
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
