"""Integration tests for Withings body weight integration.

Requires the test database container (port 5433).
Run via: ./scripts/run_integration_tests.sh
"""
import pytest


# ---------------------------------------------------------------------------
# API endpoint: GET /api/withings/status
# ---------------------------------------------------------------------------

def test_withings_status_returns_200_with_shape(client):
    """Status endpoint must return 200 with connected/configured keys."""
    resp = client.get("/api/withings/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "connected" in data
    assert "configured" in data
    assert isinstance(data["connected"], bool)
    assert isinstance(data["configured"], bool)


def test_withings_status_not_connected_by_default(client):
    """Without credentials stored, connected must be False."""
    resp = client.get("/api/withings/status")
    assert resp.status_code == 200
    # Test env has no withings tokens seeded
    assert resp.json()["connected"] is False


# ---------------------------------------------------------------------------
# DB: store_measurements upsert behavior
# ---------------------------------------------------------------------------

def test_store_measurements_inserts_and_upserts(db_conn):
    """store_measurements must insert then update on conflict."""
    from server.services.withings import store_measurements

    test_date = "2099-01-15"  # Far future — won't collide with seed data

    try:
        # Insert
        count = store_measurements([{"date": test_date, "weight_kg": 75.0}])
        assert count == 1

        row = db_conn.execute(
            "SELECT weight_kg FROM body_measurements WHERE date=%s AND source='withings'",
            (test_date,),
        ).fetchone()
        assert row is not None
        assert abs(row["weight_kg"] - 75.0) < 0.01

        # Upsert — update to new weight
        store_measurements([{"date": test_date, "weight_kg": 74.5}])
        row2 = db_conn.execute(
            "SELECT weight_kg FROM body_measurements WHERE date=%s AND source='withings'",
            (test_date,),
        ).fetchone()
        assert abs(row2["weight_kg"] - 74.5) < 0.01

    finally:
        db_conn.execute(
            "DELETE FROM body_measurements WHERE date=%s AND source='withings'",
            (test_date,),
        )


def test_store_measurements_empty_list_returns_zero(db_conn):
    from server.services.withings import store_measurements
    count = store_measurements([])
    assert count == 0


# ---------------------------------------------------------------------------
# PMC weight priority: Withings > ride weight
# ---------------------------------------------------------------------------

def test_pmc_weight_priority_withings_over_ride(db_conn):
    """Withings measurement must take priority over Garmin ride weight in PMC."""
    from server.services.withings import store_measurements
    from server.ingest import compute_daily_pmc

    # Find a date that has a daily_metrics row with a non-zero weight from seed data
    row = db_conn.execute(
        "SELECT date, weight FROM daily_metrics WHERE weight IS NOT NULL AND weight > 0 "
        "ORDER BY date DESC LIMIT 1"
    ).fetchone()

    if row is None:
        pytest.skip("No seed daily_metrics rows with weight found — cannot test priority")

    test_date = row["date"]
    original_weight = row["weight"]
    withings_weight = round(original_weight + 5.0, 1)  # Distinctly different value

    try:
        # Insert a Withings measurement that differs from the ride weight
        store_measurements([{"date": test_date, "weight_kg": withings_weight}])

        # Recompute PMC for just this date range
        compute_daily_pmc(db_conn, since_date=test_date)

        # Verify Withings weight won
        updated = db_conn.execute(
            "SELECT weight FROM daily_metrics WHERE date=%s", (test_date,)
        ).fetchone()
        assert updated is not None
        assert abs(updated["weight"] - withings_weight) < 0.01, (
            f"Expected Withings weight {withings_weight}, got {updated['weight']}"
        )

    finally:
        # Restore original weight and remove test Withings row
        db_conn.execute(
            "DELETE FROM body_measurements WHERE date=%s AND source='withings'", (test_date,)
        )
        db_conn.execute(
            "UPDATE daily_metrics SET weight=%s WHERE date=%s", (original_weight, test_date)
        )
