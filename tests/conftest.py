"""Shared test fixtures."""

import os
import tempfile
import pytest
from server.database import init_db, get_db


@pytest.fixture
def tmp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    init_db(db_path)
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def db_conn(tmp_db):
    """Provide a database connection for testing."""
    with get_db(tmp_db) as conn:
        yield conn
