"""Tests for data-access queries."""

import pytest
from server.database import get_db
from server.queries import get_latest_metric

def test_get_latest_metric():
    """Test historical and fallback lookups for athlete metrics."""
    
    with get_db() as conn:
        # Use a unique key for testing to avoid wiping real data
        test_key = "test_ftp_lookup"
        
        # Clear only the test key to ensure clean state
        conn.execute("DELETE FROM athlete_settings WHERE key = %s", (test_key,))
        
        # Set up current settings (fallback)
        conn.execute(
            "INSERT INTO athlete_settings (key, value, date_set) VALUES (%s, %s, CURRENT_DATE)",
            (test_key, "250")
        )
        
        # We need historical entries. athlete_settings stores history by date_set.
        # We'll insert two more entries for the same key with older dates.
        # Note: set_athlete_setting normally deactivates old ones, but the query 
        # looks at date_set regardless of is_active in get_latest_metric.
        conn.execute(
            "INSERT INTO athlete_settings (key, value, date_set, is_active) VALUES (%s, %s, %s, %s)",
            (test_key, "200", "2023-01-01", False)
        )
        conn.execute(
            "INSERT INTO athlete_settings (key, value, date_set, is_active) VALUES (%s, %s, %s, %s)",
            (test_key, "220", "2023-06-01", False)
        )
        
        # 1. Date between two log entries -> should return the one on or before
        assert get_latest_metric(conn, test_key, '2023-05-01') == 200.0
        
        # 2. Date before any log entries -> should return fallback from DEFAULT if nothing <= date
        # If there are no entries <= 2022-01-01, it falls back to ATHLETE_SETTINGS_DEFAULTS
        # The query in queries.py is: SELECT value FROM athlete_settings WHERE key = %s AND date_set <= %s ORDER BY date_set DESC, id DESC LIMIT 1
        # So for 2022-01-01, it should find nothing and return default.
        from server.database import ATHLETE_SETTINGS_DEFAULTS
        default_val = float(ATHLETE_SETTINGS_DEFAULTS.get(test_key, 0.0))
        assert get_latest_metric(conn, test_key, '2022-01-01') == default_val
        
        # 3. Date exactly on a log entry
        assert get_latest_metric(conn, test_key, '2023-06-01') == 220.0
        
        # 4. Date after some log entries but before current
        assert get_latest_metric(conn, test_key, '2024-01-01') == 220.0

        # Cleanup
        conn.execute("DELETE FROM athlete_settings WHERE key = %s", (test_key,))

