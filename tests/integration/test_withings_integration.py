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
    """store_measurements must insert then update on conflict, preserving measured_at."""
    from server.services.withings import store_measurements

    test_date = "2099-01-15"  # Far future — won't collide with seed data

    try:
        # Insert with full UTC timestamp
        count = store_measurements([{
            "date": test_date,
            "measured_at": "2099-01-15T06:30:00Z",
            "weight_kg": 75.0,
        }])
        assert count == 1

        row = db_conn.execute(
            "SELECT weight_kg, measured_at FROM body_measurements WHERE date=%s AND source='withings'",
            (test_date,),
        ).fetchone()
        assert row is not None
        assert abs(row["weight_kg"] - 75.0) < 0.01
        assert row["measured_at"] == "2099-01-15T06:30:00Z"

        # Upsert — update to new weight and timestamp
        store_measurements([{
            "date": test_date,
            "measured_at": "2099-01-15T07:00:00Z",
            "weight_kg": 74.5,
        }])
        row2 = db_conn.execute(
            "SELECT weight_kg, measured_at FROM body_measurements WHERE date=%s AND source='withings'",
            (test_date,),
        ).fetchone()
        assert abs(row2["weight_kg"] - 74.5) < 0.01
        assert row2["measured_at"] == "2099-01-15T07:00:00Z"

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

    test_date = str(row["date"])
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


# ---------------------------------------------------------------------------
# Webhook endpoint: POST /api/withings/webhook
# ---------------------------------------------------------------------------

def test_webhook_endpoint_stores_measurement(client, db_conn):
    """POST /api/withings/webhook must accept Withings form POST and write to body_measurements."""
    from unittest.mock import patch
    from server.database import set_setting

    test_date = "2099-03-15"
    start_ts = 4073760000  # 2099-03-15T00:00:00Z
    end_ts   = 4073846400  # 2099-03-16T00:00:00Z

    set_setting("withings_user_id", "user_webhook_test")
    try:
        with patch(
            "server.services.withings.fetch_weight_measurements",
            return_value=[{
                "date": test_date,
                "measured_at": f"{test_date}T06:30:00Z",
                "weight_kg": 73.8,
            }],
        ), patch("server.ingest.compute_daily_pmc"):
            resp = client.post("/api/withings/webhook", data={
                "userid": "user_webhook_test",
                "appli": 1,
                "startdate": start_ts,
                "enddate": end_ts,
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["synced"] == 1

        row = db_conn.execute(
            "SELECT weight_kg, measured_at FROM body_measurements WHERE date=%s AND source='withings'",
            (test_date,),
        ).fetchone()
        assert row is not None
        assert abs(row["weight_kg"] - 73.8) < 0.01
        assert row["measured_at"] == f"{test_date}T06:30:00Z"

    finally:
        db_conn.execute(
            "DELETE FROM body_measurements WHERE date=%s AND source='withings'", (test_date,)
        )
        set_setting("withings_user_id", "")


def test_webhook_endpoint_ignores_non_weight_appli(client):
    """POST /api/withings/webhook must return ignored for appli != 1 (e.g. sleep, activity)."""
    resp = client.post("/api/withings/webhook", data={
        "userid": "any_user",
        "appli": 44,  # sleep data
        "startdate": 0,
        "enddate": 1,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_webhook_endpoint_ignores_userid_mismatch(client):
    """Webhook must silently ignore notifications intended for a different user."""
    from server.database import set_setting

    set_setting("withings_user_id", "expected_user")
    try:
        resp = client.post("/api/withings/webhook", data={
            "userid": "intruder",
            "appli": 1,
            "startdate": 0,
            "enddate": 1,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
    finally:
        set_setting("withings_user_id", "")
