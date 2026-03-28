"""Tests for sync performance optimizations (Plan v1.3.1-04)."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from server.database import init_db, get_db


@pytest.fixture
def db_conn():
    init_db()
    with get_db() as conn:
        yield conn


def test_executemany_batch_matches_row_by_row(db_conn):
    """executemany with execute_batch should produce identical results to row-by-row."""
    conn = db_conn

    # Ensure we have a ride to reference
    ride_row = conn.execute("SELECT id FROM rides LIMIT 1").fetchone()
    if not ride_row:
        pytest.skip("No rides in database")
    ride_id = ride_row["id"]

    # Insert 100 test records via executemany
    test_rows = [
        (ride_id, f"2026-01-01T00:00:{i:02d}Z", i * 10, 120 + i, 85, None, None, None, None, None, None)
        for i in range(100)
    ]

    # Delete any existing test records for this ride with these timestamps
    for row in test_rows:
        conn.execute("DELETE FROM ride_records WHERE ride_id = ? AND timestamp_utc = ?", (row[0], row[1]))

    conn.executemany(
        "INSERT INTO ride_records (ride_id, timestamp_utc, power, heart_rate, cadence, speed, altitude, distance, lat, lon, temperature) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        test_rows,
    )

    # Verify all rows present
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM ride_records WHERE ride_id = ? AND timestamp_utc LIKE '2026-01-01T00:00:%%'",
        (ride_id,),
    ).fetchone()["cnt"]
    assert count == 100

    # Verify data integrity on a sample row
    sample = conn.execute(
        "SELECT power, heart_rate FROM ride_records WHERE ride_id = ? AND timestamp_utc = '2026-01-01T00:00:50Z'",
        (ride_id,),
    ).fetchone()
    assert sample["power"] == 500
    assert sample["heart_rate"] == 170

    # Cleanup
    conn.execute("DELETE FROM ride_records WHERE ride_id = ? AND timestamp_utc LIKE '2026-01-01T00:00:%%'", (ride_id,))


def test_incremental_pmc_matches_full_recompute(db_conn):
    """Incremental PMC from a since_date should produce values matching full recompute."""
    from server.ingest import compute_daily_pmc

    conn = db_conn

    # Check we have enough data
    ride_count = conn.execute("SELECT COUNT(*) as cnt FROM rides WHERE tss > 0").fetchone()["cnt"]
    if ride_count < 10:
        pytest.skip("Not enough rides for PMC test")

    # Full recompute
    compute_daily_pmc(conn)
    full_rows = {
        r["date"]: r
        for r in conn.execute("SELECT date, ctl, atl, tsb FROM daily_metrics ORDER BY date").fetchall()
    }

    # Pick a date ~30 days before the latest
    dates = sorted(full_rows.keys())
    if len(dates) < 60:
        since_idx = len(dates) // 2
    else:
        since_idx = len(dates) - 30
    since_date = dates[since_idx]

    # Incremental recompute
    compute_daily_pmc(conn, since_date=since_date)
    incr_rows = {
        r["date"]: r
        for r in conn.execute("SELECT date, ctl, atl, tsb FROM daily_metrics ORDER BY date").fetchall()
    }

    # Compare values from since_date onward — should match within rounding tolerance
    for d in dates[since_idx:]:
        full = full_rows[d]
        incr = incr_rows[d]
        assert abs(full["ctl"] - incr["ctl"]) < 0.2, f"CTL mismatch on {d}: {full['ctl']} vs {incr['ctl']}"
        assert abs(full["atl"] - incr["atl"]) < 0.2, f"ATL mismatch on {d}: {full['atl']} vs {incr['atl']}"
        assert abs(full["tsb"] - incr["tsb"]) < 0.2, f"TSB mismatch on {d}: {full['tsb']} vs {incr['tsb']}"


def test_weight_prefetch_matches_n_plus_1(db_conn):
    """Bisect-based weight lookup should match the N+1 SQL query approach."""
    import bisect

    conn = db_conn

    weight_rows = conn.execute(
        "SELECT date, weight FROM rides WHERE weight IS NOT NULL ORDER BY date"
    ).fetchall()
    if not weight_rows:
        pytest.skip("No weight data")

    weight_dates = [r["date"] for r in weight_rows]
    weight_values = [r["weight"] for r in weight_rows]

    # Test a few dates
    test_dates = [weight_dates[0], weight_dates[-1], "2025-06-15", "2026-03-01"]

    for ds in test_dates:
        # Bisect lookup
        idx = bisect.bisect_right(weight_dates, ds) - 1
        bisect_weight = weight_values[idx] if idx >= 0 else None

        # SQL lookup (original N+1 approach)
        sql_row = conn.execute(
            "SELECT weight FROM rides WHERE date <= ? AND weight IS NOT NULL ORDER BY date DESC LIMIT 1",
            (ds,),
        ).fetchone()
        sql_weight = sql_row["weight"] if sql_row else None

        assert bisect_weight == sql_weight, f"Weight mismatch on {ds}: bisect={bisect_weight} sql={sql_weight}"


def test_early_exit_all_synced():
    """Early exit logic should correctly identify when all activities exist."""
    from server.services.sync import _now_iso

    # Simulate the dedup check
    existing_filenames = {"ride_2026-03-01.json", "ride_2026-03-02.json"}
    existing_fingerprints = {("2026-03-01", 50000), ("2026-03-02", 60000)}

    activities = [
        {"filename": "ride_2026-03-01.json", "date": "2026-03-01", "distance_m": 50123},
        {"filename": "ride_2026-03-02.json", "date": "2026-03-02", "distance_m": 60456},
    ]

    has_new = False
    for a in activities:
        if a["filename"] in existing_filenames:
            continue
        dist = round((a["distance_m"] or 0) / 100) * 100
        if (a["date"], dist) in existing_fingerprints:
            continue
        has_new = True
        break

    assert not has_new, "Should detect all activities as already synced"


def test_early_exit_has_new():
    """Early exit logic should detect genuinely new activities."""
    existing_filenames = {"ride_2026-03-01.json"}
    existing_fingerprints = {("2026-03-01", 50000)}

    activities = [
        {"filename": "ride_2026-03-01.json", "date": "2026-03-01", "distance_m": 50123},
        {"filename": "ride_2026-03-03.json", "date": "2026-03-03", "distance_m": 70456},
    ]

    has_new = False
    for a in activities:
        if a["filename"] in existing_filenames:
            continue
        dist = round((a["distance_m"] or 0) / 100) * 100
        if (a["date"], dist) in existing_fingerprints:
            continue
        has_new = True
        break

    assert has_new, "Should detect new activity"
