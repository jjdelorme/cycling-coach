"""Integration test fixtures — requires test database container.

Run integration tests via: ./scripts/run_integration_tests.sh
This starts a dedicated Postgres container on port 5433 and sets
CYCLING_COACH_DATABASE_URL automatically.
"""

import gzip
import json
import os
from pathlib import Path

import pytest
from server.database import init_db, get_db


SEED_FILE = Path(__file__).parent / "seed" / "seed_data.json.gz"

# Table insertion order (respects foreign keys)
_TABLE_ORDER = [
    "rides",
    "ride_records",
    "ride_laps",
    "power_bests",
    "daily_metrics",
    "periodization_phases",
    "planned_workouts",
    "athlete_settings",
    "coach_settings",
    "workout_templates",
]


def pytest_collection_modifyitems(items):
    """Auto-mark all tests in this directory as integration tests."""
    for item in items:
        item.add_marker(pytest.mark.integration)


def _load_seed_data(conn):
    """Load seed data from compressed JSON into the test database."""
    with gzip.open(SEED_FILE, "rt") as f:
        data = json.load(f)

    for table in _TABLE_ORDER:
        rows = data.get(table, [])
        if not rows:
            continue
        cols = list(rows[0].keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        for row in rows:
            conn.execute(sql, tuple(row.get(c) for c in cols))
    conn.commit()

    # Reset sequences so new inserts don't collide with seed IDs
    for table in ["rides", "ride_records", "ride_laps", "power_bests",
                   "periodization_phases", "planned_workouts", "athlete_settings",
                   "workout_templates"]:
        conn.execute(f"""
            SELECT setval(pg_get_serial_sequence('{table}', 'id'),
                          COALESCE((SELECT MAX(id) FROM {table}), 1))
        """)
    conn.commit()


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Create schema and load seed data once per session."""
    init_db()
    with get_db() as conn:
        # Only seed if database is empty
        row = conn.execute("SELECT COUNT(*) as cnt FROM rides").fetchone()
        if row["cnt"] == 0:
            _load_seed_data(conn)


@pytest.fixture
def db_conn():
    """Provide a database connection for integration testing."""
    with get_db() as conn:
        yield conn


@pytest.fixture
def client():
    """Provide a TestClient for API integration tests."""
    from fastapi.testclient import TestClient
    from server.main import app
    yield TestClient(app)
