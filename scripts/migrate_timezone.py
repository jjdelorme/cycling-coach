"""Timezone-awareness schema migration.

This script:
1. Fixes historical non-UTC start_time values using GPS coordinates (timezonefinder)
   or falls back to America/New_York for indoor rides without GPS.
2. Drops rides.date column (no longer read by application code).
3. Promotes TEXT columns to proper DATE/TIMESTAMPTZ types.
4. Updates indexes.

SAFETY: Verify DATABASE_URL points to localhost before running.

Usage:
    source venv/bin/activate
    python scripts/migrate_timezone.py [--dry-run]
"""

import os
import sys
import argparse

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get(
    "CYCLING_COACH_DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql://postgres:dev@localhost:5432/coach"),
)


def fix_historical_start_times(conn):
    """Fix non-UTC start_time values using GPS coordinates or Eastern Time fallback."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Find rides with timezone-naive start_time (no Z, no +/- offset)
    cur.execute("""
        SELECT id, start_time, start_lat, start_lon
        FROM rides
        WHERE start_time IS NOT NULL
          AND LENGTH(start_time) > 10
          AND start_time NOT LIKE '%%Z'
          AND start_time NOT LIKE '%%+%%'
          AND start_time NOT SIMILAR TO '%%[-][0-9][0-9]:[0-9][0-9]'
    """)
    naive_rides = cur.fetchall()

    if not naive_rides:
        print("No timezone-naive start_time values found.")
        return 0

    print(f"Found {len(naive_rides)} rides with timezone-naive start_time values.")

    # Try to import timezonefinder for GPS-based resolution
    tf = None
    try:
        from timezonefinder import TimezoneFinder
        tf = TimezoneFinder()
        print("Using timezonefinder for GPS-based timezone resolution.")
    except ImportError:
        print("WARNING: timezonefinder not installed. Using America/New_York for all naive timestamps.")
        print("  Install with: pip install timezonefinder")

    from datetime import datetime
    from zoneinfo import ZoneInfo

    fixed = 0
    for ride in naive_rides:
        ride_id = ride["id"]
        naive_ts = ride["start_time"]
        lat = ride["start_lat"]
        lon = ride["start_lon"]

        # Determine timezone from GPS or fallback
        tz_name = None
        if tf and lat is not None and lon is not None:
            tz_name = tf.timezone_at(lat=lat, lng=lon)

        if not tz_name:
            # Indoor ride or no GPS — fallback to Eastern Time
            tz_name = "America/New_York"

        # Parse naive timestamp, treat as local in determined timezone, convert to UTC
        try:
            dt_naive = datetime.fromisoformat(naive_ts)
            tz = ZoneInfo(tz_name)
            dt_local = dt_naive.replace(tzinfo=tz)
            dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
            utc_str = dt_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00")

            cur.execute(
                "UPDATE rides SET start_time = %s WHERE id = %s",
                (utc_str, ride_id),
            )
            fixed += 1
        except Exception as e:
            print(f"  ERROR fixing ride {ride_id} ({naive_ts}): {e}")

    print(f"Fixed {fixed}/{len(naive_rides)} timezone-naive start_time values.")
    return fixed


def run_migration(conn, dry_run=False):
    """Run the full timezone schema migration."""
    cur = conn.cursor()

    print("\n=== Step 1: Fix historical timezone-naive start_time values ===")
    fixed = fix_historical_start_times(conn)
    if dry_run:
        print("DRY RUN — rolling back historical fixes.")
        conn.rollback()
    else:
        conn.commit()
        print(f"Committed {fixed} historical fixes.")

    migration_sql = """
    -- Step 2: Drop rides.date column
    ALTER TABLE rides DROP COLUMN IF EXISTS date;

    -- Step 3: Promote start_time TEXT -> TIMESTAMPTZ
    ALTER TABLE rides ALTER COLUMN start_time TYPE TIMESTAMPTZ USING start_time::TIMESTAMPTZ;

    -- Step 4: Promote ride_records.timestamp_utc TEXT -> TIMESTAMPTZ
    ALTER TABLE ride_records ALTER COLUMN timestamp_utc TYPE TIMESTAMPTZ USING timestamp_utc::TIMESTAMPTZ;

    -- Step 5: Promote other TEXT date columns to proper types
    ALTER TABLE daily_metrics ALTER COLUMN date TYPE DATE USING date::DATE;
    ALTER TABLE planned_workouts ALTER COLUMN date TYPE DATE USING date::DATE;
    ALTER TABLE periodization_phases ALTER COLUMN start_date TYPE DATE USING start_date::DATE;
    ALTER TABLE periodization_phases ALTER COLUMN end_date TYPE DATE USING end_date::DATE;
    ALTER TABLE power_bests ALTER COLUMN date TYPE DATE USING date::DATE;
    ALTER TABLE athlete_settings ALTER COLUMN date_set TYPE DATE USING date_set::DATE;

    -- Step 6: Update indexes
    DROP INDEX IF EXISTS idx_rides_date;
    CREATE INDEX IF NOT EXISTS idx_rides_start_time ON rides(start_time);
    """

    if dry_run:
        print("\n=== DRY RUN — would execute migration SQL: ===")
        print(migration_sql)
        print("=== DRY RUN complete — no schema changes applied. ===")
        return

    print("\n=== Step 2-6: Applying schema migration ===")
    cur.execute(migration_sql)
    conn.commit()
    print("Schema migration applied successfully.")

    # Verify
    print("\n=== Verification ===")
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'rides'
        ORDER BY ordinal_position
    """)
    print("rides table columns:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    # Check rides.date is gone
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'rides' AND column_name = 'date'
    """)
    if cur.fetchone():
        print("ERROR: rides.date column still exists!")
    else:
        print("OK: rides.date column dropped.")

    # Check start_time type
    cur.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'rides' AND column_name = 'start_time'
    """)
    row = cur.fetchone()
    if row and "timestamp" in row[0].lower():
        print(f"OK: rides.start_time is {row[0]}.")
    else:
        print(f"WARNING: rides.start_time type is {row[0] if row else 'MISSING'}.")


def main():
    parser = argparse.ArgumentParser(description="Timezone-awareness schema migration")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without applying changes")
    args = parser.parse_args()

    # Safety check — allow localhost, 127.0.0.1, and svc-pgdb (dev container)
    safe_hosts = ("localhost", "127.0.0.1", "svc-pgdb")
    if not any(host in DATABASE_URL for host in safe_hosts):
        print(f"SAFETY: DATABASE_URL does not point to a dev database: {DATABASE_URL}")
        print("Set DATABASE_URL to a local/dev database before running this migration.")
        sys.exit(1)

    print(f"Connecting to: {DATABASE_URL}")
    conn = psycopg2.connect(DATABASE_URL)

    try:
        run_migration(conn, dry_run=args.dry_run)
    except Exception as e:
        conn.rollback()
        print(f"\nMigration FAILED: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
