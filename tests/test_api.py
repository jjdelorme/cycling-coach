"""Tests for API endpoints using the real database."""

import os
import pytest
from fastapi.testclient import TestClient

from server.database import init_db, get_db

# Point to the real database for integration tests
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "coach.db")


@pytest.fixture(scope="module")
def client():
    os.environ["COACH_DB_PATH"] = DB_PATH
    if not os.path.exists(DB_PATH):
        pytest.skip("Database not found — run ingestion first")
    from server.main import app
    return TestClient(app)


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["rides"] == 291


def test_list_rides(client):
    resp = client.get("/api/rides?limit=10")
    assert resp.status_code == 200
    rides = resp.json()
    assert len(rides) <= 10
    assert "date" in rides[0]
    assert "avg_power" in rides[0]


def test_filter_rides_by_date(client):
    resp = client.get("/api/rides?start_date=2025-08-01&end_date=2025-08-31")
    assert resp.status_code == 200
    rides = resp.json()
    assert all("2025-08" in r["date"] for r in rides)


def test_get_single_ride(client):
    # Get first ride's ID
    resp = client.get("/api/rides?limit=1")
    ride_id = resp.json()[0]["id"]

    resp = client.get(f"/api/rides/{ride_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert "records" in detail
    assert len(detail["records"]) > 0


def test_ride_not_found(client):
    resp = client.get("/api/rides/99999")
    assert resp.status_code == 404


def test_weekly_summary(client):
    resp = client.get("/api/rides/summary/weekly")
    assert resp.status_code == 200
    weeks = resp.json()
    assert len(weeks) > 0
    assert "week" in weeks[0]
    assert "tss" in weeks[0]


def test_monthly_summary(client):
    resp = client.get("/api/rides/summary/monthly")
    assert resp.status_code == 200
    months = resp.json()
    assert len(months) > 0


def test_pmc(client):
    resp = client.get("/api/pmc")
    assert resp.status_code == 200
    pmc = resp.json()
    assert len(pmc) > 0
    assert "ctl" in pmc[0]


def test_pmc_current(client):
    resp = client.get("/api/pmc/current")
    assert resp.status_code == 200
    data = resp.json()
    assert "ctl" in data
    assert "tsb" in data


def test_power_curve(client):
    resp = client.get("/api/analysis/power-curve")
    assert resp.status_code == 200
    curve = resp.json()
    assert len(curve) > 0
    durations = [c["duration_s"] for c in curve]
    assert 60 in durations  # 1min
    assert 300 in durations  # 5min


def test_power_curve_history(client):
    resp = client.get("/api/analysis/power-curve/history")
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) > 0


def test_efficiency(client):
    resp = client.get("/api/analysis/efficiency")
    assert resp.status_code == 200
    ef = resp.json()
    assert len(ef) > 0
    assert "ef" in ef[0]


def test_ftp_history(client):
    resp = client.get("/api/analysis/ftp-history")
    assert resp.status_code == 200
    ftp = resp.json()
    assert len(ftp) > 0
    assert "ftp" in ftp[0]


def test_macro_plan(client):
    resp = client.get("/api/plan/macro")
    assert resp.status_code == 200
    phases = resp.json()
    assert len(phases) == 5
    assert phases[0]["name"] == "Base Rebuild"


def test_week_plan(client):
    resp = client.get("/api/plan/week/2025-08-15")
    assert resp.status_code == 200
    data = resp.json()
    assert "planned" in data
    assert "actual" in data


def test_compliance(client):
    resp = client.get("/api/plan/compliance")
    assert resp.status_code == 200
    data = resp.json()
    assert "planned" in data
    assert "compliance_pct" in data


def test_integration_status(client):
    resp = client.get("/api/plan/integrations/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "intervals_icu" in data


def test_workout_detail(client):
    """Test workout detail endpoint returns steps."""
    from server.database import get_db
    with get_db() as conn:
        row = conn.execute("SELECT id FROM planned_workouts WHERE workout_xml IS NOT NULL LIMIT 1").fetchone()
    if not row:
        pytest.skip("No workouts with XML")
    resp = client.get(f"/api/plan/workouts/{row['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert "steps" in data
    assert len(data["steps"]) > 0
    assert "ftp" in data


def test_workout_download_tcx(client):
    """Test TCX download."""
    from server.database import get_db
    with get_db() as conn:
        row = conn.execute("SELECT id FROM planned_workouts WHERE workout_xml IS NOT NULL LIMIT 1").fetchone()
    if not row:
        pytest.skip("No workouts with XML")
    resp = client.get(f"/api/plan/workouts/{row['id']}/download?fmt=tcx")
    assert resp.status_code == 200
    assert "TrainingCenterDatabase" in resp.text
