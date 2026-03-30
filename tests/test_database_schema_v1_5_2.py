"""Tests for v1.5.2 database schema extensions."""

import pytest
from server.database import get_db, init_db

def test_rides_new_columns():
    """Test that new columns in rides table work as expected."""
    # Ensure DB is initialized
    init_db()
    
    with get_db() as conn:
        # Insert a ride with new columns
        conn.execute(
            """INSERT INTO rides (date, filename, sport, duration_s, has_power_data, data_status)
            VALUES ('2025-07-01', 'test_new_columns.json', 'cycling', 3600, TRUE, 'cleaned')
            ON CONFLICT (filename) DO UPDATE SET 
                has_power_data = EXCLUDED.has_power_data,
                data_status = EXCLUDED.data_status"""
        )
        
        row = conn.execute("SELECT has_power_data, data_status FROM rides WHERE filename='test_new_columns.json'").fetchone()
        
    assert row is not None
    assert row["has_power_data"] is True
    assert row["data_status"] == 'cleaned'
    
    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM rides WHERE filename='test_new_columns.json'")

def test_power_bests_new_columns():
    """Test that new columns in power_bests table work as expected."""
    # Ensure DB is initialized
    init_db()
    
    with get_db() as conn:
        # Need a ride first for the foreign key
        conn.execute(
            "INSERT INTO rides (date, filename, sport) VALUES ('2025-07-01', 'test_power_bests.json', 'cycling') ON CONFLICT (filename) DO NOTHING"
        )
        ride_id = conn.execute("SELECT id FROM rides WHERE filename='test_power_bests.json'").fetchone()["id"]
        
        # Insert power_best with new columns
        conn.execute(
            """INSERT INTO power_bests (ride_id, date, duration_s, power, avg_hr, avg_cadence, start_offset_s)
            VALUES (%s, '2025-07-01', 60, 400, 170, 95, 1200)""",
            (ride_id,)
        )
        
        row = conn.execute("SELECT avg_hr, avg_cadence, start_offset_s FROM power_bests WHERE ride_id=%s AND duration_s=60", (ride_id,)).fetchone()
        
    assert row is not None
    assert row["avg_hr"] == 170
    assert row["avg_cadence"] == 95
    assert row["start_offset_s"] == 1200
    
    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM power_bests WHERE ride_id=%s", (ride_id,))
        conn.execute("DELETE FROM rides WHERE id=%s", (ride_id,))
