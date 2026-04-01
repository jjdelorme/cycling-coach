"""Tests for database schema and basic operations."""

from server.database import get_db


def test_schema_creation():
    with get_db() as conn:
        tables = [
            row["tablename"]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            ).fetchall()
        ]
    assert "rides" in tables
    assert "ride_records" in tables
    assert "planned_workouts" in tables
    assert "daily_metrics" in tables
    assert "power_bests" in tables
    assert "periodization_phases" in tables


def test_insert_and_query_ride():
    with get_db() as conn:
        conn.execute(
            """INSERT INTO rides (date, filename, sport, sub_sport, duration_s, avg_power, tss, ftp)
            VALUES ('2025-06-01', 'test_ride_db.json', 'cycling', 'mountain', 3600, 200, 100, 250)
            ON CONFLICT (filename) DO NOTHING"""
        )
        row = conn.execute("SELECT * FROM rides WHERE filename='test_ride_db.json'").fetchone()

    assert row is not None
    assert row["date"] == "2025-06-01"
    assert row["avg_power"] == 200
    assert row["tss"] == 100

    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM rides WHERE filename='test_ride_db.json'")


def test_insert_ride_records():
    with get_db() as conn:
        conn.execute(
            """INSERT INTO rides (date, filename, sport, duration_s) VALUES ('2025-06-01', 'test_records.json', 'cycling', 3600)
            ON CONFLICT (filename) DO NOTHING"""
        )
        ride_id = conn.execute("SELECT id FROM rides WHERE filename='test_records.json'").fetchone()["id"]
        conn.execute(
            "INSERT INTO ride_records (ride_id, timestamp_utc, power, heart_rate) VALUES (%s, '2025-06-01T10:00:00', 200, 150)",
            (ride_id,),
        )
        records = conn.execute("SELECT * FROM ride_records WHERE ride_id=%s", (ride_id,)).fetchall()

    assert len(records) >= 1
    assert records[0]["power"] == 200

    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM ride_records WHERE ride_id IN (SELECT id FROM rides WHERE filename='test_records.json')")
        conn.execute("DELETE FROM rides WHERE filename='test_records.json'")


def test_daily_metrics():
    with get_db() as conn:
        conn.execute(
            "INSERT INTO daily_metrics (date, total_tss, ctl, atl, tsb) VALUES ('2099-06-01', 100, 50, 80, -30) ON CONFLICT (date) DO NOTHING"
        )
        row = conn.execute("SELECT * FROM daily_metrics WHERE date='2099-06-01'").fetchone()

    assert row["ctl"] == 50
    assert row["tsb"] == -30

    # Cleanup
    with get_db() as conn:
        conn.execute("DELETE FROM daily_metrics WHERE date='2099-06-01'")
