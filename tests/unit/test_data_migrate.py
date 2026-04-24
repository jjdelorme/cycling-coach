"""Unit tests for ``server.data_migrate`` runner contract.

These cover filename ordering, skip-already-applied, error-surfacing on a
broken script, and the missing-``run`` function guard. They use an in-memory
fake connection so no database is required.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from server import data_migrate


# ---------------------------------------------------------------------------
# Fake connection / cursor — minimal psycopg2 shape
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, fake_conn):
        self._fake = fake_conn
        self._rows: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self._fake.calls.append((sql.strip(), params))
        s = " ".join(sql.split()).lower()
        if s.startswith("create table if not exists data_migrations"):
            self._rows = []
        elif s.startswith("select filename from data_migrations"):
            self._rows = [(name,) for name in sorted(self._fake.applied)]
        elif s.startswith("insert into data_migrations"):
            filename = params[0]
            self._fake.applied.add(filename)
            self._fake.inserts.append(params)
            self._rows = []
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, applied=None):
        self.applied = set(applied or [])
        self.calls: list[Any] = []
        self.inserts: list[Any] = []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_migration(dirpath: Path, name: str, body: str) -> Path:
    path = dirpath / name
    path.write_text(textwrap.dedent(body))
    return path


def _ok_migration_src(marker: str) -> str:
    return f"""
        RAN = []

        def run(conn):
            RAN.append({marker!r})
            return {{"marker": {marker!r}}}
    """


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_pending_returns_zero(tmp_path):
    conn = _FakeConn()
    count = data_migrate.run_data_migrations(conn, migrations_dir=tmp_path)
    assert count == 0


def test_applies_pending_in_filename_order(tmp_path):
    _write_migration(tmp_path, "0002_second.py", _ok_migration_src("second"))
    _write_migration(tmp_path, "0001_first.py", _ok_migration_src("first"))

    conn = _FakeConn()
    count = data_migrate.run_data_migrations(conn, migrations_dir=tmp_path)

    assert count == 2
    names_inserted = [params[0] for params in conn.inserts]
    assert names_inserted == ["0001_first.py", "0002_second.py"]


def test_skips_already_applied(tmp_path):
    _write_migration(tmp_path, "0001_first.py", _ok_migration_src("first"))
    _write_migration(tmp_path, "0002_second.py", _ok_migration_src("second"))

    conn = _FakeConn(applied={"0001_first.py"})
    count = data_migrate.run_data_migrations(conn, migrations_dir=tmp_path)

    assert count == 1
    names_inserted = [params[0] for params in conn.inserts]
    assert names_inserted == ["0002_second.py"]


def test_ignores_dunder_files(tmp_path):
    _write_migration(tmp_path, "__init__.py", "")
    _write_migration(tmp_path, "0001_real.py", _ok_migration_src("real"))

    conn = _FakeConn()
    count = data_migrate.run_data_migrations(conn, migrations_dir=tmp_path)

    assert count == 1
    assert conn.inserts[0][0] == "0001_real.py"


def test_missing_run_function_raises(tmp_path):
    _write_migration(tmp_path, "0001_no_run.py", "X = 1\n")

    conn = _FakeConn()
    with pytest.raises(RuntimeError, match="does not export a `run"):
        data_migrate.run_data_migrations(conn, migrations_dir=tmp_path)
    assert conn.inserts == []


def test_run_failure_propagates_and_does_not_record(tmp_path):
    _write_migration(
        tmp_path,
        "0001_boom.py",
        """
            def run(conn):
                raise RuntimeError("boom")
        """,
    )

    conn = _FakeConn()
    with pytest.raises(RuntimeError, match="boom"):
        data_migrate.run_data_migrations(conn, migrations_dir=tmp_path)
    assert conn.inserts == []


def test_records_checksum_and_result_dict(tmp_path):
    _write_migration(tmp_path, "0001_first.py", _ok_migration_src("first"))

    conn = _FakeConn()
    data_migrate.run_data_migrations(conn, migrations_dir=tmp_path)

    assert len(conn.inserts) == 1
    filename, checksum, result_wrapped = conn.inserts[0]
    assert filename == "0001_first.py"
    assert isinstance(checksum, str) and len(checksum) == 16
    # psycopg2.extras.Json wraps the dict for adaptation; unwrap to compare.
    assert result_wrapped.adapted == {"marker": "first"}


def test_none_result_is_stored_as_null(tmp_path):
    _write_migration(
        tmp_path,
        "0001_void.py",
        """
            def run(conn):
                return None
        """,
    )

    conn = _FakeConn()
    data_migrate.run_data_migrations(conn, migrations_dir=tmp_path)

    assert len(conn.inserts) == 1
    _filename, _checksum, result_param = conn.inserts[0]
    assert result_param is None
