"""Unit tests for ``server.routers.rides._haversine_km``.

The helper drives the exact-distance post-filter on the radius search.
We pin a few sentinel city-pair distances rather than re-implementing the
formula in the test, plus the obvious degenerate cases (zero and
antipodal).
"""

from __future__ import annotations

import pytest

from server.routers.rides import _bounding_box, _haversine_km


# Reference distances are sourced from public great-circle calculators
# and are accurate to within ~0.1 km. We allow 1% tolerance because the
# spherical-Earth model differs slightly from WGS84.


def test_zero_distance_for_identical_points():
    assert _haversine_km(35.69, -105.94, 35.69, -105.94) == pytest.approx(0.0, abs=1e-9)


def test_santa_fe_to_albuquerque_about_93_km():
    """Santa Fe NM to Albuquerque NM is ~93 km great-circle (driving is shorter)."""
    d = _haversine_km(35.6870, -105.9378, 35.0844, -106.6504)
    assert d == pytest.approx(93.0, rel=0.02)


def test_boston_to_new_york_about_306_km():
    d = _haversine_km(42.3601, -71.0589, 40.7128, -74.0060)
    assert d == pytest.approx(306.0, rel=0.02)


def test_antipodal_points_about_half_circumference():
    # The Earth's mean circumference is ~40030 km; half is ~20015 km.
    d = _haversine_km(0.0, 0.0, 0.0, 180.0)
    assert d == pytest.approx(20015.0, rel=0.005)


def test_symmetry_a_to_b_equals_b_to_a():
    a = _haversine_km(35.0, -105.0, 40.0, -110.0)
    b = _haversine_km(40.0, -110.0, 35.0, -105.0)
    assert a == pytest.approx(b)


# ---------------------------------------------------------------------------
# Bounding-box helper
# ---------------------------------------------------------------------------


def test_bounding_box_latitude_span_is_radius_over_111_32():
    min_lat, max_lat, _, _ = _bounding_box(35.69, -105.94, radius_km=25)
    span = max_lat - min_lat
    # 25 km / 111.32 km/deg ≈ 0.2246 (full span ≈ 0.4492°).
    assert span == pytest.approx(2 * 25 / 111.32, rel=1e-6)


def test_bounding_box_longitude_span_widens_at_low_latitude():
    # Near the equator, 1° lon ≈ 111.32 km, so the longitude span ≈ latitude span.
    _, _, min_lon, max_lon = _bounding_box(0.0, 0.0, radius_km=25)
    assert (max_lon - min_lon) == pytest.approx(2 * 25 / 111.32, rel=1e-3)


def test_bounding_box_longitude_span_collapses_at_high_latitude():
    # Near the pole, 1° lon shrinks dramatically.
    _, _, min_lon, max_lon = _bounding_box(80.0, 0.0, radius_km=25)
    # cos(80°) ≈ 0.1736, so lon span ≈ (25 / 111.32) / 0.1736 ≈ 1.293°.
    assert (max_lon - min_lon) == pytest.approx(2 * 25 / 111.32 / 0.17365, rel=1e-3)


def test_bounding_box_clamps_at_the_poles():
    # cos(90°) → 0; the helper clamps the longitude delta at ±180°.
    _, _, min_lon, max_lon = _bounding_box(90.0, 0.0, radius_km=25)
    assert min_lon >= -180.0001
    assert max_lon <= 180.0001
