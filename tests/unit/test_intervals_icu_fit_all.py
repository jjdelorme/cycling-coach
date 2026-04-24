"""Unit tests for ``fetch_activity_fit_all`` (Phase 9, Campaign 20).

The helper downloads the intervals.icu FIT file once and returns BOTH the
lap and per-record extracts. It exists to dedup the FIT download that
otherwise happens twice per ride (once for records via
``fetch_activity_fit_records`` inside ``_store_records_or_fallback``, once
for laps via ``fetch_activity_fit_laps`` from the bulk-sync hot path).

The tests pin behaviour via mocked ``fitparse``/``httpx`` calls — no real
FIT file or network. Existing single-purpose helpers
(``fetch_activity_fit_laps`` / ``fetch_activity_fit_records``) keep their
behaviour; we just need ``fetch_activity_fit_all`` to compose them
without doing a second HTTP request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import fitparse
import pytest

from server.services.intervals_icu import fetch_activity_fit_all


# ---------------------------------------------------------------------------
# Helpers (same shape as test_intervals_icu_fit_records.py)
# ---------------------------------------------------------------------------


def _make_mock_msg(fields_dict: dict) -> MagicMock:
    msg = MagicMock()
    fields = []
    for name, value in fields_dict.items():
        f = MagicMock()
        f.name = name
        f.value = value
        fields.append(f)
    msg.fields = fields
    return msg


def _patch_fit_response(records: list[MagicMock], laps: list[MagicMock], status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = b"fake-fit-content"

    mock_fitfile = MagicMock()
    mock_fitfile.get_messages.side_effect = (
        lambda kind: records if kind == "record" else (laps if kind == "lap" else [])
    )
    return mock_resp, mock_fitfile


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("server.services.intervals_icu._get_credentials", return_value=("key", "athlete"))
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_all_returns_both_laps_and_records(mock_get, mock_creds):
    """Happy path: one HTTP call yields a dict with both lists populated."""
    base_ts = datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc)
    records = [
        _make_mock_msg({
            "timestamp": base_ts.replace(second=i),
            "power": 200 + i,
            "heart_rate": 140 + i,
            "cadence": 85,
            "enhanced_speed": 7.5,
            "position_lat": int(39.31 * (2**31 / 180)),
            "position_long": int(-108.71 * (2**31 / 180)),
        })
        for i in range(3)
    ]
    laps = [
        _make_mock_msg({
            "message_index": 0,
            "start_time": base_ts,
            "total_timer_time": 60.0,
            "total_distance": 1000.0,
            "avg_power": 220,
            "max_power": 280,
        }),
        _make_mock_msg({
            "message_index": 1,
            "start_time": base_ts.replace(minute=31),
            "total_timer_time": 120.0,
            "total_distance": 2000.0,
            "avg_power": 240,
            "max_power": 300,
        }),
    ]

    mock_resp, mock_fitfile = _patch_fit_response(records, laps)
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.return_value = mock_fitfile
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_all("i12345")

    assert isinstance(result, dict)
    assert set(result.keys()) == {"laps", "records"}
    assert len(result["records"]) == 3
    assert len(result["laps"]) == 2
    # Records carry the same flat shape that fetch_activity_fit_records emits.
    r0 = result["records"][0]
    assert r0["power"] == 200
    assert r0["heart_rate"] == 140
    assert r0["lat"] == pytest.approx(39.31, abs=0.001)
    # Laps carry the same shape that fetch_activity_fit_laps emits.
    l0 = result["laps"][0]
    assert l0["lap_index"] == 0
    assert l0["total_timer_time"] == 60.0
    assert l0["avg_power"] == 220


@patch("server.services.intervals_icu._get_credentials", return_value=("key", "athlete"))
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_all_downloads_only_once(mock_get, mock_creds):
    """The whole point of the helper: a single HTTP request, not two."""
    base_ts = datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc)
    records = [
        _make_mock_msg({"timestamp": base_ts, "power": 200})
    ]
    laps = [
        _make_mock_msg({"message_index": 0, "start_time": base_ts, "total_timer_time": 1.0})
    ]

    mock_resp, mock_fitfile = _patch_fit_response(records, laps)
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.return_value = mock_fitfile
        mock_fitparse.FitParseError = fitparse.FitParseError

        fetch_activity_fit_all("i12345")

    assert mock_get.call_count == 1, "fetch_activity_fit_all must download FIT exactly once"


@patch("server.services.intervals_icu._get_credentials", return_value=("key", "athlete"))
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_all_returns_empty_lists_when_fit_unavailable(mock_get, mock_creds):
    """Non-200 download yields {"laps": [], "records": []} (matches the
    sentinel both single-purpose helpers already use)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.content = b""
    mock_get.return_value = mock_resp

    result = fetch_activity_fit_all("i_missing")

    assert result == {"laps": [], "records": []}


@patch("server.services.intervals_icu._get_credentials", return_value=("key", "athlete"))
@patch("server.services.intervals_icu.httpx.get")
def test_fetch_all_returns_empty_on_parse_failure(mock_get, mock_creds):
    """A FIT parse exception yields the empty sentinel, not a raised error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"corrupt"
    mock_get.return_value = mock_resp

    with patch("server.services.intervals_icu.fitparse") as mock_fitparse:
        mock_fitparse.FitFile.side_effect = fitparse.FitParseError("bad")
        mock_fitparse.FitParseError = fitparse.FitParseError

        result = fetch_activity_fit_all("i_corrupt")

    assert result == {"laps": [], "records": []}
