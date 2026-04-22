"""Unit tests for ``server.services.geocoding``.

Covers:
* The provider-agnostic cache + rate limiter (via a ``FakeProvider``
  implementing the ``GeocodingProvider`` Protocol).
* Provider selection from the ``GEOCODER`` env var, including the
  unknown-name error path.
* One Nominatim-specific test that pins down the URL/User-Agent/parse
  logic — kept thin so swapping providers later is easy.
"""

from __future__ import annotations

import json
from typing import Optional

import pytest

from server.services import geocoding


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    # Clear any GEOCODER override leaking from another test.
    monkeypatch.delenv("GEOCODER", raising=False)
    geocoding.reset_state()
    yield
    geocoding.reset_state()


class FakeProvider:
    """Minimal ``GeocodingProvider`` implementation used by most tests."""

    def __init__(self, responses: list, name: str = "fake") -> None:
        self.name = name
        self._iter = iter(responses)
        self.calls: list[str] = []

    def geocode(self, query: str) -> Optional[tuple[float, float]]:
        self.calls.append(query)
        try:
            value = next(self._iter)
        except StopIteration as exc:  # noqa: BLE001
            raise AssertionError(
                "Fake provider exhausted — geocode() called too many times"
            ) from exc
        if isinstance(value, Exception):
            raise value
        return value


def _install_provider(monkeypatch, responses: list) -> FakeProvider:
    provider = FakeProvider(responses)
    geocoding.set_provider(provider)
    monkeypatch.setattr(geocoding, "_now", lambda: 1000.0)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)
    return provider


# ---------------------------------------------------------------------------
# Provider-agnostic behaviour (cache + rate limiter)
# ---------------------------------------------------------------------------


def test_first_call_invokes_provider_and_returns_lat_lon(monkeypatch):
    provider = _install_provider(monkeypatch, [(35.69, -105.94)])

    result = geocoding.geocode_place("Santa Fe, NM")
    assert result == (pytest.approx(35.69), pytest.approx(-105.94))
    assert provider.calls == ["Santa Fe, NM"]
    stats = geocoding.get_cache_stats()
    assert stats["misses"] == 1 and stats["hits"] == 0


def test_repeat_query_is_served_from_cache(monkeypatch):
    provider = _install_provider(monkeypatch, [(35.69, -105.94)])

    a = geocoding.geocode_place("Santa Fe, NM")
    b = geocoding.geocode_place("santa fe, nm")  # case-insensitive cache key
    assert a == b
    assert provider.calls == ["Santa Fe, NM"]
    stats = geocoding.get_cache_stats()
    assert stats["hits"] == 1 and stats["misses"] == 1


def test_cache_expires_after_ttl(monkeypatch):
    provider = FakeProvider([(35.69, -105.94), (35.69, -105.94)])
    geocoding.set_provider(provider)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    fake_clock = {"now": 5000.0}
    monkeypatch.setattr(geocoding, "_now", lambda: fake_clock["now"])

    geocoding.geocode_place("Santa Fe, NM")
    fake_clock["now"] += geocoding.CACHE_TTL_SECONDS + 1
    geocoding.geocode_place("Santa Fe, NM")

    assert len(provider.calls) == 2


def test_rate_limiter_sleeps_when_recent_call(monkeypatch):
    provider = FakeProvider([(35.69, -105.94), (39.74, -104.99)])
    geocoding.set_provider(provider)
    sleeps: list[float] = []
    monkeypatch.setattr(geocoding, "_sleep", lambda s: sleeps.append(s))

    fake_clock = {"now": 10000.0}
    monkeypatch.setattr(geocoding, "_now", lambda: fake_clock["now"])

    geocoding.geocode_place("Santa Fe, NM")
    geocoding.geocode_place("Denver, CO")

    assert any(s >= geocoding.RATE_LIMIT_SECONDS - 0.01 for s in sleeps)


