"""Server-side geocoding wrapper around Nominatim (OpenStreetMap).

Used by ``GET /api/rides`` to resolve a ``?near=`` place name into
``(lat, lon)`` so the bounding-box + Haversine filter can run.

Nominatim usage policy
----------------------
* No more than 1 request per second from a single source.
* Requests must include a meaningful ``User-Agent`` (or ``Referer``) so
  abuse can be reported.

We comply by:
* In-process serialised single-call rate limiter (a ``threading.Lock`` plus
  a last-call timestamp). Concurrent requests from the FastAPI threadpool
  are queued one second apart.
* Per-process LRU+TTL cache so repeated lookups (e.g. "Santa Fe, NM" by
  multiple users) cost only one network call per TTL window.
* Module-level ``_HTTP_GET`` callable so tests can monkeypatch the HTTP
  layer rather than mocking ``urllib`` internals.

Concurrency note
----------------
``geocode_place`` is a synchronous, blocking call (network + sleep).
FastAPI runs synchronous endpoint handlers on its threadpool, so calling
this from the sync ``list_rides`` handler does *not* block the event loop
— no explicit ``asyncio.to_thread`` wrapper is required. If a future
refactor moves the handler to ``async def``, wrap calls with
``await asyncio.to_thread(geocode_place, q)``.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional

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
# Internal state
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_last_call_at: float = 0.0

# (cached_value, expires_at) — a plain dict keeps ordering for LRU eviction.
_cache: dict[str, tuple[Optional[tuple[float, float]], float]] = {}
_cache_lock = threading.Lock()

# Hit counters (test hooks).
_cache_hits = 0
_cache_misses = 0


def _now() -> float:
    """Return the current monotonic-ish time. Patched by tests for fake clocks."""
    return time.time()


def _sleep(seconds: float) -> None:
    """Sleep wrapper that tests can patch to avoid real waits."""
    if seconds > 0:
        time.sleep(seconds)


def _default_http_get(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — known URL
        return resp.read().decode("utf-8")


# Tests monkeypatch this attribute to inject a fake HTTP layer.
_HTTP_GET: Callable[[str, float], str] = _default_http_get


def reset_state() -> None:
    """Clear the cache and rate limiter — for use in tests only."""
    global _last_call_at, _cache_hits, _cache_misses
    with _cache_lock:
        _cache.clear()
        _cache_hits = 0
        _cache_misses = 0
    with _rate_lock:
        _last_call_at = 0.0


def get_cache_stats() -> dict:
    """Snapshot of cache metrics for tests/observability."""
    return {
        "hits": _cache_hits,
        "misses": _cache_misses,
        "size": len(_cache),
    }


def _evict_if_full() -> None:
    """LRU-ish eviction: drop the oldest entry when the cache is full.

    Plain ``dict`` insertion order acts as our LRU proxy — refresh on hit
    by deleting and re-inserting (done in ``geocode_place``).
    """
    while len(_cache) > CACHE_MAX_ENTRIES:
        oldest_key = next(iter(_cache))
        del _cache[oldest_key]


def geocode_place(query: str) -> Optional[tuple[float, float]]:
    """Resolve ``query`` to ``(lat, lon)`` via Nominatim, or ``None``.

    Returns ``None`` for unresolvable queries. Raises on transport errors
    so the caller can decide between 400 (resolvable, but no match) and
    503 (geocoder unreachable).
    """
    global _last_call_at, _cache_hits, _cache_misses

    if not query:
        return None
    key = query.strip().lower()
    if not key:
        return None

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
            # Expired — fall through to refetch.
            del _cache[key]
        _cache_misses += 1

    # Rate-limit: serialise calls and ensure ≥ RATE_LIMIT_SECONDS between
    # consecutive Nominatim hits from this process.
    with _rate_lock:
        wait = RATE_LIMIT_SECONDS - (_now() - _last_call_at)
        if wait > 0:
            _sleep(wait)
        _last_call_at = _now()

    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": "1"})
    url = f"{NOMINATIM_URL}?{params}"
    raw = _HTTP_GET(url, TIMEOUT_SECONDS)
    try:
        results = json.loads(raw)
    except (ValueError, TypeError):
        results = []

    value: Optional[tuple[float, float]] = None
    if isinstance(results, list) and results:
        first = results[0]
        try:
            value = (float(first["lat"]), float(first["lon"]))
        except (KeyError, TypeError, ValueError):
            value = None

    with _cache_lock:
        _cache[key] = (value, _now() + CACHE_TTL_SECONDS)
        _evict_if_full()

    return value
