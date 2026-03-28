"""Tests for duplicate workout prevention (Plan 3): hash-based dedup, event lifecycle."""

import pytest
from unittest.mock import patch, MagicMock
import httpx

from server.services.intervals_icu import compute_sync_hash, push_workout, delete_event


class TestSyncHash:
    """Tests for compute_sync_hash deduplication."""

    def test_same_inputs_same_hash(self):
        h1 = compute_sync_hash("Endurance", "2026-03-28", "<workout/>", 3600)
        h2 = compute_sync_hash("Endurance", "2026-03-28", "<workout/>", 3600)
        assert h1 == h2

    def test_different_name_different_hash(self):
        h1 = compute_sync_hash("Endurance", "2026-03-28", "<workout/>", 3600)
        h2 = compute_sync_hash("Tempo", "2026-03-28", "<workout/>", 3600)
        assert h1 != h2

    def test_different_date_different_hash(self):
        h1 = compute_sync_hash("Endurance", "2026-03-28", "<workout/>", 3600)
        h2 = compute_sync_hash("Endurance", "2026-03-29", "<workout/>", 3600)
        assert h1 != h2

    def test_different_xml_different_hash(self):
        h1 = compute_sync_hash("Endurance", "2026-03-28", "<workout><zone>2</zone></workout>", 3600)
        h2 = compute_sync_hash("Endurance", "2026-03-28", "<workout><zone>3</zone></workout>", 3600)
        assert h1 != h2

    def test_different_duration_different_hash(self):
        h1 = compute_sync_hash("Endurance", "2026-03-28", "<workout/>", 3600)
        h2 = compute_sync_hash("Endurance", "2026-03-28", "<workout/>", 7200)
        assert h1 != h2

    def test_hash_length(self):
        h = compute_sync_hash("Test", "2026-01-01", "<w/>")
        assert len(h) == 16


class TestPushWorkout:
    """Tests for push_workout POST vs PUT behavior."""

    @patch("server.services.intervals_icu._get_credentials", return_value=("key123", "ath456"))
    @patch("server.services.intervals_icu.httpx.post")
    def test_creates_new_event_without_icu_event_id(self, mock_post, mock_creds):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 999}
        mock_post.return_value = mock_resp

        result = push_workout("2026-03-28", "Endurance", "<workout/>")
        assert result["status"] == "success"
        assert result["event_id"] == 999
        mock_post.assert_called_once()
        assert "/events" in mock_post.call_args[0][0]
        assert "/events/" not in mock_post.call_args[0][0]

    @patch("server.services.intervals_icu._get_credentials", return_value=("key123", "ath456"))
    @patch("server.services.intervals_icu.httpx.put")
    def test_updates_existing_event_with_icu_event_id(self, mock_put, mock_creds):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 42}
        mock_put.return_value = mock_resp

        result = push_workout("2026-03-28", "Endurance", "<workout/>", icu_event_id=42)
        assert result["status"] == "success"
        mock_put.assert_called_once()
        assert "/events/42" in mock_put.call_args[0][0]

    @patch("server.services.intervals_icu._get_credentials", return_value=("", ""))
    def test_returns_error_when_not_configured(self, mock_creds):
        result = push_workout("2026-03-28", "Test", "<w/>")
        assert "error" in result


class TestDeleteEvent:
    """Tests for delete_event API call."""

    @patch("server.services.intervals_icu._get_credentials", return_value=("key123", "ath456"))
    @patch("server.services.intervals_icu.httpx.delete")
    def test_delete_success(self, mock_delete, mock_creds):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_delete.return_value = mock_resp

        result = delete_event(42)
        assert result["status"] == "success"
        assert "/events/42" in mock_delete.call_args[0][0]

    @patch("server.services.intervals_icu._get_credentials", return_value=("key123", "ath456"))
    @patch("server.services.intervals_icu.httpx.delete")
    def test_delete_failure(self, mock_delete, mock_creds):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"
        mock_delete.return_value = mock_resp

        result = delete_event(42)
        assert result["status"] == "error"
        assert result["code"] == 404

    @patch("server.services.intervals_icu._get_credentials", return_value=("", ""))
    def test_delete_not_configured(self, mock_creds):
        result = delete_event(42)
        assert result["status"] == "error"
        assert "not configured" in result["message"]
