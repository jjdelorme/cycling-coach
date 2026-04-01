"""Tests for workout sync idempotency."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from server.database import get_db
from server.services.intervals_icu import find_matching_workout

# Use a date 7 days from now so it falls within the sync window (today + 28 days)
TEST_DATE = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")


@pytest.fixture
def test_workout():
    """Create a test workout and clean it up after the test."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO planned_workouts (date, name, workout_xml, total_duration_s) VALUES (%s, %s, %s, %s)",
            (TEST_DATE, "Test Workout", "<zwo><workout><step/></workout></zwo>", 3600)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM planned_workouts WHERE name = 'Test Workout' AND date = %s", (TEST_DATE,)).fetchone()
        workout_id = row["id"]
    yield workout_id
    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM planned_workouts WHERE id = %s", (workout_id,))
        conn.commit()


@pytest.fixture
def isolated_test_workout():
    """Create a test workout that is the ONLY unsynced workout in the sync window.

    Used by the background sync test which calls _upload_workouts and needs to
    ensure only our test workout gets uploaded.
    """
    from server.services.intervals_icu import compute_sync_hash
    with get_db() as conn:
        # Mark all existing workouts in the sync window as "already synced" by
        # setting both sync_hash (to the real computed hash) and icu_event_id
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=28)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT id, name, date, workout_xml, total_duration_s FROM planned_workouts "
            "WHERE date >= %s AND date <= %s AND workout_xml IS NOT NULL",
            (today, end_date)
        ).fetchall()
        for r in rows:
            h = compute_sync_hash(r["name"] or "Workout", r["date"], r["workout_xml"], int(r["total_duration_s"] or 0))
            conn.execute(
                "UPDATE planned_workouts SET sync_hash = %s, icu_event_id = -1 WHERE id = %s",
                (h, r["id"])
            )
        conn.execute(
            "INSERT INTO planned_workouts (date, name, workout_xml, total_duration_s) VALUES (%s, %s, %s, %s)",
            (TEST_DATE, "Test Workout", "<zwo><workout><step/></workout></zwo>", 3600)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM planned_workouts WHERE name = 'Test Workout' AND date = %s", (TEST_DATE,)).fetchone()
        workout_id = row["id"]
    yield workout_id
    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM planned_workouts WHERE id = %s", (workout_id,))
        conn.execute(
            "UPDATE planned_workouts SET sync_hash = NULL, icu_event_id = NULL "
            "WHERE icu_event_id = -1"
        )
        conn.commit()


def test_sync_workout_creates_new_if_none_exists(client, test_workout):
    workout_id = test_workout

    mock_push_result = {"status": "success", "event_id": 12345}

    with patch("server.services.intervals_icu.is_configured", return_value=True), \
         patch("server.services.intervals_icu.fetch_calendar_events", return_value=[]), \
         patch("server.services.intervals_icu.push_workout", return_value=mock_push_result) as mock_push:

        resp = client.post(f"/api/plan/workouts/{workout_id}/sync")
        assert resp.status_code == 200

        args, kwargs = mock_push.call_args
        assert kwargs.get("icu_event_id") is None

        with get_db() as conn:
            row = conn.execute("SELECT icu_event_id, sync_hash FROM planned_workouts WHERE id = %s", (workout_id,)).fetchone()
            assert row["icu_event_id"] == 12345


def test_sync_workout_uses_existing_id_if_found_on_remote(client, test_workout):
    workout_id = test_workout

    mock_events = [
        {"id": 99999, "category": "WORKOUT", "name": "Test Workout", "start_date_local": f"{TEST_DATE}T00:00:00"}
    ]
    mock_push_result = {"status": "success", "event_id": 99999}

    with patch("server.services.intervals_icu.is_configured", return_value=True), \
         patch("server.services.intervals_icu.fetch_calendar_events", return_value=mock_events), \
         patch("server.services.intervals_icu.push_workout", return_value=mock_push_result) as mock_push:

        resp = client.post(f"/api/plan/workouts/{workout_id}/sync")
        assert resp.status_code == 200

        args, kwargs = mock_push.call_args
        assert kwargs.get("icu_event_id") == 99999

        with get_db() as conn:
            row = conn.execute("SELECT icu_event_id FROM planned_workouts WHERE id = %s", (workout_id,)).fetchone()
            assert row["icu_event_id"] == 99999


@pytest.mark.asyncio
async def test_background_sync_uses_existing_id(isolated_test_workout):
    workout_id = isolated_test_workout
    from server.services.sync import _upload_workouts

    mock_events = [
        {"id": 88888, "category": "WORKOUT", "name": "Test Workout", "start_date_local": f"{TEST_DATE}T00:00:00"}
    ]
    mock_push_result = {"status": "success", "event_id": 88888}

    with patch("server.services.sync.is_configured", return_value=True), \
         patch("server.services.intervals_icu.fetch_calendar_events", return_value=mock_events), \
         patch("server.services.sync.push_workout", return_value=mock_push_result) as mock_push, \
         patch("server.services.sync.find_matching_workout", wraps=find_matching_workout):

        with get_db() as conn:
            log_lines = []
            uploaded, skipped = await _upload_workouts("test-sync", log_lines, conn)

            assert uploaded == 1

            args, kwargs = mock_push.call_args
            assert kwargs.get("icu_event_id") == 88888

            row = conn.execute("SELECT icu_event_id FROM planned_workouts WHERE id = %s", (workout_id,)).fetchone()
            assert row["icu_event_id"] == 88888
