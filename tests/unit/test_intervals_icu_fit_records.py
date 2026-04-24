"""Unit tests for ``fetch_activity_fit_records`` (Phase 5, Campaign 20).

The function downloads the same intervals.icu FIT file we already pull for
laps and extracts the per-second ``record`` messages into the flat dict
shape that ``_store_records_from_fit`` (Phase 6) expects. These tests pin
the parser via mocked ``fitparse``/``httpx`` calls — no real FIT file is
required, no network is touched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import fitparse
import pytest

from server.services.intervals_icu import fetch_activity_fit_records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_record(fields_dict: dict) -> MagicMock:
    """Build a mock fitparse ``record`` message from a name->value dict."""
    msg = MagicMock()
    fields = []
    for name, value in fields_dict.items():
        f = MagicMock()
        f.name = name
        f.value = value
        fields.append(f)
    msg.fields = fields
    return msg


def _patch_fit_response(records: list[MagicMock], status_code: int = 200):
    """Return a (mock_get_response, mock_fitfile) pair for use with patches."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = b"fake-fit-content"

    mock_fitfile = MagicMock()
    # Only return the records when "record" is asked for; return [] for others
    # so the lap path (if ever exercised) doesn't accidentally see records.
    mock_fitfile.get_messages.side_effect = (
        lambda kind: records if kind == "record" else []
    )
    return mock_resp, mock_fitfile


# ---------------------------------------------------------------------------
# Test cases (Step 5.C, 1-6)
# ---------------------------------------------------------------------------


@patch(
    "server.services.intervals_icu._get_credentials",
    return_value=("key", "athlete"),
)
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_records_happy_path(mock_get, mock_creds):
    """5.C.1 — Returns a list whose length matches FIT record count and whose
    fields have the expected types/values."""
    # Build 5 minimal records spanning ~5 seconds.
    base_ts = datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc)
    records = []
    for i in range(5):
        records.append(
            _make_mock_record(
                {
                    "timestamp": base_ts.replace(second=i),
                    "power": 200 + i,
                    "heart_rate": 140 + i,
                    "cadence": 85,
                    "enhanced_speed": 7.5 + i * 0.1,
                    "enhanced_altitude": 1500.0 + i,
                    "distance": 100.0 * i,
                    "position_lat": int(39.31 * (2**31 / 180)),
                    "position_long": int(-108.71 * (2**31 / 180)),
                    "temperature": 22,
                }
            )
        )

    mock_resp, mock_fitfile = _patch_fit_response(records)
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.return_value = mock_fitfile
        # Preserve the real exception type for downstream parse-error checks
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_records("i12345")

    assert isinstance(result, list)
    assert len(result) == 5
    r0 = result[0]
    assert isinstance(r0, dict)
    assert r0["power"] == 200
    assert r0["heart_rate"] == 140
    assert r0["cadence"] == 85
    assert r0["speed"] == pytest.approx(7.5)
    assert r0["altitude"] == pytest.approx(1500.0)
    assert r0["distance"] == 0.0
    assert r0["lat"] == pytest.approx(39.31, abs=0.001)
    assert r0["lon"] == pytest.approx(-108.71, abs=0.001)
    assert r0["temperature"] == 22
    assert isinstance(r0["timestamp_utc"], str)


@patch(
    "server.services.intervals_icu._get_credentials",
    return_value=("key", "athlete"),
)
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_records_semicircle_conversion(mock_get, mock_creds):
    """5.C.2 — A known semicircle value maps to the expected decimal degrees."""
    # 469762048 semicircles ~= 39.3750°
    semicircles_lat = 469762048
    semicircles_lon = -1296535040  # ~ -108.6328°

    records = [
        _make_mock_record(
            {
                "timestamp": datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc),
                "position_lat": semicircles_lat,
                "position_long": semicircles_lon,
            }
        )
    ]

    mock_resp, mock_fitfile = _patch_fit_response(records)
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.return_value = mock_fitfile
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_records("i12345")

    assert len(result) == 1
    expected_lat = semicircles_lat * (180 / 2**31)
    expected_lon = semicircles_lon * (180 / 2**31)
    assert result[0]["lat"] == pytest.approx(expected_lat)
    assert result[0]["lon"] == pytest.approx(expected_lon)
    # ~39.31° latitude (Fruita-ish) / ~-108.7° longitude sanity bounds
    assert 39.0 < result[0]["lat"] < 40.0
    assert -109.0 < result[0]["lon"] < -108.0


