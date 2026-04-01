"""Tests for ride deletion."""

import pytest
from server.database import get_db

def test_delete_ride(client):
    # 1. Get a ride to delete
    resp = client.get("/api/rides?limit=1")
    assert resp.status_code == 200
    rides = resp.json()
    assert len(rides) > 0
    ride_id = rides[0]["id"]
    
    # Check if dependencies exist (optional but good for verification)
    with get_db() as conn:
        records_count = conn.execute("SELECT COUNT(*) as count FROM ride_records WHERE ride_id = %s", (ride_id,)).fetchone()["count"]
        laps_count = conn.execute("SELECT COUNT(*) as count FROM ride_laps WHERE ride_id = %s", (ride_id,)).fetchone()["count"]
        # power_bests might not exist for all rides, but we can check if they are deleted if they do
        pb_count = conn.execute("SELECT COUNT(*) as count FROM power_bests WHERE ride_id = %s", (ride_id,)).fetchone()["count"]

    # 2. Delete the ride
    resp = client.delete(f"/api/rides/{ride_id}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    
    # 3. Assert ride is gone
    resp = client.get(f"/api/rides/{ride_id}")
    assert resp.status_code == 404
    
    # 4. Assert dependencies are gone
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) as count FROM ride_records WHERE ride_id = %s", (ride_id,)).fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) as count FROM ride_laps WHERE ride_id = %s", (ride_id,)).fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) as count FROM power_bests WHERE ride_id = %s", (ride_id,)).fetchone()["count"] == 0

def test_delete_nonexistent_ride(client):
    resp = client.delete("/api/rides/999999")
    assert resp.status_code == 404
