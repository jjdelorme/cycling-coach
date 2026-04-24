"""Integration tests for ``server.data_migrate`` against a real Postgres.

Drives the runner with synthetic migrations written to a tmp directory and
asserts the ``data_migrations`` tracking table records each one exactly once.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import psycopg2
import pytest

from server.data_migrate import run_data_migrations
from server.database import DATABASE_URL


@pytest.fixture
def raw_conn():
    """A bare psycopg2 connection — the runner uses raw psycopg2, not the wrapper.

    The shared test DB persists between runs (per-session tmpfs), so we sweep
    any leftover ``ittest_*`` rows from a previous test invocation before each
    test. The production tracking semantics are unaffected.
    """
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS data_migrations (
                    id SERIAL PRIMARY KEY,
                    filename TEXT NOT NULL UNIQUE,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    checksum TEXT,
                    result JSONB
                )
            """)
            cur.execute("DELETE FROM data_migrations WHERE filename LIKE 'ittest_%'")
        conn.commit()
        yield conn
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM data_migrations WHERE filename LIKE 'ittest_%'")
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()


def _write(dirpath: Path, name: str, body: str) -> Path:
    path = dirpath / name
    path.write_text(textwrap.dedent(body))
    return path


def _applied_filenames(conn, prefix: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT filename FROM data_migrations WHERE filename LIKE %s ORDER BY filename",
            (f"{prefix}%",),
        )
        return [r[0] for r in cur.fetchall()]


def test_runner_applies_and_records_in_order(tmp_path, raw_conn):
    prefix = "ittest_a_"
    _write(tmp_path, f"{prefix}0002.py", """
        def run(conn):
            return {"step": 2}
    """)
    _write(tmp_path, f"{prefix}0001.py", """
        def run(conn):
            return {"step": 1}
    """)

    count = run_data_migrations(raw_conn, migrations_dir=tmp_path)
    assert count == 2

    rows = _applied_filenames(raw_conn, prefix)
    assert rows == [f"{prefix}0001.py", f"{prefix}0002.py"]


def test_rerun_is_a_noop(tmp_path, raw_conn):
    prefix = "ittest_b_"
    _write(tmp_path, f"{prefix}0001.py", """
        def run(conn):
            return {"ok": True}
    """)

    first = run_data_migrations(raw_conn, migrations_dir=tmp_path)
    second = run_data_migrations(raw_conn, migrations_dir=tmp_path)

    assert first == 1
    assert second == 0
    assert _applied_filenames(raw_conn, prefix) == [f"{prefix}0001.py"]


def test_result_dict_persisted_as_jsonb(tmp_path, raw_conn):
    prefix = "ittest_c_"
    _write(tmp_path, f"{prefix}0001.py", """
        def run(conn):
            return {"backfilled": 42, "errors": 0}
    """)

    run_data_migrations(raw_conn, migrations_dir=tmp_path)

    with raw_conn.cursor() as cur:
        cur.execute(
            "SELECT result FROM data_migrations WHERE filename = %s",
            (f"{prefix}0001.py",),
        )
        result = cur.fetchone()[0]
    assert result == {"backfilled": 42, "errors": 0}


def test_failed_migration_is_not_recorded(tmp_path, raw_conn):
    prefix = "ittest_d_"
    _write(tmp_path, f"{prefix}0001.py", """
        def run(conn):
            raise RuntimeError("intentional fail")
    """)

    with pytest.raises(RuntimeError, match="intentional fail"):
        run_data_migrations(raw_conn, migrations_dir=tmp_path)

    raw_conn.rollback()
    assert _applied_filenames(raw_conn, prefix) == []
