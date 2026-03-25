"""Migrate data from local SQLite to Neon PostgreSQL using fast bulk inserts."""

import os
import sys
import sqlite3
import time

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SQLITE_PATH = os.environ.get("COACH_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "coach.db"))

if not DATABASE_URL.startswith("postgres"):
    print("ERROR: DATABASE_URL not set or not a postgres URL")
    sys.exit(1)

import psycopg2
from psycopg2.extras import execute_values


def get_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_table(pg, lite, table, columns, batch_size=5000):
    """Bulk migrate a table from SQLite to Postgres."""
    cols = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    # Check if already populated
    cur = pg.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"  {table}: already has {existing} rows, skipping")
        cur.close()
        return

    rows = lite.execute(f"SELECT {cols} FROM {table}").fetchall()
    if not rows:
        print(f"  {table}: no data to migrate")
        cur.close()
        return

    total = len(rows)
    print(f"  {table}: migrating {total} rows...", end="", flush=True)
    start = time.time()

    # Use execute_values for fast bulk insert
    template = f"({placeholders})"
    insert_sql = f"INSERT INTO {table} ({cols}) VALUES %s"

    for i in range(0, total, batch_size):
        batch = rows[i:i + batch_size]
        values = [tuple(row) for row in batch]
        execute_values(cur, insert_sql, values, template=template, page_size=batch_size)
        pg.commit()
        pct = min(100, int((i + len(batch)) / total * 100))
        print(f"\r  {table}: migrating {total} rows... {pct}%", end="", flush=True)

    # Reset sequence to max id
    if "id" in columns:
        cur.execute(f"SELECT MAX(id) FROM {table}")
        max_id = cur.fetchone()[0] or 0
        cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), %s)", (max_id,))
        pg.commit()

    elapsed = time.time() - start
    print(f"\r  {table}: migrated {total} rows in {elapsed:.1f}s")
    cur.close()


def main():
    print(f"SQLite: {SQLITE_PATH}")
    print(f"Postgres: {DATABASE_URL[:50]}...")
    print()

    lite = get_sqlite()
    pg = psycopg2.connect(DATABASE_URL)

    # Initialize schema first
    from server.database import init_db
    init_db()
    print("Schema initialized.\n")

    # Migrate tables in dependency order
    migrate_table(pg, lite, "rides", [
        "id", "date", "filename", "sport", "sub_sport", "duration_s", "distance_m",
        "avg_power", "normalized_power", "max_power", "avg_hr", "max_hr", "avg_cadence",
        "total_ascent", "total_descent", "total_calories", "tss", "intensity_factor",
        "ftp", "total_work_kj", "training_effect", "variability_index",
        "best_1min_power", "best_5min_power", "best_20min_power", "best_60min_power",
        "weight", "start_lat", "start_lon",
    ])

    migrate_table(pg, lite, "ride_records", [
        "id", "ride_id", "timestamp", "power", "heart_rate", "cadence",
        "speed", "altitude", "distance", "lat", "lon", "temperature",
    ], batch_size=10000)

    migrate_table(pg, lite, "planned_workouts", [
        "id", "date", "name", "sport", "total_duration_s", "workout_xml",
    ])

    migrate_table(pg, lite, "daily_metrics", [
        "date", "total_tss", "ctl", "atl", "tsb", "weight", "notes",
    ])

    migrate_table(pg, lite, "power_bests", [
        "id", "ride_id", "date", "duration_s", "power",
    ])

    migrate_table(pg, lite, "periodization_phases", [
        "id", "name", "start_date", "end_date", "focus",
        "hours_per_week_low", "hours_per_week_high", "tss_target_low", "tss_target_high",
    ])

    migrate_table(pg, lite, "workout_templates", [
        "id", "key", "name", "description", "category", "steps", "source", "created_at",
    ])

    migrate_table(pg, lite, "coach_settings", [
        "key", "value",
    ])

    migrate_table(pg, lite, "chat_sessions", [
        "session_id", "user_id", "title", "created_at", "updated_at",
    ])

    migrate_table(pg, lite, "chat_events", [
        "id", "session_id", "author", "role", "content_text", "timestamp",
    ])

    migrate_table(pg, lite, "coach_memory", [
        "id", "user_id", "author", "content_text", "timestamp",
    ])

    # Final summary
    cur = pg.cursor()
    for t in ["rides", "ride_records", "planned_workouts", "daily_metrics", "power_bests"]:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {cur.fetchone()[0]}")
    cur.close()

    pg.close()
    lite.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    main()
