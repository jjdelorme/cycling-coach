"""Tests for data-access queries."""

import pytest
from server.database import get_db, init_db
from server.queries import get_latest_metric

def test_get_latest_metric():
    """Test historical and fallback lookups for athlete metrics."""
    # Ensure DB is initialized
    init_db()
    
    with get_db() as conn:
        # Clear existing data to ensure clean state for test
        conn.execute("DELETE FROM athlete_log")
        conn.execute("DELETE FROM athlete_settings")
        
        # Set up current settings (fallback)
        conn.execute(
            "INSERT INTO athlete_settings (key, value) VALUES (%s, %s)",
            ("ftp", "250")
        )
        
        # Set up historical log entries
        # FTP=200 on '2023-01-01', FTP=220 on '2023-06-01'
        conn.execute(
            "INSERT INTO athlete_log (date, type, value) VALUES (%s, %s, %s)",
            ("2023-01-01", "ftp", 200)
        )
        conn.execute(
            "INSERT INTO athlete_log (date, type, value) VALUES (%s, %s, %s)",
            ("2023-06-01", "ftp", 220)
        )
        
        # 1. Date between two log entries -> should return the one on or before
        assert get_latest_metric(conn, 'ftp', '2023-05-01') == 200.0
        
        # 2. Date before any log entries -> should return fallback from athlete_settings
        # (The plan said 2024-01-01 == 250, but given the setup 2022-01-01 is what tests the fallback)
        assert get_latest_metric(conn, 'ftp', '2022-01-01') == 250.0
        
        # 3. Date exactly on a log entry
        assert get_latest_metric(conn, 'ftp', '2023-06-01') == 220.0
        
        # 4. Date after all log entries -> should return the last log entry
        assert get_latest_metric(conn, 'ftp', '2024-01-01') == 220.0