def test_rate_limiter_skips_sleep_when_enough_time_elapsed(monkeypatch):
    provider = FakeProvider([(35.69, -105.94), (39.74, -104.99)])
    geocoding.set_provider(provider)
    sleeps: list[float] = []
    monkeypatch.setattr(geocoding, "_sleep", lambda s: sleeps.append(s))

    fake_clock = {"now": 20000.0}
    monkeypatch.setattr(geocoding, "_now", lambda: fake_clock["now"])

    geocoding.geocode_place("Santa Fe, NM")
    fake_clock["now"] += geocoding.RATE_LIMIT_SECONDS + 0.5
    geocoding.geocode_place("Denver, CO")

    assert all(s <= 0 for s in sleeps)


def test_unresolvable_query_returns_none_and_caches_negative_result(monkeypatch):
    provider = _install_provider(monkeypatch, [None])

    a = geocoding.geocode_place("ZzzNotARealPlace")
    b = geocoding.geocode_place("zzznotarealplace")
    assert a is None and b is None
    # Only one provider call — the negative result is cached.
    assert len(provider.calls) == 1


def test_empty_query_returns_none_without_provider_call(monkeypatch):
    provider = _install_provider(monkeypatch, [])
    assert geocoding.geocode_place("") is None
    assert geocoding.geocode_place("   ") is None
    assert provider.calls == []


def test_provider_exception_propagates_to_caller(monkeypatch):
    _install_provider(monkeypatch, [RuntimeError("connection refused")])

    with pytest.raises(RuntimeError):
        geocoding.geocode_place("Santa Fe, NM")


def test_cache_key_is_namespaced_per_provider(monkeypatch):
    """Switching providers must not return stale coords from a previous one."""
    monkeypatch.setattr(geocoding, "_now", lambda: 1000.0)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    p1 = FakeProvider([(1.0, 2.0)], name="alpha")
    geocoding.set_provider(p1)
    assert geocoding.geocode_place("Somewhere") == (1.0, 2.0)

    p2 = FakeProvider([(9.0, 8.0)], name="beta")
    geocoding.set_provider(p2)
    # Same query, different provider — must hit the new provider.
    assert geocoding.geocode_place("Somewhere") == (9.0, 8.0)
    assert p2.calls == ["Somewhere"]


# ---------------------------------------------------------------------------
# Provider selection from environment
# ---------------------------------------------------------------------------


def test_default_provider_is_nominatim(monkeypatch):
    monkeypatch.delenv("GEOCODER", raising=False)
    geocoding.set_provider(None)  # force re-resolve on next call
    # Force resolution by making a no-op call path: empty query short-circuits
    # before resolution, so call the resolver directly via a non-empty query
    # with a stubbed Nominatim HTTP.
    monkeypatch.setattr(geocoding, "_HTTP_GET", lambda *a, **kw: "[]")
    monkeypatch.setattr(geocoding, "_now", lambda: 1.0)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    geocoding.geocode_place("Anywhere")
    # _provider is private but the namespaced cache key reveals it.
    cache_keys = list(geocoding._cache.keys())
    assert cache_keys and cache_keys[0].startswith("nominatim:")


def test_unknown_geocoder_env_raises(monkeypatch):
    monkeypatch.setenv("GEOCODER", "not-a-real-provider")
    geocoding.set_provider(None)

    with pytest.raises(RuntimeError) as exc_info:
        geocoding.geocode_place("Santa Fe")
    msg = str(exc_info.value)
    assert "not-a-real-provider" in msg
    assert "nominatim" in msg  # lists known providers


def test_geocoder_env_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("GEOCODER", "NOMINATIM")
    geocoding.set_provider(None)
    monkeypatch.setattr(geocoding, "_HTTP_GET", lambda *a, **kw: "[]")
    monkeypatch.setattr(geocoding, "_now", lambda: 1.0)
    monkeypatch.setattr(geocoding, "_sleep", lambda s: None)

    # Should not raise.
    geocoding.geocode_place("Anywhere")


