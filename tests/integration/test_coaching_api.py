"""Tests for coaching chat API endpoint (mocked LLM)."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


def test_chat_endpoint_mocked(client):
    """Test chat endpoint with mocked LLM response."""
    with patch("server.coaching.agent.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "Your CTL is looking good. Let's plan your next build week."

        resp = client.post("/api/coaching/chat", json={"message": "How's my fitness?"})

    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert "session_id" in data
    assert len(data["session_id"]) > 0


def test_chat_preserves_session_id(client):
    """Test that session_id is preserved when provided."""
    with patch("server.coaching.agent.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "Looking good."

        resp = client.post("/api/coaching/chat", json={
            "message": "test",
            "session_id": "my-session-123",
        })

    assert resp.status_code == 200
    assert resp.json()["session_id"] == "my-session-123"


def test_build_system_instruction_includes_computed_metrics():
    """Test that system prompt includes W/kg, weight in lbs, and CTL/ATL/TSB."""
    from server.coaching.agent import _build_system_instruction

    prompt = _build_system_instruction(None)

    # Should contain computed metrics
    assert "W/kg:" in prompt
    assert "Current Weight (lbs):" in prompt
    # Should contain PMC data (test DB has daily_metrics)
    assert "CTL (Fitness):" in prompt
    assert "ATL (Fatigue):" in prompt
    assert "TSB (Form):" in prompt
    assert "Metrics as-of:" in prompt
    # Should contain planned vs actual guidance
    assert "get_planned_workout_for_ride" in prompt


def test_build_system_instruction_includes_coach_notes_mandate():
    """System instruction includes the mandatory coach notes instruction."""
    from server.coaching.agent import _build_system_instruction
    prompt = _build_system_instruction(None)
    assert "COACH NOTES" in prompt
    assert "set_workout_coach_notes" in prompt
    assert "replace_workout" in prompt


def test_build_system_instruction_pmc_missing():
    """Test that system prompt handles missing PMC data gracefully."""
    from server.coaching.agent import _build_system_instruction

    with patch("server.queries.get_current_pmc_row", return_value=None):
        prompt = _build_system_instruction(None)

    assert "CTL/ATL/TSB: No data available" in prompt
