"""Tests for INTERVALS_ICU_DISABLE environment variable protection."""

import pytest
from unittest.mock import patch, MagicMock
from server.services.intervals_icu import push_workout, push_workouts_bulk, delete_event, update_ftp, update_weight, is_configured, is_sync_disabled

@patch("server.services.intervals_icu.INTERVALS_ICU_DISABLED", True)
def test_sync_disabled_checks():
    """Verify that all write operations are blocked when INTERVALS_ICU_DISABLED is True."""
    assert is_sync_disabled() is True
    
    # All these should return error dictionaries immediately without calling httpx
    res1 = push_workout("2026-04-06", "Test", "<xml/>")
    assert "disabled" in res1["error"]
    
    res2 = push_workouts_bulk([{"date": "2026-04-06", "name": "Test", "zwo_xml": "<xml/>"}])
    assert "disabled" in res2["error"]
    
    res3 = delete_event(12345)
    assert "disabled" in res3["error"]
    
    res4 = update_ftp(280)
    assert "disabled" in res4["error"]
    
    res5 = update_weight(75.0)
    assert "disabled" in res5["error"]

@patch("server.services.intervals_icu.INTERVALS_ICU_DISABLED", True)
@patch("server.services.intervals_icu._get_credentials")
def test_is_configured_still_true_when_disabled(mock_credentials):
    """Verify that is_configured still returns true (if credentials exist) so downloads continue."""
    mock_credentials.return_value = ("api_key", "athlete_id")
    # is_configured should ignore the disable flag, as it's used for general feature availability (like downloads)
    assert is_configured() is True

@patch("server.services.intervals_icu.INTERVALS_ICU_DISABLED", False)
@patch("server.services.intervals_icu._get_credentials")
@patch("httpx.post")
def test_push_workout_works_when_not_disabled(mock_post, mock_credentials):
    """Verify that operations work normally when INTERVALS_ICU_DISABLED is False."""
    mock_credentials.return_value = ("api_key", "athlete_id")
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": 999}
    mock_post.return_value = mock_response
    
    res = push_workout("2026-04-06", "Test", "<xml/>")
    assert res["status"] == "success"
    assert res["event_id"] == 999
