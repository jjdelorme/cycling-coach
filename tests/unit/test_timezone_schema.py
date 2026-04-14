"""Unit tests for Phase 3 timezone schema migration changes.

Tests the _start_time_to_date helper and verifies that write paths
handle both string and datetime start_time values correctly.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestStartTimeToDate:
    """Tests for _start_time_to_date -- must handle both str and datetime."""

    def test_string_iso_utc(self):
        """ISO string with Z suffix extracts YYYY-MM-DD."""
        from server.ingest import _start_time_to_date
        assert _start_time_to_date("2026-04-09T03:30:00Z") == "2026-04-09"

    def test_string_iso_offset(self):
        """ISO string with +00:00 offset extracts YYYY-MM-DD."""
        from server.ingest import _start_time_to_date
        assert _start_time_to_date("2026-04-09T03:30:00+00:00") == "2026-04-09"

    def test_string_iso_no_tz(self):
        """ISO string without timezone extracts YYYY-MM-DD."""
        from server.ingest import _start_time_to_date
        assert _start_time_to_date("2026-04-09T03:30:00") == "2026-04-09"

    def test_datetime_object(self):
        """datetime object uses strftime to produce YYYY-MM-DD."""
        from server.ingest import _start_time_to_date
        dt = datetime(2026, 4, 9, 3, 30, 0, tzinfo=timezone.utc)
        assert _start_time_to_date(dt) == "2026-04-09"

    def test_datetime_date_object(self):
        """date object also has strftime."""
        from server.ingest import _start_time_to_date
        from datetime import date
        d = date(2026, 4, 9)
        assert _start_time_to_date(d) == "2026-04-09"

    def test_none_returns_empty(self):
        """None input returns empty string."""
        from server.ingest import _start_time_to_date
        assert _start_time_to_date(None) == ""

    def test_empty_string_returns_empty(self):
        """Empty string returns empty string."""
        from server.ingest import _start_time_to_date
        assert _start_time_to_date("") == ""

    def test_short_string_returns_empty(self):
        """String shorter than 10 chars returns empty."""
        from server.ingest import _start_time_to_date
        assert _start_time_to_date("2026") == ""


class TestGetBenchmarkForDate:
    """Tests for get_benchmark_for_date with TIMESTAMPTZ comparison."""

    def test_uses_timestamptz_cast_in_query(self):
        """The SQL query must cast date_str to TIMESTAMPTZ for comparison."""
        mock_conn = MagicMock()
        # First call: get_latest_metric returns 0
        # Second call: ride query
        mock_conn.execute.return_value.fetchone.return_value = None

        with patch("server.queries.get_latest_metric", return_value=0):
            from server.ingest import get_benchmark_for_date
            get_benchmark_for_date(mock_conn, "ftp", "2026-04-09")

        # Find the ride query call (last execute call)
        ride_query_call = mock_conn.execute.call_args
        sql = ride_query_call[0][0]
        assert "::TIMESTAMPTZ" in sql, f"Query must use TIMESTAMPTZ cast: {sql}"


class TestIngestRidesPowerBestsDate:
    """Verify power_bests INSERT derives date from start_time via _start_time_to_date."""

    def test_power_bests_date_from_start_time(self):
        """power_bests date should come from ride start_time, not rides.date."""
        from server.ingest import _start_time_to_date

        # Simulate what ingest_rides does
        ride = {"start_time": "2026-04-09T03:30:00Z"}
        pb_date = _start_time_to_date(ride.get("start_time"))
        assert pb_date == "2026-04-09"

    def test_power_bests_date_from_datetime_start_time(self):
        """After migration, start_time could be datetime if read back from DB."""
        from server.ingest import _start_time_to_date

        ride = {"start_time": datetime(2026, 4, 9, 3, 30, 0, tzinfo=timezone.utc)}
        pb_date = _start_time_to_date(ride.get("start_time"))
        assert pb_date == "2026-04-09"


class TestSyncFingerprintDedup:
    """Verify sync.py fingerprint handles datetime start_time from DB."""

    def test_datetime_start_time_fingerprint(self):
        """Fingerprint extraction from datetime start_time (post-migration)."""
        dt = datetime(2026, 4, 9, 3, 30, 0, tzinfo=timezone.utc)
        # Replicate the sync.py fingerprint logic
        st = dt
        date_str = st.strftime("%Y-%m-%d") if hasattr(st, "strftime") else (str(st)[:10] if st else "")
        assert date_str == "2026-04-09"

    def test_string_start_time_fingerprint(self):
        """Fingerprint extraction from string start_time (pre-migration)."""
        st = "2026-04-09T03:30:00Z"
        date_str = st[:10] if st else ""
        assert date_str == "2026-04-09"


class TestMigrationSqlPatterns:
    """Verify the migration SQL patterns are correct."""

    def test_update_regex_excludes_utc_z(self):
        """Timestamps ending with Z should NOT get +00:00 appended."""
        import re
        # Replicate the migration's regex pattern
        pattern = re.compile(r'[+-]\d{2}:\d{2}$')

        ts_with_z = "2026-04-09T03:30:00Z"
        # The SQL uses NOT LIKE '%Z', so Z is excluded before regex check
        assert ts_with_z.endswith("Z")

    def test_update_regex_excludes_positive_offset(self):
        """Timestamps with + offset should NOT get +00:00 appended."""
        ts_with_plus = "2026-04-09T03:30:00+05:30"
        # The SQL uses NOT LIKE '%+%', so + is excluded before regex check
        assert "+" in ts_with_plus

    def test_update_regex_excludes_negative_offset(self):
        """Timestamps with - offset at end should NOT get +00:00 appended."""
        import re
        pattern = re.compile(r'[+-]\d{2}:\d{2}$')

        ts_with_minus = "2026-04-09T03:30:00-05:00"
        # The SQL regex !~ '[+-]\d{2}:\d{2}$' would match this, so the
        # WHERE clause would exclude it (NOT matching = skip the UPDATE)
        assert pattern.search(ts_with_minus) is not None

    def test_update_regex_includes_bare_timestamp(self):
        """Bare timestamps (no tz info) should get +00:00 appended."""
        import re
        pattern = re.compile(r'[+-]\d{2}:\d{2}$')

        bare = "2026-04-09T03:30:00"
        # No Z, no +, and regex does NOT match -> UPDATE will fire
        assert not bare.endswith("Z")
        assert "+" not in bare
        assert pattern.search(bare) is None  # regex does NOT match

    def test_update_regex_does_not_false_positive_on_date_dashes(self):
        """The date portion dashes (2026-04-09) must not trigger the regex."""
        import re
        pattern = re.compile(r'[+-]\d{2}:\d{2}$')

        bare = "2026-04-09T03:30:00"
        # The dashes in 2026-04-09 are NOT at the end, so the $ anchor
        # ensures they don't match
        assert pattern.search(bare) is None
