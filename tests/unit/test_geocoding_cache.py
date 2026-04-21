"""Unit tests for ``server.services.geocoding``.

Exercises the rate limiter, in-process LRU+TTL cache, and the result
parsing — without ever touching the real Nominatim service. Tests
monkeypatch the module-level ``_HTTP_GET`` callable as well as ``_now``
and ``_sleep`` so we can use a fake clock and avoid real waits.
"""

from __future__ import annotations

import json

import pytest

from server.services import geocoding


@pytest.fixture(autouse=True)
def _reset_state():
    geocoding.reset_state()
    yield
    geocoding.reset_state()


def _make_fake_http(responses: list, calls: list[str]):
    """Return a fake ``_HTTP_GET`` that pops responses off a queue."""
    iterator = iter(responses)

    def _fake(url: str, timeout: float) -> str:
        calls.append(url)
        try:
            value = next(iterator)
        except StopIteration as exc:  # noqa: BLE001
            raise AssertionError("Fake HTTP exhausted — geocoder called too many times") from exc
        if isinstance(value, Exception):
            raise value
        return value

    return _fake


def _santa_fe_payload() -> str:
    return json.dumps([{"lat": "35.69", "lon": "-105.94", "display_name": "Santa Fe, NM"}])


def _denver_payload() -> str:
    return json.dumps([{"lat": "39.74", "lon": "-104.99", "display_name": "Denver, CO"}])


def test_first_call_invokes_http_and_parses_lat_lon(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(geocoding, "_HTTP_GET", _make_fake_http([_santa_fe_payload()], calls))
    # Avoid the rate-limit sleep on first call.
    monkeypatch.setattr(geocoding, "_now", lambda: 1000.0)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    result = geocoding.geocode_place("Santa Fe, NM")
    assert result == (pytest.approx(35.69), pytest.approx(-105.94))
    assert len(calls) == 1
    stats = geocoding.get_cache_stats()
    assert stats["misses"] == 1 and stats["hits"] == 0


def test_repeat_query_is_served_from_cache(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(geocoding, "_HTTP_GET", _make_fake_http([_santa_fe_payload()], calls))
    monkeypatch.setattr(geocoding, "_now", lambda: 2000.0)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    a = geocoding.geocode_place("Santa Fe, NM")
    b = geocoding.geocode_place("santa fe, nm")  # case-insensitive cache key
    assert a == b
    # Only one HTTP call — the second hit was served from cache.
    assert len(calls) == 1
    stats = geocoding.get_cache_stats()
    assert stats["hits"] == 1 and stats["misses"] == 1


def test_cache_expires_after_ttl(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        geocoding, "_HTTP_GET",
        _make_fake_http([_santa_fe_payload(), _santa_fe_payload()], calls),
    )
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    fake_clock = {"now": 5000.0}
    monkeypatch.setattr(geocoding, "_now", lambda: fake_clock["now"])

    geocoding.geocode_place("Santa Fe, NM")
    fake_clock["now"] += geocoding.CACHE_TTL_SECONDS + 1
    geocoding.geocode_place("Santa Fe, NM")

    # TTL expiry forces a second network call.
    assert len(calls) == 2


def test_rate_limiter_sleeps_when_recent_call(monkeypatch):
    calls: list[str] = []
    sleeps: list[float] = []
    monkeypatch.setattr(
        geocoding, "_HTTP_GET",
        _make_fake_http([_santa_fe_payload(), _denver_payload()], calls),
    )
    monkeypatch.setattr(geocoding, "_sleep", lambda s: sleeps.append(s))

    fake_clock = {"now": 10000.0}
    monkeypatch.setattr(geocoding, "_now", lambda: fake_clock["now"])

    geocoding.geocode_place("Santa Fe, NM")
    # Second call immediately after — clock has not advanced.
    geocoding.geocode_place("Denver, CO")

    # The second call must have triggered a sleep close to RATE_LIMIT_SECONDS.
    assert any(s >= geocoding.RATE_LIMIT_SECONDS - 0.01 for s in sleeps)


def test_rate_limiter_skips_sleep_when_enough_time_elapsed(monkeypatch):
    calls: list[str] = []
    sleeps: list[float] = []
    monkeypatch.setattr(
        geocoding, "_HTTP_GET",
        _make_fake_http([_santa_fe_payload(), _denver_payload()], calls),
    )
    monkeypatch.setattr(geocoding, "_sleep", lambda s: sleeps.append(s))

    fake_clock = {"now": 20000.0}
    monkeypatch.setattr(geocoding, "_now", lambda: fake_clock["now"])

    geocoding.geocode_place("Santa Fe, NM")
    fake_clock["now"] += geocoding.RATE_LIMIT_SECONDS + 0.5
    geocoding.geocode_place("Denver, CO")

    # No sleep was needed because >1s elapsed between calls.
    assert all(s <= 0 for s in sleeps)


def test_unresolvable_query_returns_none_and_caches_negative_result(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(geocoding, "_HTTP_GET", _make_fake_http(["[]"], calls))
    monkeypatch.setattr(geocoding, "_now", lambda: 30000.0)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    a = geocoding.geocode_place("ZzzNotARealPlace")
    b = geocoding.geocode_place("zzznotarealplace")
    assert a is None and b is None
    # Only one HTTP call — the negative result is cached.
    assert len(calls) == 1


def test_empty_query_returns_none_without_http_call(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(geocoding, "_HTTP_GET", _make_fake_http([], calls))
    assert geocoding.geocode_place("") is None
    assert geocoding.geocode_place("   ") is None
    assert calls == []


def test_http_exception_propagates_to_caller(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        geocoding, "_HTTP_GET",
        _make_fake_http([RuntimeError("connection refused")], calls),
    )
    monkeypatch.setattr(geocoding, "_now", lambda: 40000.0)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    with pytest.raises(RuntimeError):
        geocoding.geocode_place("Santa Fe, NM")
