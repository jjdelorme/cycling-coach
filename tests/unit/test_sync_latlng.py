"""Unit tests for the intervals.icu ``latlng`` stream parser.

These tests pin the behaviour of ``server.services.sync._normalize_latlng``
plus the two consumers that depend on it (``_store_streams`` and
``_backfill_start_location``). The parser must accept both the nested-pair
shape ``[[lat, lon], ...]`` and the flat alternating-floats shape
``[lat, lon, lat, lon, ...]`` because intervals.icu has been observed to
return either, and the legacy code only handled nested pairs (silently
dropping every GPS point on flat-format payloads).

No database is touched — ``_store_streams`` and ``_backfill_start_location``
are exercised against a fake connection that records the SQL it would run.
"""

from __future__ import annotations

from server.services.sync import (
    _backfill_start_location,
    _normalize_latlng,
    _store_streams,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeConn:
    """Minimal stand-in for a DB connection used by the consumers under test.

    Records each ``execute``/``executemany`` call so tests can assert exactly
    which rows would have been written, without actually opening a database.
    """

    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple]] = []
        self.executemany_calls: list[tuple[str, list]] = []

    def execute(self, sql, params=()):
        self.execute_calls.append((sql, params))
        return self

    def executemany(self, sql, rows):
        self.executemany_calls.append((sql, list(rows)))
        return self


# ---------------------------------------------------------------------------
# _normalize_latlng — pure helper
# ---------------------------------------------------------------------------


def test_normalize_latlng_empty_returns_empty_list():
    assert _normalize_latlng([]) == []


def test_normalize_latlng_none_returns_empty_list():
    assert _normalize_latlng(None) == []


def test_normalize_latlng_nested_pairs_passthrough():
    raw = [[42.29, -71.35], [42.30, -71.36]]
    assert _normalize_latlng(raw) == [(42.29, -71.35), (42.30, -71.36)]


def test_normalize_latlng_nested_tuples_passthrough():
    raw = [(42.29, -71.35), (42.30, -71.36)]
    assert _normalize_latlng(raw) == [(42.29, -71.35), (42.30, -71.36)]


def test_normalize_latlng_flat_floats_pairs_them_up():
    raw = [42.29, -71.35, 42.30, -71.36]
    assert _normalize_latlng(raw) == [(42.29, -71.35), (42.30, -71.36)]


def test_normalize_latlng_flat_odd_length_truncates_trailing_orphan():
    # Trailing lat with no lon is dropped, never paired with garbage.
    raw = [42.29, -71.35, 42.30]
    assert _normalize_latlng(raw) == [(42.29, -71.35)]


def test_normalize_latlng_skips_nested_entries_shorter_than_two():
    raw = [[42.29, -71.35], [42.30], [42.31, -71.37]]
    assert _normalize_latlng(raw) == [(42.29, -71.35), (42.31, -71.37)]


# ---------------------------------------------------------------------------
# _store_streams — must populate lat/lon for the flat format
# ---------------------------------------------------------------------------


def test_store_streams_writes_lat_lon_from_flat_latlng():
    conn = _FakeConn()
    streams = {
        "time": [0, 1, 2],
        "latlng": [42.29, -71.35, 42.30, -71.36, 42.31, -71.37],
    }
    _store_streams(ride_id=99, streams=streams, conn=conn)

    assert len(conn.executemany_calls) == 1
    sql, rows = conn.executemany_calls[0]
    assert "INSERT INTO ride_records" in sql
    assert len(rows) == 3
    # Row layout: (ride_id, ts, power, hr, cad, speed, alt, dist, lat, lon, temp)
    assert rows[0][0] == 99
    assert rows[0][8] == 42.29 and rows[0][9] == -71.35
    assert rows[1][8] == 42.30 and rows[1][9] == -71.36
    assert rows[2][8] == 42.31 and rows[2][9] == -71.37


def test_store_streams_writes_lat_lon_from_nested_latlng():
    conn = _FakeConn()
    streams = {
        "time": [0, 1],
        "latlng": [[42.29, -71.35], [42.30, -71.36]],
    }
    _store_streams(ride_id=7, streams=streams, conn=conn)

    sql, rows = conn.executemany_calls[0]
    assert rows[0][8] == 42.29 and rows[0][9] == -71.35
    assert rows[1][8] == 42.30 and rows[1][9] == -71.36


def test_store_streams_no_latlng_writes_none_for_each_row():
    """Indoor rides have no GPS — must not crash and must write NULLs."""
    conn = _FakeConn()
    streams = {"time": [0, 1], "watts": [200, 210]}
    _store_streams(ride_id=1, streams=streams, conn=conn)

    sql, rows = conn.executemany_calls[0]
    assert len(rows) == 2
    assert rows[0][8] is None and rows[0][9] is None
    assert rows[1][8] is None and rows[1][9] is None


# ---------------------------------------------------------------------------
# _backfill_start_location — must use the first valid (non-(0,0)) point
# ---------------------------------------------------------------------------


def test_backfill_start_location_picks_first_point_from_flat_latlng():
    conn = _FakeConn()
    streams = {
        "time": [0, 1],
        "latlng": [42.29, -71.35, 42.30, -71.36],
    }
    _backfill_start_location(ride_id=42, streams=streams, conn=conn)

    assert len(conn.execute_calls) == 1
    sql, params = conn.execute_calls[0]
    assert "UPDATE rides" in sql and "start_lat IS NULL" in sql
    assert params == (42.29, -71.35, 42)


def test_backfill_start_location_picks_first_point_from_nested_latlng():
    conn = _FakeConn()
    streams = {"latlng": [[42.29, -71.35], [42.30, -71.36]]}
    _backfill_start_location(ride_id=42, streams=streams, conn=conn)

    sql, params = conn.execute_calls[0]
    assert params == (42.29, -71.35, 42)


def test_backfill_start_location_skips_zero_zero_fix():
    """A (0, 0) GPS reading is a transient before-lock value, not a real fix."""
    conn = _FakeConn()
    streams = {"latlng": [0.0, 0.0, 42.29, -71.35]}
    _backfill_start_location(ride_id=5, streams=streams, conn=conn)

    sql, params = conn.execute_calls[0]
    assert params == (42.29, -71.35, 5)


def test_backfill_start_location_no_op_when_latlng_missing():
    conn = _FakeConn()
    streams = {"time": [0, 1], "watts": [200, 210]}
    _backfill_start_location(ride_id=5, streams=streams, conn=conn)

    assert conn.execute_calls == []


def test_backfill_start_location_no_op_when_only_zero_points():
    conn = _FakeConn()
    streams = {"latlng": [0.0, 0.0, 0.0, 0.0]}
    _backfill_start_location(ride_id=5, streams=streams, conn=conn)

    assert conn.execute_calls == []
