"""Tests for coaching chat API endpoint (mocked LLM)."""

import os
import pytest
from unittest.mock import patch, AsyncMock

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "coach.db")


@pytest.fixture(scope="module")
def client():
    os.environ["COACH_DB_PATH"] = DB_PATH
    if not os.path.exists(DB_PATH):
        pytest.skip("Database not found")
    from fastapi.testclient import TestClient
    from server.main import app
    return TestClient(app)


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
