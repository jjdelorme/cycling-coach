"""Unit tests for server/services/weight.py — the weight resolver abstraction."""
from unittest.mock import MagicMock


def _make_conn(*query_results):
    """Build a mock connection that returns each item in query_results in sequence."""
    conn = MagicMock()
    results = list(query_results)
    call_count = [0]

    def execute(sql, params=None):
        idx = call_count[0]
        call_count[0] += 1
        cursor = MagicMock()
        cursor.fetchone.return_value = results[idx] if idx < len(results) else None
        return cursor

    conn.execute.side_effect = execute
    return conn


def _row(d: dict):
    """Return a dict-like object that supports __getitem__."""
    return d


# ---------------------------------------------------------------------------
# get_weight_for_date
# ---------------------------------------------------------------------------

class TestGetWeightForDate:
    def test_uses_withings_when_available(self):
        """Priority 1: Withings body_measurements wins when present."""
        from server.services.weight import get_weight_for_date
        # First query (body_measurements) returns data → use it
        conn = _make_conn(
            _row({"weight_kg": 72.5}),  # body_measurements
        )
        result = get_weight_for_date(conn, "2026-04-01")
        assert result == 72.5

    def test_falls_back_to_ride_weight_when_no_withings(self):
        """Priority 2: ride weight used when no Withings measurement."""
        from server.services.weight import get_weight_for_date
        conn = _make_conn(
            None,                        # body_measurements — no data
            _row({"weight": 73.0}),      # rides
        )
        result = get_weight_for_date(conn, "2026-04-01")
        assert result == 73.0

    def test_falls_back_to_athlete_settings_when_no_ride(self):
        """Priority 3: athlete_settings used when no Withings or ride weight."""
        from server.services.weight import get_weight_for_date
        conn = _make_conn(
            None,                           # body_measurements — no data
            None,                           # rides — no data
            _row({"value": "74.0"}),        # athlete_settings
        )
        result = get_weight_for_date(conn, "2026-04-01")
        assert result == 74.0

    def test_returns_default_when_all_sources_empty(self):
        """Priority 4: 75.0 kg default when no data anywhere."""
        from server.services.weight import get_weight_for_date, DEFAULT_WEIGHT_KG
        conn = _make_conn(None, None, None)
        result = get_weight_for_date(conn, "2026-04-01")
        assert result == DEFAULT_WEIGHT_KG

    def test_withings_takes_priority_over_ride_weight(self):
        """Withings value (72.5) wins over a heavier ride weight (80.0)."""
        from server.services.weight import get_weight_for_date
        conn = _make_conn(
            _row({"weight_kg": 72.5}),  # body_measurements
            # ride query is never reached
        )
        result = get_weight_for_date(conn, "2026-04-01")
        assert result == 72.5
        # Only one query was issued (ride query was skipped)
        assert conn.execute.call_count == 1

    def test_skips_zero_ride_weight(self):
        """A ride weight of 0 is treated as missing — falls through to athlete_settings."""
        from server.services.weight import get_weight_for_date
        conn = _make_conn(
            None,                        # body_measurements
            _row({"weight": 0}),         # rides — zero (invalid)
            _row({"value": "74.0"}),     # athlete_settings
        )
        result = get_weight_for_date(conn, "2026-04-01")
        assert result == 74.0

    def test_skips_invalid_athlete_setting(self):
        """An unparseable athlete_settings value falls through to default."""
        from server.services.weight import get_weight_for_date, DEFAULT_WEIGHT_KG
        conn = _make_conn(
            None,               # body_measurements
            None,               # rides
            _row({"value": "not-a-number"}),  # athlete_settings — bad value
        )
        result = get_weight_for_date(conn, "2026-04-01")
        assert result == DEFAULT_WEIGHT_KG


# ---------------------------------------------------------------------------
# get_current_weight
# ---------------------------------------------------------------------------

class TestGetCurrentWeight:
    def test_delegates_to_get_weight_for_date_with_user_today(self):
        """get_current_weight calls get_weight_for_date with user_today()."""
        from unittest.mock import patch
        from server.services.weight import get_current_weight

        conn = _make_conn(_row({"weight_kg": 71.0}))

        with patch("server.services.weight.get_weight_for_date") as mock_fn, \
             patch("server.utils.dates.user_today", return_value="2026-04-14") as mock_today:
            mock_fn.return_value = 71.0
            result = get_current_weight(conn)

        mock_today.assert_called_once()
        mock_fn.assert_called_once_with(conn, "2026-04-14")
        assert result == 71.0
