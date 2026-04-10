"""Tests for logging infrastructure (Plan v1.3.1-06)."""

import logging
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


def test_root_logger_has_handler():
    """After importing server.main, root logger should have handlers configured."""
    import server.main  # noqa: F401
    root = logging.getLogger()
    assert len(root.handlers) > 0


def test_sync_logger_not_silenced():
    """The sync logger should not have its own level set (inherits from root)."""
    sync_logger = logging.getLogger("server.services.sync")
    # Logger should not be explicitly set to a level that would silence INFO
    assert sync_logger.level == logging.NOTSET or sync_logger.level <= logging.INFO


def test_slow_query_logs_warning(db_conn):
    """Queries exceeding SLOW_QUERY_MS should emit a WARNING."""
    from server.database import _DbConnection

    # Create a mock connection whose cursor.execute sleeps 150ms
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.execute = lambda sql, params=None: time.sleep(0.15)
    mock_conn.cursor.return_value = mock_cursor
    db = _DbConnection(mock_conn)

    with patch("server.database.logger") as mock_logger:
        db.execute("SELECT 1")
        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0]
        assert args[0] == "slow_query"


def test_fast_query_no_warning(db_conn):
    """Fast queries should not produce a WARNING."""
    from server.database import _DbConnection

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    db = _DbConnection(mock_conn)

    with patch("server.database.logger") as mock_logger:
        db.execute("SELECT 1")
        mock_logger.warning.assert_not_called()


def test_api_request_logged():
    """GET /api/health should be logged by the request middleware."""
    from server.main import app
    client = TestClient(app)

    with patch("server.main.logger") as mock_logger:
        client.get("/api/health")
        # Find a call that includes the path
        info_calls = mock_logger.info.call_args_list
        logged_paths = [str(c) for c in info_calls]
        assert any("/api/health" in s for s in logged_paths)


def test_tlog_adds_timestamp():
    """_tlog should prefix with a bracketed ISO timestamp."""
    from server.services.sync import _tlog
    result = _tlog("test message")
    assert result.startswith("[")
    assert "Z]" in result
    assert "test message" in result
