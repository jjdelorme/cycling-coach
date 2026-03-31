
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from server.database import init_db, get_db
from server.main import app
from server.services.intervals_icu import find_matching_workout
import datetime

@pytest.fixture
def client():
    init_db()
    yield TestClient(app)

@pytest.fixture
def db():
    init_db()
    with get_db() as conn:
        # Clear existing planned workouts to ensure test isolation
        conn.execute("TRUNCATE TABLE planned_workouts CASCADE")
        # Create a planned workout
        conn.execute(
            "INSERT INTO planned_workouts (date, name, workout_xml, total_duration_s) VALUES (?, ?, ?, ?)",
            ("2026-04-01", "Test Workout", "<zwo><workout><step/></workout></zwo>", 3600)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM planned_workouts WHERE name = 'Test Workout'").fetchone()
        workout_id = row["id"]
    yield workout_id

def test_sync_workout_creates_new_if_none_exists(client, db):
    workout_id = db
    
    mock_push_result = {"status": "success", "event_id": 12345}
    
    # Path manual sync router's internal import of push_workout
    with patch("server.services.intervals_icu.is_configured", return_value=True), \
         patch("server.services.intervals_icu.fetch_calendar_events", return_value=[]), \
         patch("server.services.intervals_icu.push_workout", return_value=mock_push_result) as mock_push:
        
        resp = client.post(f"/api/plan/workouts/{workout_id}/sync")
        assert resp.status_code == 200
        
        # Verify it was called without icu_event_id (or with None)
        args, kwargs = mock_push.call_args
        assert kwargs.get("icu_event_id") is None
        
        # Verify DB updated
        with get_db() as conn:
            row = conn.execute("SELECT icu_event_id, sync_hash FROM planned_workouts WHERE id = ?", (workout_id,)).fetchone()
            assert row["icu_event_id"] == 12345

def test_sync_workout_uses_existing_id_if_found_on_remote(client, db):
    workout_id = db
    
    # Remote already has a workout with same name and date
    mock_events = [
        {"id": 99999, "category": "WORKOUT", "name": "Test Workout", "start_date_local": "2026-04-01T00:00:00"}
    ]
    mock_push_result = {"status": "success", "event_id": 99999}
    
    with patch("server.services.intervals_icu.is_configured", return_value=True), \
         patch("server.services.intervals_icu.fetch_calendar_events", return_value=mock_events), \
         patch("server.services.intervals_icu.push_workout", return_value=mock_push_result) as mock_push:
        
        # Initial sync (where we don't have the ID locally yet)
        resp = client.post(f"/api/plan/workouts/{workout_id}/sync")
        assert resp.status_code == 200
        
        # It SHOULD have found the existing event and used its ID
        args, kwargs = mock_push.call_args
        assert kwargs.get("icu_event_id") == 99999
        
        # Verify DB updated
        with get_db() as conn:
            row = conn.execute("SELECT icu_event_id FROM planned_workouts WHERE id = ?", (workout_id,)).fetchone()
            assert row["icu_event_id"] == 99999

@pytest.mark.asyncio
async def test_background_sync_uses_existing_id(db):
    workout_id = db
    from server.services.sync import _upload_workouts
    
    # Remote already has a workout with same name and date
    mock_events = [
        {"id": 88888, "category": "WORKOUT", "name": "Test Workout", "start_date_local": "2026-04-01T00:00:00"}
    ]
    mock_push_result = {"status": "success", "event_id": 88888}
    
    # Patch the service used by background sync
    with patch("server.services.sync.is_configured", return_value=True), \
         patch("server.services.intervals_icu.fetch_calendar_events", return_value=mock_events), \
         patch("server.services.sync.push_workout", return_value=mock_push_result) as mock_push, \
         patch("server.services.sync.find_matching_workout", wraps=find_matching_workout):
        
        with get_db() as conn:
            log_lines = []
            uploaded, skipped = await _upload_workouts("test-sync", log_lines, conn)
            
            assert uploaded == 1
            assert skipped == 0
            
            # It SHOULD have found the existing event and used its ID
            args, kwargs = mock_push.call_args
            assert kwargs.get("icu_event_id") == 88888
            
            # Verify DB updated
            row = conn.execute("SELECT icu_event_id FROM planned_workouts WHERE id = ?", (workout_id,)).fetchone()
            assert row["icu_event_id"] == 88888
