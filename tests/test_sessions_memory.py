"""Tests for persistent sessions and memory services."""

import os
import pytest
from unittest.mock import patch, AsyncMock

from server.database import init_db


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    with patch("server.database.get_db_path", return_value=db_path):
        yield db_path


# --- SqliteSessionService tests ---

@pytest.mark.asyncio
async def test_create_and_get_session(tmp_db):
    with patch("server.coaching.sqlite_session_service.get_db") as mock_get_db:
        from server.database import get_connection
        import contextlib

        @contextlib.contextmanager
        def _fake_db():
            conn = get_connection(tmp_db)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        mock_get_db.side_effect = _fake_db

        from server.coaching.sqlite_session_service import SqliteSessionService
        svc = SqliteSessionService()

        session = await svc.create_session(
            app_name="test", user_id="athlete", session_id="s1"
        )
        assert session.id == "s1"

        retrieved = await svc.get_session(
            app_name="test", user_id="athlete", session_id="s1"
        )
        assert retrieved is not None
        assert retrieved.id == "s1"


@pytest.mark.asyncio
async def test_list_sessions(tmp_db):
    with patch("server.coaching.sqlite_session_service.get_db") as mock_get_db:
        from server.database import get_connection
        import contextlib

        @contextlib.contextmanager
        def _fake_db():
            conn = get_connection(tmp_db)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        mock_get_db.side_effect = _fake_db

        from server.coaching.sqlite_session_service import SqliteSessionService
        svc = SqliteSessionService()

        await svc.create_session(app_name="test", user_id="athlete", session_id="s1")
        await svc.create_session(app_name="test", user_id="athlete", session_id="s2")

        result = await svc.list_sessions(app_name="test", user_id="athlete")
        assert len(result.sessions) == 2


@pytest.mark.asyncio
async def test_delete_session(tmp_db):
    with patch("server.coaching.sqlite_session_service.get_db") as mock_get_db:
        from server.database import get_connection
        import contextlib

        @contextlib.contextmanager
        def _fake_db():
            conn = get_connection(tmp_db)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        mock_get_db.side_effect = _fake_db

        from server.coaching.sqlite_session_service import SqliteSessionService
        svc = SqliteSessionService()

        await svc.create_session(app_name="test", user_id="athlete", session_id="s1")
        await svc.delete_session(app_name="test", user_id="athlete", session_id="s1")

        result = await svc.get_session(app_name="test", user_id="athlete", session_id="s1")
        assert result is None


# --- SqliteMemoryService tests ---

@pytest.mark.asyncio
async def test_memory_add_and_search(tmp_db):
    with patch("server.coaching.sqlite_memory_service.get_db") as mock_get_db:
        from server.database import get_connection
        import contextlib

        @contextlib.contextmanager
        def _fake_db():
            conn = get_connection(tmp_db)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        mock_get_db.side_effect = _fake_db

        from server.coaching.sqlite_memory_service import SqliteMemoryService
        from google.adk.sessions import Session
        from google.adk.events import Event
        from google.genai import types

        svc = SqliteMemoryService()

        # Create a session with events
        session = Session(
            app_name="test",
            user_id="athlete",
            id="s1",
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
        result = await svc.search_memory(app_name="test", user_id="athlete", query="FTP")
        assert len(result.memories) >= 1

        # Search for unrelated term should return less
        result2 = await svc.search_memory(app_name="test", user_id="athlete", query="swimming")
        ftp_count = len([m for m in result2.memories if "FTP" in (m.content.parts[0].text if m.content.parts else "")])
        # "swimming" shouldn't match FTP memories
        assert ftp_count == 0


@pytest.mark.asyncio
async def test_memory_deduplication(tmp_db):
    with patch("server.coaching.sqlite_memory_service.get_db") as mock_get_db:
        from server.database import get_connection
        import contextlib

        @contextlib.contextmanager
        def _fake_db():
            conn = get_connection(tmp_db)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        mock_get_db.side_effect = _fake_db

        from server.coaching.sqlite_memory_service import SqliteMemoryService
        from google.adk.sessions import Session
        from google.adk.events import Event
        from google.genai import types

        svc = SqliteMemoryService()

        session = Session(
            app_name="test",
            user_id="athlete",
            id="s1",
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

        result = await svc.search_memory(app_name="test", user_id="athlete", query="CTL")
        assert len(result.memories) == 1


# --- API endpoint tests ---

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "coach.db")


@pytest.fixture(scope="module")
def client():
    os.environ["COACH_DB_PATH"] = DB_PATH
    if not os.path.exists(DB_PATH):
        pytest.skip("Database not found")
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
