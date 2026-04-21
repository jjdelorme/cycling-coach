"""Unit tests for the pure rides query-builder helper.

These tests lock the SQL shape and parameter order produced by
``server.routers.rides._build_rides_query`` without touching a database.
They guard against accidental string-formatting injection (the helper must
always use ``?`` placeholders, never inline values) and pin the multi-word
search semantics described in plans/feat-rides-search.md.
"""

from __future__ import annotations

import pytest

from server.routers.rides import _build_rides_query


def _params_for(**kwargs):
    """Build with sensible defaults so each test only states what it changes."""
    base = dict(
        tz_name="UTC",
        start_date=None,
        end_date=None,
        sport=None,
        q=None,
        limit=500,
        near=None,
        radius_km=None,
    )
    base.update(kwargs)
    return _build_rides_query(**base)


# ---------------------------------------------------------------------------
# Baseline (no filters) — locks the legacy SQL shape so the refactor is safe
# ---------------------------------------------------------------------------


def test_no_filters_produces_minimal_query():
    sql, params = _params_for()
    assert "WHERE start_time IS NOT NULL" in sql
    assert "ORDER BY start_time DESC LIMIT ?" in sql
    # No q-clause, no sport-clause, no date-clause.
    assert "LIKE" not in sql
    assert " sport = " not in sql
    # Two binds: the tz_name (for the date column projection) and the limit.
    assert params == ["UTC", 500]


def test_uses_question_mark_placeholders_not_percent_s():
    """Project psycopg2 wrapper requires ``?``; ``%s`` would not be adapted."""
    sql, _ = _params_for(q="threshold", start_date="2026-01-01", end_date="2026-12-31", sport="Ride")
    assert "%s" not in sql
    assert sql.count("?") >= 4


def test_date_range_filter_appends_clauses_in_order():
    sql, params = _params_for(start_date="2026-01-01", end_date="2026-03-01")
    assert "(start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE >= ?::DATE" in sql
    assert "(start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE <= ?::DATE" in sql
    # tz, tz, start, tz, end, limit
    assert params == ["UTC", "UTC", "2026-01-01", "UTC", "2026-03-01", 500]


def test_sport_filter_matches_sport_or_sub_sport():
    sql, params = _params_for(sport="Ride")
    assert "(sport = ? OR sub_sport = ?)" in sql
    assert params == ["UTC", "Ride", "Ride", 500]


# ---------------------------------------------------------------------------
# Free-text search — the new behaviour
# ---------------------------------------------------------------------------


def test_q_none_adds_no_search_clause():
    sql, params = _params_for(q=None)
    assert "LIKE" not in sql
    assert params == ["UTC", 500]


def test_q_whitespace_only_treated_as_none():
    sql, params = _params_for(q="   \t   ")
    assert "LIKE" not in sql
    assert params == ["UTC", 500]


def test_q_single_word_adds_one_or_group_across_three_columns():
    sql, params = _params_for(q="threshold")
    expected_fragment = (
        "AND (LOWER(title) LIKE ? OR LOWER(post_ride_comments) LIKE ?"
        " OR LOWER(coach_comments) LIKE ?)"
    )
    assert expected_fragment in sql
    # tz_name + 3 LIKE binds + limit
    assert params == ["UTC", "%threshold%", "%threshold%", "%threshold%", 500]


def test_q_lowercases_input_for_case_insensitive_match():
    sql, params = _params_for(q="THRESHOLD")
    assert "%threshold%" in params
    assert "%THRESHOLD%" not in params
    # SQL still uses LOWER() on the columns, not on the bind.
    assert "LOWER(title)" in sql


def test_q_two_words_anded_each_word_one_or_group():
    sql, params = _params_for(q="hard climb")
    # Each word becomes its own parenthesised group; groups ANDed together.
    expected_fragment = (
        "AND (LOWER(title) LIKE ? OR LOWER(post_ride_comments) LIKE ?"
        " OR LOWER(coach_comments) LIKE ?)"
        " AND (LOWER(title) LIKE ? OR LOWER(post_ride_comments) LIKE ?"
        " OR LOWER(coach_comments) LIKE ?)"
    )
    assert expected_fragment in sql
    # tz_name + 3 binds for "hard" + 3 binds for "climb" + limit
    assert params == [
        "UTC",
        "%hard%", "%hard%", "%hard%",
        "%climb%", "%climb%", "%climb%",
        500,
    ]


