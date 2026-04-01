"""Tests for FIT file device lap extraction and related helpers."""

import pytest
from unittest.mock import patch, MagicMock

from server.services.intervals_icu import (
    _semicircles_to_degrees,
    fetch_activity_fit_laps,
    map_activity_to_ride,
)
from server.services.sync import _enrich_laps_with_np


class TestSemicirclesToDegrees:
    """Tests for coordinate conversion helper."""

    def test_none_returns_none(self):
        assert _semicircles_to_degrees(None) is None

    def test_zero(self):
        assert _semicircles_to_degrees(0) == 0

    def test_positive_semicircles(self):
        # 2^31 semicircles = 180 degrees
        result = _semicircles_to_degrees(2**31)
        assert result == pytest.approx(180.0)

    def test_negative_semicircles(self):
        result = _semicircles_to_degrees(-(2**31))
        assert result == pytest.approx(-180.0)

    def test_known_coordinate(self):
        # ~47.6 degrees N (Seattle-ish latitude)
        semicircles = int(47.6 * (2**31 / 180))
        result = _semicircles_to_degrees(semicircles)
        assert result == pytest.approx(47.6, abs=0.01)

    def test_small_value_passthrough(self):
        # Values already in degrees (abs <= 180) pass through unchanged
        assert _semicircles_to_degrees(45.5) == 45.5
        assert _semicircles_to_degrees(-120.3) == -120.3


