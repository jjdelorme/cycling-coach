"""Server-side geocoding wrapper with pluggable providers.

Used by ``GET /api/rides`` to resolve a ``?near=`` place name into
``(lat, lon)`` so the bounding-box + Haversine filter can run.

Architecture
------------
We define a small ``GeocodingProvider`` Protocol so the third-party
geocoder can be swapped (Nominatim → Google Maps → Mapbox → ...) without
touching callers. The Nominatim implementation is the default; selection
happens via the ``GEOCODER`` environment variable.

* The cache and the per-process rate limiter live outside the provider so
  they apply uniformly. The cache key is namespaced by provider name so
  switching providers doesn't return stale coords from the previous one.
* Providers raise on transport errors; ``None`` means "resolved cleanly,
  but no match." Callers (rides router) map raises → 503 and ``None`` →
  400 — the contract is unchanged from the pre-refactor version.

Nominatim usage policy
----------------------
* No more than 1 request per second from a single source.
* Requests must include a meaningful ``User-Agent`` (or ``Referer``).

Concurrency note
----------------
``geocode_place`` is a synchronous, blocking call (network + sleep).
FastAPI runs sync handlers on its threadpool, so calling this from the
sync ``list_rides`` handler does *not* block the event loop.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional, Protocol

# ---------------------------------------------------------------------------
# Tunables — kept module-level so tests can patch them.
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "cycling-coach/1.0 (+https://github.com/jasondelaune/cycling-coach)"
RATE_LIMIT_SECONDS = 1.0
TIMEOUT_SECONDS = 5.0
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h
CACHE_MAX_ENTRIES = 512

# ---------------------------------------------------------------------------
# Provider Protocol
# ---------------------------------------------------------------------------


class GeocodingProvider(Protocol):
    """Resolves a place query to ``(lat, lon)``.

    Contract:
    * ``name`` is a short stable identifier used as part of the cache key.
    * ``geocode(query)`` returns ``(lat, lon)`` on a clean match,
      ``None`` for a clean no-match, and *raises* on transport errors so
      the caller can distinguish 400 from 503.
    """

    name: str

    def geocode(self, query: str) -> Optional[tuple[float, float]]:
        ...


# ---------------------------------------------------------------------------
# Internal state — module-level so tests can reset it.
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_last_call_at: float = 0.0

# Cache key: ``f"{provider_name}:{query_lower}"`` so a future provider
# swap can't return stale coords from the previous provider.
_cache: dict[str, tuple[Optional[tuple[float, float]], float]] = {}
_cache_lock = threading.Lock()

_cache_hits = 0
_cache_misses = 0

# Resolved provider — initialised lazily on first call. Tests can clear
# this by calling ``reset_state()``.
_provider: Optional[GeocodingProvider] = None
_provider_lock = threading.Lock()


def _now() -> float:
    """Current wall time. Patched by tests for fake clocks."""
    return time.time()


def _sleep(seconds: float) -> None:
    """Sleep wrapper that tests can patch to avoid real waits."""
    if seconds > 0:
        time.sleep(seconds)


def _default_http_get(url: str, timeout: float, headers: Optional[dict] = None) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — known URL
        return resp.read().decode("utf-8")


# Tests monkeypatch this attribute to inject a fake HTTP layer. The shim
# allows the legacy two-arg signature for back-compat with older tests.
_HTTP_GET: Callable[..., str] = _default_http_get


# ---------------------------------------------------------------------------
# Built-in providers
# ---------------------------------------------------------------------------


class NominatimProvider:
    """Geocode via the public Nominatim/OpenStreetMap service.

    Owns Nominatim-specific concerns: URL, ``User-Agent`` policy, and the
    JSON-shape parsing of the search response. The cross-provider cache
    and rate limiter live in ``geocode_place``.
    """

    name = "nominatim"

    def geocode(self, query: str) -> Optional[tuple[float, float]]:
        params = urllib.parse.urlencode({"q": query, "format": "json", "limit": "1"})
        url = f"{NOMINATIM_URL}?{params}"
        headers = {"User-Agent": USER_AGENT}

        # Support both the new (url, timeout, headers) signature and the
        # legacy (url, timeout) one that older tests may still patch in.
        try:
            raw = _HTTP_GET(url, TIMEOUT_SECONDS, headers)
        except TypeError:
            raw = _HTTP_GET(url, TIMEOUT_SECONDS)

        try:
            results = json.loads(raw)
        except (ValueError, TypeError):
            return None

        if not isinstance(results, list) or not results:
            return None

        first = results[0]
        try:
            return (float(first["lat"]), float(first["lon"]))
        except (KeyError, TypeError, ValueError):
            return None


class MockProvider:
    """In-memory geocoder for E2E and integration tests.

    Selected via ``GEOCODER=mock``. Holds a small fixed table of place
    names so the radius-search pipeline can be exercised end-to-end
    without hitting Nominatim. No network, no sleep, no rate limit —
    pure dict lookup.

    Fixtures are chosen to line up with data that exists in our seed /
    test corpora:

    * ``"white mountains"`` → centre of the synthetic-ride cluster the
      integration seed builds around (Twin Mountain area, NH). Matches
      the dominant ride cluster in the seed fixture and any real Neon
      ride data the E2E suite runs against.
    * ``"santa fe"`` → matches the Santa Fe-centred fixture rides created
      by ``tests/integration/test_api.py`` for the radius integration
      tests, so the same place name is meaningful in both layers.
    * ``"north pole"`` → guaranteed to be far from any real ride; lets
      E2E assert the "no rides match" UI path deterministically.

    Special sentinel: the query ``"__unreachable__"`` raises a transport
    exception so callers/tests can cover the 503 path without
    monkeypatching ``_HTTP_GET``.
    """

    name = "mock"

    # Lookups are case- and whitespace-insensitive; keys are stored
    # already-normalised.
    _FIXTURES: dict[str, tuple[float, float]] = {
        "white mountains": (44.166893, -71.164314),
        "santa fe": (35.6870, -105.9378),
        "santa fe, nm": (35.6870, -105.9378),
        "denver": (39.7392, -104.9903),
        "denver, co": (39.7392, -104.9903),
        "north pole": (89.9, 0.0),
    }

    UNREACHABLE_SENTINEL = "__unreachable__"

    def geocode(self, query: str) -> Optional[tuple[float, float]]:
        normalised = (query or "").strip().lower()
        if normalised == self.UNREACHABLE_SENTINEL:
            raise RuntimeError("MockProvider: simulated geocoder transport failure")
        return self._FIXTURES.get(normalised)


# Registry of built-in providers. Intentionally small — adding a new
# provider is two lines: implement the Protocol, then add an entry here.
_BUILTIN_PROVIDERS: dict[str, Callable[[], GeocodingProvider]] = {
    "nominatim": NominatimProvider,
    "mock": MockProvider,
}


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def _resolve_provider() -> GeocodingProvider:
    """Pick a provider based on the ``GEOCODER`` env var, memoised."""
    global _provider
    if _provider is not None:
        return _provider
    with _provider_lock:
        if _provider is not None:
            return _provider
        name = (os.environ.get("GEOCODER") or "nominatim").strip().lower()
        factory = _BUILTIN_PROVIDERS.get(name)
        if factory is None:
            known = ", ".join(sorted(_BUILTIN_PROVIDERS))
            raise RuntimeError(
                f"Unknown GEOCODER provider: {name!r}. Known providers: {known}."
            )
        _provider = factory()
        return _provider


def set_provider(provider: Optional[GeocodingProvider]) -> None:
    """Override the active provider — for tests."""
    global _provider
    with _provider_lock:
        _provider = provider


# ---------------------------------------------------------------------------
# Test / observability hooks
# ---------------------------------------------------------------------------


def reset_state() -> None:
    """Clear cache, rate limiter, and resolved provider — tests only."""
    global _last_call_at, _cache_hits, _cache_misses, _provider
    with _cache_lock:
        _cache.clear()
        _cache_hits = 0
        _cache_misses = 0
    with _rate_lock:
        _last_call_at = 0.0
    with _provider_lock:
        _provider = None


def get_cache_stats() -> dict:
    """Snapshot of cache metrics for tests/observability."""
    return {
        "hits": _cache_hits,
        "misses": _cache_misses,
        "size": len(_cache),
    }


def _evict_if_full() -> None:
    """LRU-ish eviction: drop oldest entry when the cache is full."""
    while len(_cache) > CACHE_MAX_ENTRIES:
        oldest_key = next(iter(_cache))
        del _cache[oldest_key]


# ---------------------------------------------------------------------------
# Public entry point — back-compat: signature unchanged from prior version
# ---------------------------------------------------------------------------


def geocode_place(query: str) -> Optional[tuple[float, float]]:
    """Resolve ``query`` to ``(lat, lon)`` via the configured provider.

    Returns ``None`` for unresolvable queries. Raises on transport errors
    so the caller can decide between 400 (resolvable, no match) and
    503 (geocoder unreachable).
    """
    global _last_call_at, _cache_hits, _cache_misses

    if not query:
        return None
    normalised = query.strip().lower()
    if not normalised:
        return None

    provider = _resolve_provider()
    key = f"{provider.name}:{normalised}"

    now = _now()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            value, expires_at = cached
            if expires_at > now:
                _cache_hits += 1
                # Refresh LRU position.
                del _cache[key]
                _cache[key] = (value, expires_at)
                return value
            del _cache[key]
        _cache_misses += 1

    # Rate-limit: serialise calls and ensure ≥ RATE_LIMIT_SECONDS between
    # consecutive provider hits from this process.
    with _rate_lock:
        wait = RATE_LIMIT_SECONDS - (_now() - _last_call_at)
        if wait > 0:
            _sleep(wait)
        _last_call_at = _now()

    value = provider.geocode(query)

    with _cache_lock:
        _cache[key] = (value, _now() + CACHE_TTL_SECONDS)
        _evict_if_full()

    return value
