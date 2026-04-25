"""Integration tests for timezone-aware ride queries.

Requires test database (coach-test-db on port 5433).
Run via: ./scripts/run_integration_tests.sh

These tests verify that the AT TIME ZONE pattern produces correct results
when deriving local dates from UTC start_time values stored as TEXT.
"""


def test_ride_local_date_derivation(db_conn):
    """A ride at 2026-04-09T03:00:00Z should appear as 2026-04-08 in America/Chicago (UTC-5 in April)."""
    db_conn.execute(
        "INSERT INTO rides (start_time, filename, sport, duration_s) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (filename) DO NOTHING",
        ("2026-04-09T03:00:00Z", "tz_test_1", "cycling", 3600),
    )
    db_conn.commit()

    row = db_conn.execute(
        "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS local_date FROM rides WHERE filename = %s",
        ("America/Chicago", "tz_test_1"),
    ).fetchone()

    assert row is not None
    assert row["local_date"] == "2026-04-08"


def test_ride_local_date_utc(db_conn):
    """Same ride should appear as 2026-04-09 in UTC."""
    # Insert in case test_ride_local_date_derivation didn't run first
    db_conn.execute(
        "INSERT INTO rides (start_time, filename, sport, duration_s) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (filename) DO NOTHING",
        ("2026-04-09T03:00:00Z", "tz_test_1", "cycling", 3600),
    )
    db_conn.commit()

    row = db_conn.execute(
        "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS local_date FROM rides WHERE filename = %s",
        ("UTC", "tz_test_1"),
    ).fetchone()

    assert row is not None
    assert row["local_date"] == "2026-04-09"


def test_ride_date_filter_timezone_aware(db_conn):
    """Filtering by local date 2026-04-08 in Chicago should include the ride."""
    # Ensure test ride exists
    db_conn.execute(
        "INSERT INTO rides (start_time, filename, sport, duration_s) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (filename) DO NOTHING",
        ("2026-04-09T03:00:00Z", "tz_test_1", "cycling", 3600),
    )
    db_conn.commit()

    rows = db_conn.execute(
        """SELECT filename FROM rides
           WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE""",
        ("America/Chicago", "2026-04-08"),
    ).fetchall()

    filenames = [r["filename"] for r in rows]
    assert "tz_test_1" in filenames


def test_ride_date_filter_excludes_wrong_timezone(db_conn):
    """Filtering by local date 2026-04-09 in Chicago should NOT include the ride
    (it's April 8 in Chicago)."""
    db_conn.execute(
        "INSERT INTO rides (start_time, filename, sport, duration_s) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (filename) DO NOTHING",
        ("2026-04-09T03:00:00Z", "tz_test_1", "cycling", 3600),
    )
    db_conn.commit()

    rows = db_conn.execute(
        """SELECT filename FROM rides
           WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE
           AND filename = %s""",
        ("America/Chicago", "2026-04-09", "tz_test_1"),
    ).fetchall()

    assert len(rows) == 0


def test_pmc_groups_by_local_date(db_conn):
    """compute_daily_pmc should group rides by local date when given a timezone."""
    # Insert a ride with TSS at 03:00 UTC = 10:00 PM CDT on April 8
    db_conn.execute(
        "INSERT INTO rides (start_time, filename, sport, duration_s, tss, ftp, weight) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (filename) DO NOTHING",
        ("2026-04-09T03:00:00Z", "pmc_tz_test", "cycling", 3600, 80, 250, 75),
    )
    db_conn.commit()

    from server.ingest import compute_daily_pmc
    compute_daily_pmc(db_conn, tz_name="America/Chicago")

    row = db_conn.execute(
        "SELECT date, total_tss FROM daily_metrics WHERE date = %s",
        ("2026-04-08",),
    ).fetchone()

    # The ride at 03:00 UTC = 10:00 PM CDT on April 8 should appear under April 8
    assert row is not None
    assert row["total_tss"] >= 80


def test_tss_aggregation_by_timezone(db_conn):
    """Two rides on different UTC dates should land on the same local date
    when both fall within the same local calendar day."""
    # Ride 1: 2026-04-10T01:00:00Z = April 9 20:00 CDT
    db_conn.execute(
        "INSERT INTO rides (start_time, filename, sport, duration_s, tss, ftp, weight) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (filename) DO NOTHING",
        ("2026-04-10T01:00:00Z", "tz_agg_1", "cycling", 3600, 50, 250, 75),
    )
    # Ride 2: 2026-04-10T04:00:00Z = April 9 23:00 CDT
    db_conn.execute(
        "INSERT INTO rides (start_time, filename, sport, duration_s, tss, ftp, weight) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (filename) DO NOTHING",
        ("2026-04-10T04:00:00Z", "tz_agg_2", "cycling", 3600, 30, 250, 75),
    )
    db_conn.commit()

    # Both should aggregate to April 9 in Chicago
    row = db_conn.execute(
        """SELECT (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE::TEXT AS local_date,
                  SUM(tss) as total_tss
           FROM rides
           WHERE filename IN ('tz_agg_1', 'tz_agg_2')
             AND tss > 0
           GROUP BY (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE""",
        ("America/Chicago", "America/Chicago"),
    ).fetchone()

    assert row is not None
    assert row["local_date"] == "2026-04-09"
    assert row["total_tss"] == 80