@patch(
    "server.services.intervals_icu._get_credentials",
    return_value=("key", "athlete"),
)
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_records_no_fit_returns_empty_list(mock_get, mock_creds):
    """5.C.3 — Non-200 from intervals.icu /file → ``[]`` (no exception)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.content = b""
    mock_get.return_value = mock_resp

    result = fetch_activity_fit_records("i_missing")

    assert result == []


@patch(
    "server.services.intervals_icu._get_credentials",
    return_value=("key", "athlete"),
)
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_records_parse_error_returns_empty_list(mock_get, mock_creds):
    """5.C.4 — fitparse raising ``FitParseError`` (or any exception) → ``[]``."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"not-a-real-fit-file"
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.side_effect = fitparse.FitParseError("bad fit")
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_records("i_corrupt")

    assert result == []


@patch(
    "server.services.intervals_icu._get_credentials",
    return_value=("key", "athlete"),
)
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_records_uses_enhanced_fields_when_present(mock_get, mock_creds):
    """5.C.5 — ``enhanced_speed`` wins over ``speed``; ``enhanced_altitude``
    wins over ``altitude``."""
    records = [
        _make_mock_record(
            {
                "timestamp": datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc),
                "speed": 1.0,
                "enhanced_speed": 9.99,
                "altitude": 100.0,
                "enhanced_altitude": 1234.5,
            }
        ),
        # Second record only has the non-enhanced fields — those are used.
        _make_mock_record(
            {
                "timestamp": datetime(2026, 4, 13, 14, 30, 1, tzinfo=timezone.utc),
                "speed": 5.5,
                "altitude": 555.5,
            }
        ),
    ]

    mock_resp, mock_fitfile = _patch_fit_response(records)
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.return_value = mock_fitfile
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_records("i_enh")

    assert len(result) == 2
    assert result[0]["speed"] == pytest.approx(9.99)
    assert result[0]["altitude"] == pytest.approx(1234.5)
    assert result[1]["speed"] == pytest.approx(5.5)
    assert result[1]["altitude"] == pytest.approx(555.5)


@patch(
    "server.services.intervals_icu._get_credentials",
    return_value=("key", "athlete"),
)
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_records_emits_iso_utc_timestamps(mock_get, mock_creds):
    """5.C.6 — Every ``timestamp_utc`` is an ISO-8601 string ending with
    ``Z`` or ``+00:00`` (downstream column is TEXT)."""
    records = [
        _make_mock_record(
            {
                "timestamp": datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc),
            }
        ),
        # fitparse sometimes returns naive datetimes (UTC by spec) — make sure
        # we tag them with UTC rather than emitting a naive ISO string.
        _make_mock_record({"timestamp": datetime(2026, 4, 13, 14, 30, 1)}),
    ]

    mock_resp, mock_fitfile = _patch_fit_response(records)
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.return_value = mock_fitfile
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_records("i_ts")

    assert len(result) == 2
    for r in result:
        ts = r["timestamp_utc"]
        assert isinstance(ts, str)
        assert ts.endswith("Z") or ts.endswith("+00:00")


@patch(
    "server.services.intervals_icu._get_credentials",
    return_value=("key", "athlete"),
)
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_records_zero_records_returns_empty_list(mock_get, mock_creds):
    """A FIT file with zero ``record`` messages → ``[]`` (D1 contract)."""
    mock_resp, mock_fitfile = _patch_fit_response([])
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.return_value = mock_fitfile
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_records("i_empty")

    assert result == []


@patch(
    "server.services.intervals_icu._get_credentials",
    return_value=("key", "athlete"),
)
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_records_skips_records_without_timestamp(mock_get, mock_creds):
    """Defensive: records missing ``timestamp`` are dropped, others retained."""
    records = [
        _make_mock_record(
            {
                "timestamp": datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc),
                "power": 200,
            }
        ),
        # No timestamp key at all — must be skipped.
        _make_mock_record({"power": 999}),
        _make_mock_record(
            {
                "timestamp": datetime(2026, 4, 13, 14, 30, 2, tzinfo=timezone.utc),
                "power": 220,
            }
        ),
    ]

    mock_resp, mock_fitfile = _patch_fit_response(records)
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.return_value = mock_fitfile
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_records("i_skip")

    assert len(result) == 2
    assert result[0]["power"] == 200
    assert result[1]["power"] == 220
