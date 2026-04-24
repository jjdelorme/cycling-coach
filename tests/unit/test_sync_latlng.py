"""Unit tests for the intervals.icu ``latlng`` stream parser.

These tests pin the behaviour of ``server.services.sync._normalize_latlng``
plus the two consumers that depend on it (``_store_streams`` and
``_backfill_start_location``). The parser must accept all three observed
intervals.icu formats:

  * Nested pairs:     ``[[lat, lon], [lat, lon], ...]``
  * Flat alternating: ``[lat, lon, lat, lon, ...]``
  * Flat concatenated:``[lat1, lat2, ..., latN, lon1, lon2, ..., lonN]``

The concatenated format is the root cause of the "Syria bug" — consecutive
latitude values being stored as (lat, lat) instead of (lat, lon), which
reverse-geocodes to the wrong country.

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


def test_normalize_latlng_concatenated_format():
    # Reproduces the "Syria bug": ICU returns all lats then all lons.
    # Fruita, CO: lat≈39.31, lon≈-108.73
    raw = [39.310474, 39.31047, 39.309, 39.308, -108.730, -108.731, -108.731, -108.732]
    result = _normalize_latlng(raw)
    assert len(result) == 4
    assert result[0] == (39.310474, -108.730)
    assert result[1] == (39.31047, -108.731)


def test_normalize_latlng_concatenated_not_triggered_for_zero_prefix():
    # Flat alternating with (0,0) GPS-no-lock at start must NOT be detected
    # as concatenated — the 0.0 sentinel guards against this.
    raw = [0.0, 0.0, 42.29, -71.35]
    result = _normalize_latlng(raw)
    assert result == [(0.0, 0.0), (42.29, -71.35)]


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


def test_backfill_start_location_picks_first_point_from_concatenated_latlng():
    # Santa Fe, NM: lat≈35.69, lon≈-105.94.
    # Without the concatenated-format fix this would store (35.69, 35.69) which
    # reverse-geocodes to Syria.
    conn = _FakeConn()
    streams = {
        "latlng": [35.690, 35.691, 35.692, 35.693, -105.940, -105.941, -105.942, -105.943],
    }
    _backfill_start_location(ride_id=99, streams=streams, conn=conn)

    assert len(conn.execute_calls) == 1
    sql, params = conn.execute_calls[0]
    assert "UPDATE rides" in sql and "start_lat IS NULL" in sql
    assert params == (35.690, -105.940, 99)


# ---------------------------------------------------------------------------
# Phase 7 — lat-only "Variant B" payload + corruption guard (Campaign 20 D4)
# ---------------------------------------------------------------------------


def test_normalize_latlng_lat_only_variant_returns_empty():
    """Variant B (observed on ride 3238, 2026-04-22): the ICU latlng stream
    is 100% latitudes (no longitudes anywhere). The first/second halves are
    statistically identical latitude clouds.

    The Phase 7 detector must return [] rather than fabricating (lat, lat)
    pairs that the existing alternating-pairs fallback would otherwise emit.
    """
    # 100 elements, all in the latitude range, with sub-degree noise. No
    # longitudes anywhere — both halves are still latitudes.
    raw = []
    for i in range(50):
        raw.extend([39.750 + i * 0.0001, 39.750 + i * 0.0001])
    assert len(raw) == 100

    result = _normalize_latlng(raw)
    assert result == []


def test_normalize_latlng_lat_only_short_payload_passes_through():
    """A short (n<60) lat-only-shaped payload bypasses the new detector and
    falls through to the existing alternating-pairs branch.

    This is intentional: small fixtures used in other tests (and any real
    very-short ride) don't trigger the heuristic, which needs a meaningful
    sample size to be confident. The previous 'lat-only short' behaviour
    (produces (lat, lat) pairs) is preserved verbatim here so other test
    expectations that pre-date Phase 7 keep working."""
    raw = [39.750, 39.751, 39.752, 39.753, 39.754, 39.755]
    result = _normalize_latlng(raw)

    # Old-style alternating-pairs fallback fires — n=6 < 60 so the new
    # detector does not engage.
    assert len(result) == 3
    # And critically each pair has |lat - lon| < 1° (the (lat, lat) shape
    # the new detector exists to suppress at scale). This is a contract test
    # documenting the deliberate carve-out.
    for lat, lon in result:
        assert abs(lat - lon) < 1.0


def test_normalize_latlng_real_us_ride_passes():
    """A 100-element concatenated payload for a real Boulder, CO ride
    must still parse as 50 valid (lat, lon) pairs after Phase 7's
    detector is added — proves we didn't break the happy path."""
    lat_values = [40.000 + i * 0.0001 for i in range(50)]
    lon_values = [-105.300 - i * 0.0001 for i in range(50)]
    raw = lat_values + lon_values
    assert len(raw) == 100

    result = _normalize_latlng(raw)
    assert len(result) == 50
    for lat, lon in result:
        # Real (lat, lon) for the US: |lat - lon| > 100°.
        assert abs(lat - lon) > 100


def test_store_streams_corruption_guard_drops_lat_lat_pairs():
    """When _normalize_latlng yields pairs that nonetheless trip the D4
    corruption signature (>50% have |lat-lon|<1°) AND there are at least
    MIN_GPS_RECORDS_FOR_DETECTION (60) of them, the _store_streams guard
    refuses to write GPS columns for that ride — non-GPS columns still
    get written so power/HR/cadence aren't lost.

    This is belt-and-suspenders: a future parser variant we missed should
    still produce 'no GPS' (UI shows the indoor placeholder) rather than
    rendering a wrong polyline."""
    conn = _FakeConn()
    # 80 nested (lat, lat) pairs — fits the corruption signature and meets
    # the MIN_GPS_RECORDS threshold.
    streams = {
        "time": list(range(80)),
        "watts": [200] * 80,
        "latlng": [[39.75, 39.75]] * 80,
    }

    _store_streams(ride_id=99, streams=streams, conn=conn)

    assert len(conn.executemany_calls) == 1
    _sql, rows = conn.executemany_calls[0]
    assert len(rows) == 80
    # Every row has lat=None AND lon=None — the guard fired.
    for row in rows:
        assert row[8] is None and row[9] is None
    # Power was preserved (column index 2) — guard only nukes GPS.
    assert all(row[2] == 200 for row in rows)
