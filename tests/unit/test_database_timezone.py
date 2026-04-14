"""Unit tests for timezone-aware fixes in server/database.py."""
from unittest.mock import patch, MagicMock


def test_set_athlete_setting_uses_user_today_when_no_date_set():
    """set_athlete_setting must use user_today() for date_set when not provided."""
    mock_conn = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("server.database.get_db", return_value=mock_ctx), \
         patch("server.utils.dates.user_today", return_value="2026-04-14") as mock_today:
        from server.database import set_athlete_setting
        set_athlete_setting("ftp", "280")

    mock_today.assert_called_once()
    # Verify the INSERT used the mocked date
    insert_call = mock_conn.execute.call_args_list[-1]
    sql = insert_call[0][0]
    params = insert_call[0][1]
    assert "INSERT INTO athlete_settings" in sql
    assert params == ("ftp", "280", "2026-04-14")


def test_set_athlete_setting_uses_explicit_date_set():
    """set_athlete_setting must use the explicit date_set when provided."""
    mock_conn = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("server.database.get_db", return_value=mock_ctx):
        from server.database import set_athlete_setting
        set_athlete_setting("ftp", "280", date_set="2026-03-01")

    insert_call = mock_conn.execute.call_args_list[-1]
    params = insert_call[0][1]
    assert params == ("ftp", "280", "2026-03-01")