# ---------------------------------------------------------------------------
# Nominatim-specific test — pin down URL, header, and parse logic.
# ---------------------------------------------------------------------------


def test_nominatim_provider_builds_search_url_and_parses_response(monkeypatch):
    captured: dict = {}

    def _fake_http(url: str, timeout: float, headers: Optional[dict] = None) -> str:
        captured["url"] = url
        captured["timeout"] = timeout
        captured["headers"] = headers or {}
        return json.dumps([{"lat": "35.69", "lon": "-105.94", "display_name": "Santa Fe"}])

    monkeypatch.setattr(geocoding, "_HTTP_GET", _fake_http)

    provider = geocoding.NominatimProvider()
    result = provider.geocode("Santa Fe, NM")

    assert result == (pytest.approx(35.69), pytest.approx(-105.94))
    assert captured["url"].startswith(geocoding.NOMINATIM_URL)
    assert "q=Santa+Fe%2C+NM" in captured["url"]
    assert "format=json" in captured["url"]
    assert "limit=1" in captured["url"]
    # Nominatim policy: User-Agent must be set.
    assert "User-Agent" in captured["headers"]
    assert "cycling-coach" in captured["headers"]["User-Agent"]


def test_nominatim_provider_returns_none_for_empty_results(monkeypatch):
    monkeypatch.setattr(geocoding, "_HTTP_GET", lambda *a, **kw: "[]")
    assert geocoding.NominatimProvider().geocode("Nowhere") is None


def test_nominatim_provider_returns_none_for_malformed_json(monkeypatch):
    monkeypatch.setattr(geocoding, "_HTTP_GET", lambda *a, **kw: "{not json")
    assert geocoding.NominatimProvider().geocode("Nowhere") is None


# ---------------------------------------------------------------------------
# MockProvider — used by the E2E radius test and as a deterministic
# integration seam for any future test that needs a stable place table.
# ---------------------------------------------------------------------------


def test_mock_provider_returns_known_fixture():
    p = geocoding.MockProvider()
    result = p.geocode("white mountains")
    assert result == (pytest.approx(44.166893), pytest.approx(-71.164314))


def test_mock_provider_lookup_is_case_and_whitespace_insensitive():
    p = geocoding.MockProvider()
    a = p.geocode("Santa Fe")
    b = p.geocode("  SANTA FE  ")
    c = p.geocode("santa fe")
    assert a == b == c
    assert a == (pytest.approx(35.6870), pytest.approx(-105.9378))


def test_mock_provider_unknown_query_returns_none():
    p = geocoding.MockProvider()
    assert p.geocode("ZzzNotARealPlace") is None
    # Empty/whitespace also returns None — same contract as Nominatim.
    assert p.geocode("") is None
    assert p.geocode("   ") is None


def test_mock_provider_unreachable_sentinel_raises():
    p = geocoding.MockProvider()
    with pytest.raises(RuntimeError) as exc_info:
        p.geocode("__unreachable__")
    assert "MockProvider" in str(exc_info.value)
    # Case-insensitive sentinel.
    with pytest.raises(RuntimeError):
        p.geocode("__UNREACHABLE__")


def test_geocoder_env_mock_selects_mock_provider(monkeypatch):
    monkeypatch.setenv("GEOCODER", "mock")
    geocoding.set_provider(None)  # force re-resolve

    result = geocoding.geocode_place("White Mountains")
    assert result == (pytest.approx(44.166893), pytest.approx(-71.164314))

    # Cache key is namespaced with the provider name.
    cache_keys = list(geocoding._cache.keys())
    assert cache_keys and cache_keys[0].startswith("mock:")


def test_geocoder_env_mock_propagates_unreachable_via_geocode_place(monkeypatch):
    """Ensures the 503-path can be exercised end-to-end via the env-selected provider."""
    monkeypatch.setenv("GEOCODER", "mock")
    geocoding.set_provider(None)

    with pytest.raises(RuntimeError):
        geocoding.geocode_place("__unreachable__")
