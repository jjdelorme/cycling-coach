"""Shared test fixtures."""

import os
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