def test_q_does_not_substring_match_phrase():
    """Multi-word semantics must NOT collapse to LIKE '%hard climb%'."""
    sql, params = _params_for(q="hard climb")
    assert "%hard climb%" not in params
    assert "%hard%" in params
    assert "%climb%" in params


def test_q_collapses_extra_whitespace():
    """Whitespace splitting handles multi-spaces and tabs cleanly."""
    sql_a, params_a = _params_for(q="hard climb")
    sql_b, params_b = _params_for(q="  hard\t\tclimb  ")
    assert sql_a == sql_b
    assert params_a == params_b


def test_q_composes_with_date_range():
    sql, params = _params_for(q="climb", start_date="2026-01-01", end_date="2026-12-31")
    # Date clauses precede the q-clause in the WHERE; LIMIT is last.
    pos_start = sql.find(">= ?::DATE")
    pos_end = sql.find("<= ?::DATE")
    pos_q = sql.find("LOWER(title)")
    pos_limit = sql.find("LIMIT ?")
    assert 0 < pos_start < pos_end < pos_q < pos_limit
    # Param order: tz, tz, start_date, tz, end_date, like x3, limit
    assert params == [
        "UTC", "UTC", "2026-01-01", "UTC", "2026-12-31",
        "%climb%", "%climb%", "%climb%",
        500,
    ]


def test_q_composes_with_sport_filter():
    sql, params = _params_for(q="climb", sport="Ride")
    assert "(sport = ? OR sub_sport = ?)" in sql
    assert "LOWER(title)" in sql
    assert params == [
        "UTC",
        "Ride", "Ride",
        "%climb%", "%climb%", "%climb%",
        500,
    ]


def test_limit_appears_once_at_end():
    sql, params = _params_for(q="threshold", limit=42)
    assert sql.rstrip().endswith("LIMIT ?")
    assert params[-1] == 42


# ---------------------------------------------------------------------------
# Location radius — bounding-box prefilter SQL
# ---------------------------------------------------------------------------


def test_near_without_radius_adds_no_clause():
    sql, params = _params_for(near=(35.69, -105.94), radius_km=None)
    assert "BETWEEN" not in sql
    assert params == ["UTC", 500]


def test_radius_without_near_adds_no_clause():
    """Caller-side validation enforces the contract; the helper itself is permissive."""
    sql, params = _params_for(near=None, radius_km=25)
    assert "BETWEEN" not in sql


def test_near_plus_radius_adds_bounding_box_and_not_null_clauses():
    sql, params = _params_for(near=(35.69, -105.94), radius_km=25)
    assert "start_lat IS NOT NULL AND start_lon IS NOT NULL" in sql
    assert "start_lat BETWEEN ? AND ?" in sql
    assert "start_lon BETWEEN ? AND ?" in sql
    # tz_name + 4 bounding-box binds + limit
    assert len(params) == 6
    assert params[0] == "UTC"
    assert params[-1] == 500


def test_bounding_box_params_match_documented_formula():
    sql, params = _params_for(near=(0.0, 0.0), radius_km=25)
    # Near the equator the latitude and longitude spans both equal radius/111.32.
    delta = 25 / 111.32
    _, min_lat, max_lat, min_lon, max_lon, _ = params
    assert min_lat == pytest.approx(-delta, rel=1e-6)
    assert max_lat == pytest.approx(delta, rel=1e-6)
    assert min_lon == pytest.approx(-delta, rel=1e-3)
    assert max_lon == pytest.approx(delta, rel=1e-3)


def test_radius_composes_with_q_and_dates():
    sql, params = _params_for(
        q="climb",
        start_date="2026-01-01",
        end_date="2026-12-31",
        near=(35.69, -105.94),
        radius_km=25,
    )
    pos_dates = sql.find(">= ?::DATE")
    pos_q = sql.find("LOWER(title)")
    pos_geo = sql.find("BETWEEN")
    pos_limit = sql.find("LIMIT ?")
    assert 0 < pos_dates < pos_q < pos_geo < pos_limit
    # Param order: tz, tz, start, tz, end, like x3, min_lat, max_lat, min_lon, max_lon, limit
    assert len(params) == 5 + 3 + 4 + 1
    assert params[-1] == 500