class TestFetchActivityFitLaps:
    """Tests for FIT file download and lap extraction."""

    def _make_mock_lap(self, fields_dict):
        """Create a mock fitparse lap message from a dict of field name -> value."""
        mock_lap = MagicMock()
        mock_fields = []
        for name, value in fields_dict.items():
            field = MagicMock()
            field.name = name
            field.value = value
            mock_fields.append(field)
        mock_lap.fields = mock_fields
        return mock_lap

    @patch("server.services.intervals_icu._get_credentials", return_value=("key", "athlete"))
    @patch("server.services.intervals_icu.httpx.get")
    def test_extracts_laps_from_fit_file(self, mock_get, mock_creds):
        """Verify correct field mapping from FIT lap messages to our schema."""
        # Mock the HTTP response with fake FIT binary content
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake-fit-content"
        mock_get.return_value = mock_resp

        mock_laps = [
            self._make_mock_lap({
                "message_index": 0,
                "start_time": "2026-03-31 08:00:00",
                "total_timer_time": 900.9,
                "total_elapsed_time": 900.9,
                "total_distance": 5000.0,
                "avg_power": 161,
                "Normalized Power": 165,
                "max_power": 250,
                "avg_heart_rate": 102,
                "max_heart_rate": 130,
                "avg_cadence": 85,
                "max_cadence": 110,
                "enhanced_avg_speed": 5.5,
                "enhanced_max_speed": 8.2,
                "total_ascent": 50,
                "total_descent": 30,
                "total_calories": 200,
                "total_work": 144900,
                "intensity": "active",
                "lap_trigger": "manual",
                "wkt_step_index": None,
                "start_position_lat": int(47.6 * (2**31 / 180)),
                "start_position_long": int(-122.3 * (2**31 / 180)),
                "end_position_lat": int(47.7 * (2**31 / 180)),
                "end_position_long": int(-122.2 * (2**31 / 180)),
                "avg_temperature": 20,
            }),
            self._make_mock_lap({
                "message_index": 1,
                "start_time": "2026-03-31 08:15:01",
                "total_timer_time": 3384.3,
                "total_elapsed_time": 3384.3,
                "total_distance": 25000.0,
                "avg_power": 181,
                "Normalized Power": 185,
                "max_power": 300,
                "avg_heart_rate": 108,
                "max_heart_rate": 145,
                "avg_cadence": 88,
                "max_cadence": 115,
                "enhanced_avg_speed": 7.4,
                "enhanced_max_speed": 10.1,
                "total_ascent": 200,
                "total_descent": 180,
                "total_calories": 800,
                "total_work": 612498,
                "intensity": "active",
                "lap_trigger": "manual",
                "wkt_step_index": None,
                "start_position_lat": None,
                "start_position_long": None,
                "end_position_lat": None,
                "end_position_long": None,
                "avg_temperature": 22,
            }),
        ]

        mock_fitfile = MagicMock()
        mock_fitfile.get_messages.return_value = mock_laps

        with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
            mock_fitparse.FitFile.return_value = mock_fitfile

            laps = fetch_activity_fit_laps("i12345")

        assert len(laps) == 2

        # Verify first lap field mapping
        lap0 = laps[0]
        assert lap0["lap_index"] == 0
        assert lap0["start_time"] == "2026-03-31 08:00:00"
        assert lap0["total_timer_time"] == 900.9
        assert lap0["total_elapsed_time"] == 900.9
        assert lap0["total_distance"] == 5000.0
        assert lap0["avg_power"] == 161
        assert lap0["normalized_power"] == 165
        assert lap0["max_power"] == 250
        assert lap0["avg_hr"] == 102
        assert lap0["max_hr"] == 130
        assert lap0["avg_cadence"] == 85
        assert lap0["max_cadence"] == 110
        assert lap0["avg_speed"] == 5.5
        assert lap0["max_speed"] == 8.2
        assert lap0["total_ascent"] == 50
        assert lap0["total_descent"] == 30
        assert lap0["total_calories"] == 200
        assert lap0["total_work"] == 144900
        assert lap0["intensity"] == "active"
        assert lap0["lap_trigger"] == "manual"
        assert lap0["start_lat"] == pytest.approx(47.6, abs=0.01)
        assert lap0["start_lon"] == pytest.approx(-122.3, abs=0.01)
        assert lap0["avg_temperature"] == 20

        # Verify second lap
        lap1 = laps[1]
        assert lap1["lap_index"] == 1
        assert lap1["total_timer_time"] == 3384.3
        assert lap1["avg_power"] == 181
        assert lap1["lap_trigger"] == "manual"
        assert lap1["start_lat"] is None
        assert lap1["start_lon"] is None

    @patch("server.services.intervals_icu._get_credentials", return_value=("key", "athlete"))
    @patch("server.services.intervals_icu.httpx.get")
    def test_returns_empty_on_http_error(self, mock_get, mock_creds):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        laps = fetch_activity_fit_laps("i99999")
        assert laps == []

    @patch("server.services.intervals_icu._get_credentials", return_value=("key", "athlete"))
    @patch("server.services.intervals_icu.httpx.get")
    def test_returns_empty_on_parse_error(self, mock_get, mock_creds):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"not-a-fit-file"
        mock_get.return_value = mock_resp

        with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
            mock_fitparse.FitFile.side_effect = Exception("Invalid FIT file")
            laps = fetch_activity_fit_laps("i99999")

        assert laps == []

    @patch("server.services.intervals_icu._get_credentials", return_value=("key", "athlete"))
    @patch("server.services.intervals_icu.httpx.get")
    def test_handles_non_string_intensity_and_trigger(self, mock_get, mock_creds):
        """Non-string intensity/lap_trigger values should become None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake"
        mock_get.return_value = mock_resp

        mock_lap = self._make_mock_lap({
            "message_index": 0,
            "start_time": None,
            "total_timer_time": 100.0,
            "total_elapsed_time": 100.0,
            "total_distance": None,
            "avg_power": None,
            "Normalized Power": None,
            "max_power": None,
            "avg_heart_rate": None,
            "max_heart_rate": None,
            "avg_cadence": None,
            "max_cadence": None,
            "enhanced_avg_speed": None,
            "enhanced_max_speed": None,
            "total_ascent": None,
            "total_descent": None,
            "total_calories": None,
            "total_work": None,
            "intensity": 0,  # non-string
            "lap_trigger": 1,  # non-string
            "wkt_step_index": None,
            "start_position_lat": None,
            "start_position_long": None,
            "end_position_lat": None,
            "end_position_long": None,
            "avg_temperature": None,
        })

        mock_fitfile = MagicMock()
        mock_fitfile.get_messages.return_value = [mock_lap]

        with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
            mock_fitparse.FitFile.return_value = mock_fitfile
            laps = fetch_activity_fit_laps("i12345")

        assert len(laps) == 1
        assert laps[0]["intensity"] is None
        assert laps[0]["lap_trigger"] is None


class TestEnrichLapsWithNP:
    """Tests for calculating NP per lap from stream power data."""

    def _make_lap(self, duration, normalized_power=None):
        return {
            "lap_index": 0,
            "start_time": None,
            "total_timer_time": duration,
            "total_elapsed_time": duration,
            "total_distance": None,
            "avg_power": 200,
            "normalized_power": normalized_power,
            "max_power": 300,
            "avg_hr": None,
            "max_hr": None,
            "avg_cadence": None,
            "max_cadence": None,
            "avg_speed": None,
            "max_speed": None,
            "total_ascent": None,
            "total_descent": None,
            "total_calories": None,
            "total_work": None,
            "intensity": None,
            "lap_trigger": None,
            "wkt_step_index": None,
            "start_lat": None,
            "start_lon": None,
            "end_lat": None,
            "end_lon": None,
            "avg_temperature": None,
        }

    def test_calculates_np_for_laps(self):
        """NP is computed from stream power data when missing from source."""
        # 120 seconds of steady 200w power
        stream_map = {
            "time": list(range(120)),
            "watts": [200] * 120,
        }
        laps = [self._make_lap(60), self._make_lap(60)]
        laps[0]["lap_index"] = 0
        laps[1]["lap_index"] = 1

        _enrich_laps_with_np(laps, stream_map)

        # Steady power → NP ≈ avg power
        assert laps[0]["normalized_power"] == 200
        assert laps[1]["normalized_power"] == 200

    def test_preserves_existing_np(self):
        """Laps that already have NP from source data are not overwritten."""
        stream_map = {
            "time": list(range(60)),
            "watts": [200] * 60,
        }
        laps = [self._make_lap(60, normalized_power=185)]

        _enrich_laps_with_np(laps, stream_map)

        assert laps[0]["normalized_power"] == 185

    def test_variable_power_np_exceeds_average(self):
        """NP should be higher than average power for variable efforts."""
        # Alternating blocks of 100w and 300w (60s each) for 240s total
        # Blocks longer than the 30s rolling window so variability shows up in NP
        watts = [100] * 60 + [300] * 60 + [100] * 60 + [300] * 60
        stream_map = {
            "time": list(range(240)),
            "watts": watts,
        }
        laps = [self._make_lap(240)]

        _enrich_laps_with_np(laps, stream_map)

        # Average is 200, NP should be higher due to variability
        assert laps[0]["normalized_power"] is not None
        assert laps[0]["normalized_power"] > 200

    def test_no_watts_stream(self):
        """No crash when watts stream is missing."""
        stream_map = {"time": list(range(60)), "watts": []}
        laps = [self._make_lap(60)]

        _enrich_laps_with_np(laps, stream_map)

        assert laps[0]["normalized_power"] is None

    def test_mismatched_stream_lengths(self):
        """No crash when time and watts arrays differ in length."""
        stream_map = {"time": list(range(60)), "watts": [200] * 30}
        laps = [self._make_lap(60)]

        _enrich_laps_with_np(laps, stream_map)

        # Should bail out — lengths don't match
        assert laps[0]["normalized_power"] is None

    def test_zero_duration_lap_skipped(self):
        """Laps with zero or missing duration are skipped without error."""
        stream_map = {
            "time": list(range(60)),
            "watts": [200] * 60,
        }
        laps = [self._make_lap(0), self._make_lap(60)]
        laps[1]["lap_index"] = 1

        _enrich_laps_with_np(laps, stream_map)

        assert laps[0]["normalized_power"] is None
        assert laps[1]["normalized_power"] == 200


class TestMapActivityToRideTitle:
    """Tests for title extraction in map_activity_to_ride."""

    def test_title_extracted(self):
        activity = {
            "id": "i123",
            "start_date_local": "2026-03-31T08:00:00",
            "type": "Ride",
            "name": "Morning Endurance",
            "moving_time": 3600,
            "distance": 30000,
        }
        ride = map_activity_to_ride(activity)
        assert ride is not None
        assert ride["title"] == "Morning Endurance"

    def test_title_none_when_missing(self):
        activity = {
            "id": "i124",
            "start_date_local": "2026-03-31T08:00:00",
            "type": "Ride",
            "moving_time": 3600,
            "distance": 30000,
        }
        ride = map_activity_to_ride(activity)
        assert ride is not None
        assert ride["title"] is None
