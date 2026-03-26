"""Shared test fixtures."""

import os

# Disable Google auth for tests so endpoints don't require tokens
os.environ["GOOGLE_AUTH_ENABLED"] = "false"

import pytest
from server.database import init_db, get_db


@pytest.fixture
def db_conn():
    """Provide a database connection for testing.

    Requires DATABASE_URL to be set (local Postgres via podman-compose).
    """
    init_db()
    with get_db() as conn:
        yield conn
