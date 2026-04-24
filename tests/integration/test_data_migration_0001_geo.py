"""Integration test for ``data_migrations/0001_backfill_ride_start_geo.py``.

Mirrors ``tests/integration/test_backfill_ride_start_geo.py`` but drives the
ported data-migration module instead of the standalone script. Seeds three
rides directly into the integration test DB:
  1. ICU ride with ``start_lat IS NULL`` whose mocked stream contains a
     valid flat-array ``latlng`` — must be backfilled.
  2. ICU ride with ``start_lat IS NULL`` whose mocked stream is empty (no
     GPS, e.g. an indoor ride) — must remain NULL.
  3. ICU ride with ``start_lat`` already populated — must be untouched.

The intervals.icu HTTP layer is monkeypatched; no network call is made.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data_migrations"
    / "0001_backfill_ride_start_geo.py"
)
_spec = importlib.util.spec_from_file_location(
    "_migration_0001_backfill_ride_start_geo", _MIGRATION_PATH
)
migration_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault(_spec.name, migration_module)
_spec.loader.exec_module(migration_module)


_FIXTURE_FILENAMES = ("icu_geomig_a", "icu_geomig_b", "icu_geomig_c")


def _install_fixtures(db_conn):
    db_conn.execute(
        "DELETE FROM ride_records WHERE ride_id IN ("
        " SELECT id FROM rides WHERE filename = ANY(%s)"
        ")",
        (list(_FIXTURE_FILENAMES),),
    )
    db_conn.execute(
        "DELETE FROM rides WHERE filename = ANY(%s)",
        (list(_FIXTURE_FILENAMES),),
    )
    db_conn.execute(
        "INSERT INTO rides (filename, start_time, sport, duration_s,"
        " distance_m, tss, total_ascent) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("icu_geomig_a", "2099-08-01 09:00:00+00", "Ride", 3600, 30000, 50, 100),
    )
    db_conn.execute(
        "INSERT INTO rides (filename, start_time, sport, duration_s,"
        " distance_m, tss, total_ascent) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("icu_geomig_b", "2099-08-02 09:00:00+00", "Ride", 3600, 30000, 50, 100),
    )
    db_conn.execute(
        "INSERT INTO rides (filename, start_time, sport, duration_s,"
        " distance_m, tss, total_ascent, start_lat, start_lon)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("icu_geomig_c", "2099-08-03 09:00:00+00", "Ride", 3600, 30000, 50, 100,
         35.69, -105.94),
    )
    db_conn.commit()


def _stream_dispatch(icu_id: str):
    if icu_id == "geomig_a":
        return {
            "time": [0, 1, 2],
            "latlng": [40.71, -74.00, 40.72, -74.01, 40.73, -74.02],
        }
    if icu_id == "geomig_b":
        return {"time": [0, 1, 2], "watts": [200, 210, 220]}
    return None


@pytest.fixture
def fixtures_installed(db_conn, monkeypatch):
    monkeypatch.delenv("INTERVALS_ICU_DISABLED", raising=False)
    monkeypatch.delenv("INTERVALS_ICU_DISABLE", raising=False)
    _install_fixtures(db_conn)
    yield
    db_conn.execute(
        "DELETE FROM ride_records WHERE ride_id IN ("
        " SELECT id FROM rides WHERE filename = ANY(%s)"
        ")",
        (list(_FIXTURE_FILENAMES),),
    )
    db_conn.execute(
        "DELETE FROM rides WHERE filename = ANY(%s)",
        (list(_FIXTURE_FILENAMES),),
    )
    db_conn.commit()


def _patch_streams(monkeypatch):
    from server.services import sync as sync_module
    monkeypatch.setattr(sync_module, "fetch_activity_streams", _stream_dispatch)


def _row_state(db_conn) -> dict:
    return {
        dict(r)["filename"]: dict(r)
        for r in db_conn.execute(
            "SELECT filename, start_lat, start_lon FROM rides"
            " WHERE filename = ANY(%s)",
            (list(_FIXTURE_FILENAMES),),
        ).fetchall()
    }


def test_migration_backfills_only_null_icu_rides_with_gps(
    monkeypatch, fixtures_installed, db_conn
):
    _patch_streams(monkeypatch)

    counts = migration_module.run(conn=None, sleep_seconds=0.0)

    assert counts["backfilled"] >= 1
    assert counts["no_gps_in_streams"] >= 1
    assert counts["errors"] == 0

    rows = _row_state(db_conn)
    assert rows["icu_geomig_a"]["start_lat"] == pytest.approx(40.71)
    assert rows["icu_geomig_a"]["start_lon"] == pytest.approx(-74.00)
    assert rows["icu_geomig_b"]["start_lat"] is None
    assert rows["icu_geomig_c"]["start_lat"] == pytest.approx(35.69)
    assert rows["icu_geomig_c"]["start_lon"] == pytest.approx(-105.94)


def test_migration_is_idempotent(monkeypatch, fixtures_installed, db_conn):
    _patch_streams(monkeypatch)
    migration_module.run(conn=None, sleep_seconds=0.0)
    rows_after_first = _row_state(db_conn)
    counts = migration_module.run(conn=None, sleep_seconds=0.0)
    rows_after_second = _row_state(db_conn)

    assert rows_after_first == rows_after_second
    assert rows_after_second["icu_geomig_a"]["start_lat"] == pytest.approx(40.71)
    assert counts["errors"] == 0


def test_icu_disabled_env_var_short_circuits(monkeypatch, db_conn):
    monkeypatch.setenv("INTERVALS_ICU_DISABLED", "1")
    result = migration_module.run(conn=None)
    assert result == {"skipped": True, "reason": "icu_disabled"}
