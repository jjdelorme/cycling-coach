"""Integration test for ``scripts/backfill_ride_start_geo.py``.

Seeds three rides directly into the integration test DB:
  1. ICU ride with ``start_lat IS NULL`` whose mocked stream contains a
     valid flat-array ``latlng`` — must be backfilled.
  2. ICU ride with ``start_lat IS NULL`` whose mocked stream is empty (no
     GPS, e.g. an indoor ride) — must remain NULL.
  3. ICU ride with ``start_lat`` already populated — must be untouched
     (and must not even appear in the candidate query).

The intervals.icu HTTP layer is monkeypatched so no network call is made;
the stream payloads are dispatched by the synthetic ICU id encoded in the
ride filename.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_ride_start_geo.py"
_spec = importlib.util.spec_from_file_location("backfill_ride_start_geo", _SCRIPT_PATH)
backfill_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("backfill_ride_start_geo", backfill_module)
_spec.loader.exec_module(backfill_module)


_FIXTURE_FILENAMES = ("icu_geotest_a", "icu_geotest_b", "icu_geotest_c")


def _install_geo_fixtures(db_conn):
    """Idempotently insert the three fixture rides used by this test."""
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
    # Ride A: NULL start_lat, ICU streams will return GPS — should be filled.
    db_conn.execute(
        "INSERT INTO rides (filename, start_time, sport, duration_s,"
        " distance_m, tss, total_ascent) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("icu_geotest_a", "2099-07-01 09:00:00+00", "Ride", 3600, 30000, 50, 100),
    )
    # Ride B: NULL start_lat, ICU streams will be empty — should stay NULL.
    db_conn.execute(
        "INSERT INTO rides (filename, start_time, sport, duration_s,"
        " distance_m, tss, total_ascent) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("icu_geotest_b", "2099-07-02 09:00:00+00", "Ride", 3600, 30000, 50, 100),
    )
    # Ride C: already populated — script's WHERE clause should skip it.
    db_conn.execute(
        "INSERT INTO rides (filename, start_time, sport, duration_s,"
        " distance_m, tss, total_ascent, start_lat, start_lon)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("icu_geotest_c", "2099-07-03 09:00:00+00", "Ride", 3600, 30000, 50, 100, 35.69, -105.94),
    )
    db_conn.commit()


def _stream_dispatch(icu_id: str):
    """Return the synthetic stream payload keyed off the ICU id."""
    if icu_id == "geotest_a":
        return {
            "time": [0, 1, 2],
            "latlng": [42.29, -71.35, 42.30, -71.36, 42.31, -71.37],
        }
    if icu_id == "geotest_b":
        # Indoor ride: streams exist but contain no GPS.
        return {"time": [0, 1, 2], "watts": [200, 210, 220]}
    return None


@pytest.fixture
def fixtures_installed(db_conn):
    _install_geo_fixtures(db_conn)
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


def test_backfill_updates_only_null_icu_rides_with_gps(monkeypatch, fixtures_installed, db_conn):
    _patch_streams(monkeypatch)
    counts = backfill_module.run_backfill(dry_run=False, sleep_seconds=0.0)

    # The shared test seed contains additional NULL-start_lat ICU rides for
    # which our dispatcher returns None — those count as ``no_streams`` and
    # are harmless. We assert only the things this test owns: ride A was
    # backfilled, ride B stayed NULL, ride C was untouched, and at least
    # one ``backfilled`` and one ``no_gps_in_streams`` were recorded.
    assert counts["backfilled"] >= 1
    assert counts["no_gps_in_streams"] >= 1
    assert counts["errors"] == 0

    rows = _row_state(db_conn)
    assert rows["icu_geotest_a"]["start_lat"] == pytest.approx(42.29)
    assert rows["icu_geotest_a"]["start_lon"] == pytest.approx(-71.35)
    assert rows["icu_geotest_b"]["start_lat"] is None
    # Ride C must be untouched.
    assert rows["icu_geotest_c"]["start_lat"] == pytest.approx(35.69)
    assert rows["icu_geotest_c"]["start_lon"] == pytest.approx(-105.94)


def test_backfill_is_idempotent(monkeypatch, fixtures_installed, db_conn):
    _patch_streams(monkeypatch)
    backfill_module.run_backfill(dry_run=False, sleep_seconds=0.0)
    rows_after_first = _row_state(db_conn)

    # Second run: ride A no longer matches the WHERE clause, so it cannot
    # be touched again.
    counts = backfill_module.run_backfill(dry_run=False, sleep_seconds=0.0)
    rows_after_second = _row_state(db_conn)

    assert rows_after_first == rows_after_second
    # Ride A is no longer a candidate, so the second run cannot count it
    # in either ``backfilled`` or ``no_gps_in_streams``.
    assert rows_after_second["icu_geotest_a"]["start_lat"] == pytest.approx(42.29)
    # Idempotency only requires that no rows changed; the seed-rides may
    # still appear in ``total``/``no_streams``, which is fine.
    assert counts["errors"] == 0


def test_dry_run_does_not_write(monkeypatch, fixtures_installed, db_conn):
    _patch_streams(monkeypatch)
    counts = backfill_module.run_backfill(dry_run=True, sleep_seconds=0.0)

    assert counts["backfilled"] >= 1
    assert counts["no_gps_in_streams"] >= 1

    # The DB must be untouched.
    row = dict(
        db_conn.execute(
            "SELECT start_lat FROM rides WHERE filename = ?",
            ("icu_geotest_a",),
        ).fetchone()
    )
    assert row["start_lat"] is None
