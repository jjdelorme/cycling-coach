"""Tests for persistent sessions and memory services."""

import os
import pytest
from unittest.mock import patch, AsyncMock


# --- DbSessionService tests ---

@pytest.mark.asyncio
async def test_create_and_get_session():
    from server.coaching.session_service import DbSessionService
    svc = DbSessionService()

    session = await svc.create_session(
        app_name="test", user_id="athlete", session_id="test-s1"
    )
    assert session.id == "test-s1"

    retrieved = await svc.get_session(
        app_name="test", user_id="athlete", session_id="test-s1"
    )
    assert retrieved is not None
    assert retrieved.id == "test-s1"

    # Cleanup
    await svc.delete_session(app_name="test", user_id="athlete", session_id="test-s1")


@pytest.mark.asyncio
async def test_list_sessions():
    from server.coaching.session_service import DbSessionService
    svc = DbSessionService()

    await svc.create_session(app_name="test", user_id="athlete", session_id="test-list-s1")
    await svc.create_session(app_name="test", user_id="athlete", session_id="test-list-s2")

    result = await svc.list_sessions(app_name="test", user_id="athlete")
    session_ids = [s.id for s in result.sessions]
    assert "test-list-s1" in session_ids
    assert "test-list-s2" in session_ids

    # Cleanup
    await svc.delete_session(app_name="test", user_id="athlete", session_id="test-list-s1")
    await svc.delete_session(app_name="test", user_id="athlete", session_id="test-list-s2")


@pytest.mark.asyncio
async def test_delete_session():
    from server.coaching.session_service import DbSessionService
    svc = DbSessionService()

    await svc.create_session(app_name="test", user_id="athlete", session_id="test-del-s1")
    await svc.delete_session(app_name="test", user_id="athlete", session_id="test-del-s1")

    result = await svc.get_session(app_name="test", user_id="athlete", session_id="test-del-s1")
    assert result is None


# --- DbMemoryService tests ---

@pytest.mark.asyncio
async def test_memory_add_and_search():
    from server.coaching.memory_service import DbMemoryService
    from google.adk.sessions import Session
    from google.adk.events import Event
    from google.genai import types

    svc = DbMemoryService()

    # Create a session with events
    session = Session(
        app_name="test",
        user_id="test-mem-athlete",
        id="test-mem-s1",
        state={},
        events=[
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="What is my FTP trend?")],
                ),
            ),
            Event(
                author="cycling_coach",
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text="Your FTP has been climbing steadily to 261w.")],
                ),
            ),
        ],
    )

    await svc.add_session_to_memory(session)

    # Search should find FTP-related memories
    result = await svc.search_memory(app_name="test", user_id="test-mem-athlete", query="FTP")
    assert len(result.memories) >= 1

    # Search for unrelated term should return less
    result2 = await svc.search_memory(app_name="test", user_id="test-mem-athlete", query="swimming")
    ftp_count = len([m for m in result2.memories if "FTP" in (m.content.parts[0].text if m.content.parts else "")])
    assert ftp_count == 0

    # Cleanup
    from server.database import get_db
    with get_db() as conn:
        conn.execute("DELETE FROM coach_memory WHERE user_id = 'test-mem-athlete'")


@pytest.mark.asyncio
async def test_memory_deduplication():
    from server.coaching.memory_service import DbMemoryService
    from google.adk.sessions import Session
    from google.adk.events import Event
    from google.genai import types

    svc = DbMemoryService()

    session = Session(
        app_name="test",
        user_id="test-dedup-athlete",
        id="test-dedup-s1",
        state={},
        events=[
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="How is my CTL?")],
                ),
            ),
        ],
    )

    # Add same session twice
    await svc.add_session_to_memory(session)
    await svc.add_session_to_memory(session)

    result = await svc.search_memory(app_name="test", user_id="test-dedup-athlete", query="CTL")
    assert len(result.memories) == 1

    # Cleanup
    from server.database import get_db
    with get_db() as conn:
        conn.execute("DELETE FROM coach_memory WHERE user_id = 'test-dedup-athlete'")


# --- API endpoint tests ---

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from server.main import app
    return TestClient(app)


def test_sessions_list_endpoint(client):
    resp = client.get("/api/coaching/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_session_not_found(client):
    resp = client.get("/api/coaching/sessions/nonexistent-id")
    assert resp.status_code == 404
