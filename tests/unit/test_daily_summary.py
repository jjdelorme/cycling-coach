"""Unit tests for aggregate_daily_rides — pure function, no DB."""

import pytest
from server.routers.rides import aggregate_daily_rides


def _ride(date, duration_s=3600.0, tss=80.0, calories=900, distance_m=40000.0, ascent=500, power=200):
    return {"date": date, "duration_s": duration_s, "tss": tss,
            "total_calories": calories, "distance_m": distance_m,
            "total_ascent": ascent, "avg_power": power}


def test_empty_input_returns_empty():
    assert aggregate_daily_rides([]) == []


def test_single_ride_single_day():
    result = aggregate_daily_rides([_ride("2026-04-01")])
    assert len(result) == 1
    r = result[0]
    assert r.date == "2026-04-01"
    assert r.rides == 1
    assert r.duration_s == 3600.0
    assert r.tss == pytest.approx(80.0)
    assert r.total_calories == 900
    assert r.distance_m == pytest.approx(40000.0)
    assert r.ascent_m == 500
    assert r.avg_power == 200


def test_multiple_rides_same_day_are_aggregated():
    rows = [
        _ride("2026-04-01", duration_s=3600.0, tss=80.0, calories=900, distance_m=40000.0, ascent=300, power=200),
        _ride("2026-04-01", duration_s=1800.0, tss=40.0, calories=450, distance_m=20000.0, ascent=200, power=160),
    ]
    result = aggregate_daily_rides(rows)
    assert len(result) == 1
    r = result[0]
    assert r.rides == 2
    assert r.duration_s == pytest.approx(5400.0)
    assert r.tss == pytest.approx(120.0)
    assert r.total_calories == 1350
    assert r.distance_m == pytest.approx(60000.0)
    assert r.ascent_m == 500
    # weighted avg power: (200*3600 + 160*1800) / (3600+1800) = (720000+288000)/5400 = 1008000/5400 = ~186.67 -> 187
    assert r.avg_power == 187


def test_avg_power_weighted_by_duration():
    """Longer ride at lower power should pull weighted avg down."""
    rows = [
        _ride("2026-04-01", duration_s=7200.0, power=150),  # long, low power
        _ride("2026-04-01", duration_s=1800.0, power=300),  # short, high power
    ]
    result = aggregate_daily_rides(rows)
    # weighted: (150*7200 + 300*1800) / 9000 = (1080000 + 540000) / 9000 = 180
    assert result[0].avg_power == 180


def test_avg_power_none_when_no_power_data():
    rows = [{"date": "2026-04-01", "duration_s": 3600.0, "tss": 50.0,
             "total_calories": 600, "distance_m": 30000.0, "total_ascent": 200, "avg_power": 0}]
    result = aggregate_daily_rides(rows)
    assert result[0].avg_power is None


def test_multiple_days_returned_sorted():
    rows = [
        _ride("2026-04-03"),
        _ride("2026-04-01"),
        _ride("2026-04-02"),
    ]
    result = aggregate_daily_rides(rows)
    assert [r.date for r in result] == ["2026-04-01", "2026-04-02", "2026-04-03"]


def test_null_fields_treated_as_zero():
    rows = [{"date": "2026-04-01", "duration_s": None, "tss": None,
             "total_calories": None, "distance_m": None, "total_ascent": None, "avg_power": None}]
    result = aggregate_daily_rides(rows)
    r = result[0]
    assert r.duration_s == 0.0
    assert r.tss == 0.0
    assert r.total_calories == 0
    assert r.distance_m == 0.0
    assert r.ascent_m == 0
    assert r.avg_power is None


def test_rows_missing_fields_treated_as_zero():
    result = aggregate_daily_rides([{"date": "2026-04-01"}])
    r = result[0]
    assert r.rides == 1
    assert r.tss == 0.0
    assert r.total_calories == 0
    assert r.avg_power is None


def test_row_missing_date_is_skipped():
    rows = [
        _ride("2026-04-01"),
        {"duration_s": 1800.0, "tss": 40.0},  # no date
    ]
    result = aggregate_daily_rides(rows)
    assert len(result) == 1
    assert result[0].date == "2026-04-01"
