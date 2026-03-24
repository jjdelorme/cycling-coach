"""Tests for database schema and basic operations."""

from server.database import init_db, get_db


def test_schema_creation(tmp_db):
    with get_db(tmp_db) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
    assert "rides" in tables
    assert "ride_records" in tables
    assert "planned_workouts" in tables
    assert "daily_metrics" in tables
    assert "power_bests" in tables
    assert "periodization_phases" in tables


def test_insert_and_query_ride(tmp_db):
    with get_db(tmp_db) as conn:
        conn.execute(
            """INSERT INTO rides (date, filename, sport, sub_sport, duration_s, avg_power, tss, ftp)
            VALUES ('2025-06-01', 'test_ride.json', 'cycling', 'mountain', 3600, 200, 100, 250)"""
        )
        row = conn.execute("SELECT * FROM rides WHERE filename='test_ride.json'").fetchone()

    assert row is not None
    assert row["date"] == "2025-06-01"
    assert row["avg_power"] == 200
    assert row["tss"] == 100


def test_insert_ride_records(tmp_db):
    with get_db(tmp_db) as conn:
        conn.execute(
            """INSERT INTO rides (date, filename, sport, duration_s) VALUES ('2025-06-01', 'test.json', 'cycling', 3600)"""
        )
        ride_id = conn.execute("SELECT id FROM rides").fetchone()["id"]
        conn.execute(
            "INSERT INTO ride_records (ride_id, timestamp, power, heart_rate) VALUES (?, '2025-06-01T10:00:00', 200, 150)",
            (ride_id,),
        )
        records = conn.execute("SELECT * FROM ride_records WHERE ride_id=?", (ride_id,)).fetchall()

    assert len(records) == 1
    assert records[0]["power"] == 200


def test_daily_metrics(tmp_db):
    with get_db(tmp_db) as conn:
        conn.execute(
            "INSERT INTO daily_metrics (date, total_tss, ctl, atl, tsb) VALUES ('2025-06-01', 100, 50, 80, -30)"
        )
        row = conn.execute("SELECT * FROM daily_metrics WHERE date='2025-06-01'").fetchone()

    assert row["ctl"] == 50
    assert row["tsb"] == -30
