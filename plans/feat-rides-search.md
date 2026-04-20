# Feature Implementation Plan: Rides Search (Free-Text + Location Radius)

## Problem & Goal

The Rides screen (`frontend/src/pages/Rides.tsx`) currently lets the user filter the
activity history by a date range only. As ride history grows it becomes hard to find
"that gravel ride near Santa Fe" or "the ride I named Tuesday Threshold". We want to
add two complementary filters that **augment** (do not replace) the existing date
filter:

1. **Free-text search** over the ride's user-visible text fields (`title`,
   `post_ride_comments`, `coach_comments`).
2. **Advanced "near a place" search**: user types a place name and a radius
   (km/mi), and the list is restricted to rides whose start point falls inside the
   resulting bounding circle.

Both filters must compose with the existing `start_date` / `end_date` filter and
must be implementable as additive query params on the existing
`GET /api/rides` endpoint — no new endpoint, no breaking changes.

---

## Investigation Summary (already done — read-only)

**Frontend — date-filter precedent (`frontend/src/pages/Rides.tsx`):**
- Local `useState` for `startDate` / `endDate` (lines 79-80).
- Separate `filterParams` state object that is *only* updated when the "Go" button
  is clicked (`handleFilter`, lines 136-141). `useRides(filterParams)` re-fetches
  on change.
- Filter UI lives in a single rounded toolbar to the right of the H1 (lines 580-605).
  Mobile: same toolbar, inputs shrink. There is no separate "advanced" panel today.
- The page already uses Nominatim **client-side** for *reverse* geocoding the
  selected ride's start GPS to a city name (lines 177-194). This is a useful
  precedent for the geocoding strategy and rate-limit etiquette.

**Frontend API client (`frontend/src/lib/api.ts`):**
- `fetchRides({ start_date, end_date, sport, limit })` builds query string and
  calls `GET /api/rides`. New params would be added here (lines 73-80).
- `useRides` (`frontend/src/hooks/useApi.ts:6`) is a thin React-Query wrapper.

**Backend — list endpoint (`server/routers/rides.py:25-54`):**
- `GET /api/rides` accepts `start_date`, `end_date`, `sport`, `limit` (default 500).
- **Not paginated** — returns up to `limit` rows ordered by `start_time DESC`.
  No offset or cursor. We will keep this for v1 and only revisit if the result
  set is large.
- Built with parameterized SQL using `?` placeholders against `get_db()` (the
  project's psycopg2 wrapper that translates `?` → `%s`).

**Backend — schema (`migrations/0001_baseline.sql`):**
- `rides` table already has `start_lat REAL`, `start_lon REAL` (lines 45-46).
- **No** PostGIS extension installed; no spatial index.
- Searchable text columns on `rides`: `title`, `post_ride_comments`,
  `coach_comments`, `filename`. There is no `description` column — ride text
  comes from the user-edited `title`/`post_ride_comments` and the agent-written
  `coach_comments`. There is no separate "notes" column on rides.

**Geo-data population — important data gap:**
- `server/ingest.py` (FIT-file path): writes `start_lat` / `start_lon` from
  `session.start_position_lat`/`long` (lines 192-193, 224-225). Populated.
- `server/services/intervals_icu.py` (ICU sync path, line 356-357): explicitly
  sets `"start_lat": None, "start_lon": None`. **Not populated.**
- However, the same module already pulls per-second `latlng` streams into
  `ride_records` (line 200, `params = {"types": "...latlng"}`), so geo data
  exists per-record but not at the ride level for ICU-sourced rides.
- **Consequence:** depending on how the user ingests rides, a non-trivial
  fraction of historical `rides` rows may have `start_lat IS NULL`. Phase 2
  must handle this and ship a backfill.

**Existing geo-radius prior art (`server/routers/analysis.py:217-253`):**
- `/api/analysis/route-matches` already does an `ABS(start_lat - ?) < 0.01 AND
  ABS(start_lon - ?) < 0.01` bounding-box filter. This is a "fast box prefilter"
  pattern we will mirror, then refine with a Haversine post-filter for true
  great-circle distance.

**Test infra:**
- Unit tests live in `tests/unit/` (no DB, fast). The query-builder for the new
  filters should be unit-testable as a pure function.
- Integration tests live in `tests/integration/`, run via
  `./scripts/run_integration_tests.sh` against a Postgres container on **port
  5433**. Seed data is loaded from `tests/integration/seed/seed_data.json.gz`
  and the seed generator (`generate_recent.py:136`) already populates
  `start_lat`/`start_lon` in a small lat/lon box.
- E2E tests use Playwright in `tests/e2e/` — `03-rides.spec.ts` is the file to
  extend.

---

## Phasing

This work is split into **two separable phases** because they have very
different complexity, risk profiles, and data prerequisites. Phase 1 ships
useful value on its own and de-risks the API/UX shape before tackling geo.

| Phase | Scope | Migrations | External services |
| --- | --- | --- | --- |
| **Phase 1** | Free-text search (`?q=`) | None | None |
| **Phase 2** | Location radius (`?near=...&radius_km=...`) | One migration: index on `start_lat`; backfill script for ICU rides | Nominatim geocoder (server-side, cached) |

Phase 2 should not start until Phase 1 has shipped and the data-gap question
(ICU rides missing geo) is resolved.

---

## API Design

Add four optional query params to `GET /api/rides`. All are additive; absent
params behave exactly as today.

| Param | Type | Phase | Meaning |
| --- | --- | --- | --- |
| `q` | `string` | 1 | Free-text needle. Case-insensitive substring match against `title`, `post_ride_comments`, `coach_comments`. Multiple words are AND-ed (each word must appear somewhere across the searched columns). Whitespace-trimmed; empty string is ignored. |
| `near` | `string` | 2 | A place name to be geocoded server-side (e.g. `"Santa Fe, NM"`). The server resolves it to (lat, lon) via Nominatim and caches the result. |
| `near_lat`, `near_lon` | `float` | 2 | Pre-resolved coordinates. If both are supplied they take precedence over `near` (lets the frontend cache Nominatim results client-side, matching the existing reverse-geocoding pattern). |
| `radius_km` | `float` | 2 | Required when `near` or `near_lat`/`near_lon` is supplied. Range `[0.1, 500]`. Defaults to `25` if omitted but a `near*` param is present. |

Error semantics:
- `radius_km` without any `near*` → `400` "radius_km requires near or near_lat/near_lon".
- `near` that geocoder cannot resolve → `400` "could not resolve location 'X'".
- `near` + geocoder timeout → `503` "geocoding service unavailable, please try again".

Response shape is unchanged — still `list[RideSummary]`. Rides without
`start_lat`/`start_lon` are silently excluded when a geo filter is active
(documented in the OpenAPI summary so the UI can warn).

---

## Affected Files

### Phase 1 (free-text)
**Backend**
- `server/routers/rides.py` — extend `list_rides()` signature + SQL.
- `server/models/schemas.py` — no changes (response shape unchanged).
- `tests/unit/test_rides_search.py` — **new** — unit tests for the pure query-builder helper.
- `tests/integration/test_api.py` — extend to cover `?q=` against seeded rides.
- `tests/e2e/03-rides.spec.ts` — extend with a search-box test.

**Frontend**
- `frontend/src/lib/api.ts` — add `q` to `fetchRides` params.
- `frontend/src/pages/Rides.tsx` — add search input + state plumbing.

**Refactor candidate (optional):**
- Extract the SQL-WHERE composition out of `list_rides()` into a small pure
  helper `_build_rides_filter(...)` in the same file so the unit test does not
  need a DB.

### Phase 2 (radius)
**Backend**
- `server/routers/rides.py` — extend `list_rides()` further; add Haversine
  post-filter helper.
- `server/services/geocoding.py` — **new** — thin Nominatim wrapper with
  in-process LRU cache (TTL 24h) and a 1-req/sec rate limiter (Nominatim
  policy). Falls back to a stub in tests.
- `server/services/intervals_icu.py` — populate `start_lat`/`start_lon` from
  the `start_latlng` field in the activity payload (currently hard-coded to
  `None` on line 356-357).
- `migrations/0008_rides_start_lat_lon_index.sql` — **new** — partial B-tree
  index `CREATE INDEX IF NOT EXISTS idx_rides_start_lat_lon ON rides (start_lat, start_lon) WHERE start_lat IS NOT NULL;`
- `scripts/backfill_ride_start_geo.py` — **new** — idempotent script that
  walks every ride with `start_lat IS NULL`, looks at its first non-null
  `ride_records` row, and writes that lat/lon up to the parent ride. Designed
  to be safe to re-run.
- `tests/unit/test_haversine.py` — **new** — unit test for the distance helper.
- `tests/unit/test_geocoding_cache.py` — **new** — unit test for the cache and
  rate-limiter (with mocked HTTP).
- `tests/integration/test_api.py` — extend to cover `?near_lat=&near_lon=&radius_km=`.

**Frontend**
- `frontend/src/lib/api.ts` — add `near` / `near_lat` / `near_lon` /
  `radius_km` to `fetchRides` params.
- `frontend/src/pages/Rides.tsx` — add an "Advanced" disclosure panel below
  the existing toolbar containing the place + radius inputs.

---

## Implementation Steps

### Prerequisites
- Local Podman Postgres running (`podman run -d --name coach-db -p 5432:5432
  -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:16-alpine`).
- `source venv/bin/activate` then `pip install -r requirements.txt`.
- `cd frontend && npm install`.
- Verify `DATABASE_URL` points to localhost before running anything that
  writes (per AGENTS.md mandate).

---

### PHASE 1 — Free-text search

#### Step 1.A — Characterise current `/api/rides` behaviour (Safety Harness)
*Target file:* `tests/integration/test_api.py` (existing).
*Action:* Before changing any code, add **golden tests** that lock in current
behaviour:
- `GET /api/rides` returns the seeded rides count and is ordered by
  `start_time DESC`.
- `GET /api/rides?start_date=...&end_date=...` filters correctly (this proves
  our future composition with `q` won't break date filtering).
- `GET /api/rides?sport=Ride` filters correctly.

*Verification:*
```bash
./scripts/run_integration_tests.sh tests/integration/test_api.py -v -k rides
```
All assertions must pass before touching `rides.py`.

#### Step 1.B — Extract a pure query-builder helper (Refactor under harness)
*Target file:* `server/routers/rides.py`.
*Change:* Refactor the body of `list_rides()` (lines 35-50) so the
SQL/params construction lives in a private pure function:

```python
def _build_rides_query(
    *, tz_name: str,
    start_date: str | None, end_date: str | None,
    sport: str | None, q: str | None,
    limit: int,
) -> tuple[str, list]:
    """Return (sql, params). Pure — no DB access, no FastAPI deps."""
```
The function returns the same SQL the endpoint produces today (with `q=None`
yielding *exactly* the current SQL — verified by tests in 1.A).

*Verification:* Re-run the harness from 1.A. No behaviour change yet.

#### Step 1.C — Unit tests for the helper
*Target file:* `tests/unit/test_rides_search.py` (new).
*Test cases:*
- `q=None` produces SQL with no `q`-related clause and no extra params.
- `q="threshold"` adds `(LOWER(title) LIKE %s OR LOWER(post_ride_comments) LIKE %s OR LOWER(coach_comments) LIKE %s)` to the WHERE clause and appends `%threshold%` three times to params.
- `q="hard climb"` (two words) ANDs the per-word clause: each word becomes one parenthesised OR-group, ANDed together.
- `q="   "` (whitespace) is treated as `None`.
- `q` plus `start_date` produces both clauses, params in the correct order.
- `q` is lowercased before being placed in `LIKE` params (case-insensitive).

*Verification:*
```bash
source venv/bin/activate && pytest tests/unit/test_rides_search.py -v
```

#### Step 1.D — Wire `q` into the endpoint
*Target file:* `server/routers/rides.py`.
*Change:*
- Add `q: Optional[str] = Query(None)` to `list_rides()`.
- Call `_build_rides_query(..., q=q, ...)` instead of inline SQL building.
- Trim/lowercase `q` once at the top of the helper so the SQL is always
  case-insensitive.

*Verification:*
```bash
./scripts/run_integration_tests.sh tests/integration/test_api.py -v
```
Existing tests must still pass.

#### Step 1.E — Integration tests for `?q=`
*Target file:* `tests/integration/test_api.py`.
*Test cases (against the seeded test DB):*
- `GET /api/rides?q=<seeded title substring>` returns at least one ride and
  none of the returned rides has all three text columns lacking the substring.
- `GET /api/rides?q=zzznotatitleanywhere` returns `[]`.
- `GET /api/rides?q=<word>&start_date=2026-01-01&end_date=2026-12-31` composes
  correctly (count ≤ pure date-filter count, ≥ pure-q count limited to range).
- `GET /api/rides?q=THRESHOLD` returns the same set as `q=threshold`
  (case-insensitive).

*Verification:*
```bash
./scripts/run_integration_tests.sh tests/integration/test_api.py -v -k rides
```

#### Step 1.F — Frontend API client
*Target file:* `frontend/src/lib/api.ts`.
*Change:* Add `q?: string` to the `fetchRides` params type and append it to
the `URLSearchParams` if non-empty (mirror existing pattern lines 73-80).

#### Step 1.G — Frontend search input
*Target file:* `frontend/src/pages/Rides.tsx`.
*Change:*
1. Add `const [searchText, setSearchText] = useState('')` next to the
   existing `startDate`/`endDate` state (line ~79).
2. Extend the `filterParams` state type to include `q?: string`.
3. Update `handleFilter()` (line 136) to include `q: searchText.trim() ||
   undefined`.
4. Add a search input to the filter toolbar (lines 580-605). Place it to the
   left of the date inputs, separated by the existing divider style. Use a
   `Search` lucide icon. Placeholder: `"Search by name or notes..."`.
5. Pressing **Enter** in the input should call `handleFilter()` (parity with
   the date-filter "Go" button — do not auto-fire on every keystroke; this
   matches the established pattern of explicit submit).
6. If `filterParams.q` is non-empty after fetching and `rides` is empty, the
   existing "No rides match your filters" empty state already handles this —
   no new empty-state copy needed.

*Verification:*
- `cd frontend && npm run build` — no TS errors.
- Manual smoke: `./scripts/dev.sh`, navigate to Rides, type a known title
  substring, press Enter, see filtered list.

#### Step 1.H — E2E test
*Target file:* `tests/e2e/03-rides.spec.ts`.
*Test case:*
```
test('search box filters rides by title', ...)
```
Type a substring known to exist in seeded data, press Enter, assert row count
decreased OR "No rides match" appears.

*Verification:* `./scripts/run_e2e_tests.sh -g "search"`.

#### Phase 1 Definition of Done
- All unit + integration + E2E tests green.
- `GET /api/rides?q=foo` returns case-insensitive substring matches across
  `title`, `post_ride_comments`, `coach_comments`.
- The existing date filter and the new `?q=` filter compose without surprise.
- The Rides page UI has a working search box that visually matches the
  existing toolbar style.

---

### PHASE 2 — Location radius

> **Blocking discovery — read first.** A subset of `rides` rows have
> `start_lat IS NULL` because intervals.icu sync does not populate the ride-
> level coordinates (`server/services/intervals_icu.py:356-357`). Per-second
> coords *do* exist in `ride_records` for those same rides. Phase 2 therefore
> requires an ingest fix **and** a one-time backfill before the UX is honest.
> Without these, the new radius filter will silently drop most of the user's
> ICU-synced history.

#### Step 2.A — Fix forward: populate `start_lat/lon` on ICU sync
*Target file:* `server/services/intervals_icu.py`.
*Change:*
- Inspect the activity payload returned by intervals.icu — the activity
  resource exposes `start_latlng` (a 2-element list) on activities that have
  GPS. Replace the hard-coded `None`s on lines 356-357 with:
  ```python
  latlng = activity.get("start_latlng") or []
  "start_lat": latlng[0] if len(latlng) >= 2 else None,
  "start_lon": latlng[1] if len(latlng) >= 2 else None,
  ```
- Confirm the field name by looking at `tests/integration/test_sync.py` and
  any intervals.icu fixture JSON in the repo before committing — if the field
  is named differently in our actual payload (e.g. `latlng` or
  `start_latitude/start_longitude`), use the real one. Do **not** guess.

*Verification:*
- Add unit test in `tests/unit/test_intervals_icu_metrics.py`: build a fake
  activity dict with `start_latlng=[35.69, -105.94]`, call the ride-builder,
  assert `start_lat == 35.69` and `start_lon == -105.94`.
- Add unit test for missing/empty `start_latlng` → both `None`.

#### Step 2.B — Backfill historical ICU rides
*Target file:* `scripts/backfill_ride_start_geo.py` (new).
*Logic:*
```python
# For each ride where start_lat IS NULL:
#   SELECT lat, lon FROM ride_records
#     WHERE ride_id = ? AND lat IS NOT NULL AND lon IS NOT NULL
#     ORDER BY id LIMIT 1
#   if found: UPDATE rides SET start_lat=?, start_lon=? WHERE id=?
# Print counts: scanned, backfilled, no_records.
```
- Idempotent: re-running is a no-op.
- Per project mandate: the script must `print` the resolved `DATABASE_URL`
  and refuse to run unless it points to localhost OR the user passes
  `--allow-remote`.

*Verification:*
- Unit test in `tests/unit/test_backfill_geo.py` with a mocked DB connection
  asserting the SQL is correct and that rides with no lat/lon records are
  left untouched.
- Manual run against local Podman DB; rerun should report `backfilled=0`.

#### Step 2.C — Add the spatial-ish index
*Target file:* `migrations/0008_rides_start_lat_lon_index.sql` (new).
*Contents:*
```sql
-- 0008_rides_start_lat_lon_index.sql
-- Composite index to speed up bounding-box prefilters used by the
-- "rides near a place" search and the existing /api/analysis/route-matches.
CREATE INDEX IF NOT EXISTS idx_rides_start_lat_lon
    ON rides (start_lat, start_lon)
    WHERE start_lat IS NOT NULL;
```
- We deliberately do **not** introduce PostGIS for v1: the dataset is small
  (single-athlete, low thousands of rides), Haversine in SQL with a bounding-
  box prefilter is plenty fast, and skipping PostGIS keeps Cloud Run startup
  and Podman dev simple.

*Verification:*
- `python -m server.migrate` applies cleanly against local DB.
- `\d+ rides` shows the new index.
- Re-run does not error (idempotent).

#### Step 2.D — Geocoding service module
*Target file:* `server/services/geocoding.py` (new).
*Design:*
- Single function: `def geocode_place(query: str) -> tuple[float, float] | None`.
- Calls Nominatim: `https://nominatim.openstreetmap.org/search?q=...&format=json&limit=1`.
- **Required headers:** `User-Agent: cycling-coach/<version> (+contact)` —
  Nominatim's usage policy forbids anonymous requests.
- **Rate limit:** Nominatim allows ≤1 req/sec. Use a simple in-process
  threading lock + last-call timestamp; sleep if needed before the next call.
- **Cache:** in-process `functools.lru_cache(maxsize=512)` plus a manual
  TTL wrapper (24h). Cache hit count exposed via a module-level counter for
  test assertions.
- **Tests:** never hit the real Nominatim. Inject the HTTP client via a
  module-level `_http_get` callable that tests can monkeypatch.

*Tradeoff note (decision recorded):*
- **Server-side Nominatim** chosen over **client-side Browser Geolocation
  API** because:
  - The user is typing a *place name*, not asking for "my current location".
    The Browser Geolocation API only resolves the user's device location.
  - Server-side caching means the same "Santa Fe, NM" query across users
    costs us one Nominatim call.
  - Avoids exposing a second domain to the SPA's CSP.
  - The frontend already calls Nominatim directly for *reverse* geocoding on
    the ride-detail page — moving forward geocoding to the server is a step
    toward consolidating that traffic and respecting Nominatim's etiquette.
- **Tradeoff:** introduces a new external dependency on the request path. We
  mitigate via cache + hard timeout (5s) + graceful 503 + the `near_lat`/
  `near_lon` escape hatch that lets the frontend bypass the server geocoder
  if/when we want to.
- **Future option:** if the user requests heavier geo features, swap in a
  paid geocoder (Mapbox, Google) behind the same `geocode_place()` interface.

#### Step 2.E — Haversine helper + query-builder extension
*Target file:* `server/routers/rides.py`.
*Change:*
- Extend `_build_rides_query()` from Phase 1 to optionally accept
  `near: tuple[float, float] | None` and `radius_km: float | None`.
- When supplied, add a **bounding-box prefilter** to the SQL (uses the new
  index): `start_lat BETWEEN ? AND ? AND start_lon BETWEEN ? AND ?`. The
  bounding box is computed as `radius_km / 111.32` for latitude and
  `radius_km / (111.32 * cos(lat_rad))` for longitude.
- Apply the **exact Haversine post-filter in Python** on the rows returned
  from the bounding box. This keeps the SQL portable (no PostGIS, no `EARTH_DISTANCE`).

```python
from math import radians, sin, cos, asin, sqrt

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))
```

#### Step 2.F — Wire `near` / `near_lat` / `near_lon` / `radius_km` into the endpoint
*Target file:* `server/routers/rides.py`.
*Change:*
- Add the four query params to the `list_rides()` signature.
- Validation:
  - `radius_km` requires at least one of `near` / (`near_lat` AND `near_lon`)
    → 400.
  - If `near` supplied and no `near_lat`/`near_lon`, call
    `geocoding.geocode_place(near)`. On `None` → 400. On exception → 503.
- Pass the resolved tuple + radius into `_build_rides_query()`.
- After SQL fetch, run the Haversine post-filter.

#### Step 2.G — Unit tests
*Target file:* `tests/unit/test_haversine.py` (new).
- Known city-pair distances within 1% (e.g. Santa Fe NM → Albuquerque NM
  ≈ 88 km).
- A point on top of itself returns 0.
- Antipodal points return ≈ 20015 km.

*Target file:* `tests/unit/test_geocoding_cache.py` (new).
- First call invokes the HTTP layer; second identical call does not (cache
  hit counter increments).
- Rate limiter sleeps if the previous call was <1s ago (use a fake clock).
- Cache entry expires after the configured TTL (use a fake clock).

*Target file:* `tests/unit/test_rides_search.py` (extend).
- `_build_rides_query(near=(35.69, -105.94), radius_km=25)` adds the four
  bounding-box bind params in the correct order.
- Bounding box width matches the documented `radius_km / 111.32` formula.

*Verification:*
```bash
source venv/bin/activate && pytest tests/unit -v
```

#### Step 2.H — Integration tests
*Target file:* `tests/integration/test_api.py`.
*Test cases (the seed generator already places rides in a small lat/lon box
near 44.16, 0.0; tests should anchor to whatever the seed actually uses):*
- `GET /api/rides?near_lat=44.166&near_lon=0.0&radius_km=10` returns at
  least one seeded ride.
- `GET /api/rides?near_lat=0.0&near_lon=0.0&radius_km=1` returns `[]`
  (nothing in the seed near (0,0)).
- `GET /api/rides?radius_km=10` (no `near*`) → 400.
- `GET /api/rides?near_lat=44.166&near_lon=0.0&radius_km=10000` returns
  every seeded ride that has GPS (sanity).
- `GET /api/rides?near_lat=44.166&near_lon=0.0&radius_km=10&q=<seeded
  word>&start_date=2026-01-01&end_date=2026-12-31` composes all three
  filters.

*Verification:* `./scripts/run_integration_tests.sh tests/integration/test_api.py -v`.

#### Step 2.I — Frontend API client
*Target file:* `frontend/src/lib/api.ts`.
*Change:* Extend `fetchRides` params type with `near?: string`, `near_lat?:
number`, `near_lon?: number`, `radius_km?: number` and append them to the
query string.

#### Step 2.J — Frontend "Advanced" UI
*Target file:* `frontend/src/pages/Rides.tsx`.
*Change:*
1. Add an "Advanced" toggle button (chevron) at the right end of the
   existing filter toolbar. When clicked, expand a second row beneath the
   toolbar containing:
   - Place input (text), placeholder `"e.g. Santa Fe, NM"`.
   - Radius input (number), default `25`, with a unit selector (`km` / `mi`)
     that respects the existing `useUnits()` hook.
   - A small "Use my current location" button (browser geolocation) that
     fills in `near_lat`/`near_lon` directly. Optional — gated behind the
     existing pattern of feature flags if any.
2. Plumb new state: `searchPlace`, `radiusValue`. Convert miles→km before
   sending if needed.
3. `handleFilter()` includes the geo params iff `searchPlace.trim() !== ''`
   (or geolocation has populated `near_lat`/`near_lon`).
4. When the geo filter is active, render a small chip below the toolbar:
   `"Showing rides within X km of <resolved place>"`. If the API returns 400,
   surface the error inline (use the existing toast/error pattern if one
   exists, otherwise render below the input in red).

#### Step 2.K — E2E test
*Target file:* `tests/e2e/03-rides.spec.ts`.
- Open Advanced panel.
- Fill place + radius (use a known seed lat/lon expressed as a place — or use
  the `near_lat`/`near_lon` escape hatch by populating the inputs via
  `page.evaluate` to bypass Nominatim in CI).
- Click Go, assert filtered count.

*Verification:* `./scripts/run_e2e_tests.sh -g "near"`.

#### Phase 2 Definition of Done
- ICU rides ingested **after** Step 2.A have `start_lat`/`start_lon`
  populated.
- Backfill script has been run once against the local DB and reports a
  no-op on second run.
- Migration `0008` applied, index visible.
- `GET /api/rides?near=Santa+Fe%2C+NM&radius_km=50` works end-to-end.
- The Advanced panel on the Rides screen returns sensible results for at
  least three known places.

---

## Test Plan Summary

| Layer | What we test | Where |
| --- | --- | --- |
| Unit | Pure query-builder (`_build_rides_query`) — every param combination | `tests/unit/test_rides_search.py` |
| Unit | Haversine distance helper | `tests/unit/test_haversine.py` |
| Unit | Geocoding cache + rate limiter (mocked HTTP) | `tests/unit/test_geocoding_cache.py` |
| Unit | ICU ride builder populates `start_lat`/`start_lon` | `tests/unit/test_intervals_icu_metrics.py` |
| Unit | Backfill script SQL (mocked DB) | `tests/unit/test_backfill_geo.py` |
| Integration | `/api/rides?q=` composes with date and sport filters | `tests/integration/test_api.py` |
| Integration | `/api/rides?near_lat=&near_lon=&radius_km=` | `tests/integration/test_api.py` |
| E2E | Search box filters list | `tests/e2e/03-rides.spec.ts` |
| E2E | Advanced panel filters list | `tests/e2e/03-rides.spec.ts` |
| Manual | Re-run backfill is a no-op | local Podman |

---

## Out of Scope

- Searching across **planned-workout** notes (`planned_workouts.coach_notes`,
  `athlete_notes`) — separate domain, separate endpoint.
- Searching **chat history** (`chat_events.content_text`) — different access
  patterns; would warrant FTS/`tsvector`.
- Postgres full-text search (`to_tsvector` / GIN). Substring `LIKE` is
  sufficient for the current dataset size and avoids a migration. Revisit if
  rides corpus grows past ~50k rows or users complain about ranking.
- Map-pin UI on the rides list. The radius filter is text-input only in v1.
- Drawing the search radius on the existing rides timeline / heatmap.
- Searching across **route geometry** (entire route within radius), not just
  start point. v1 only filters by start point. Some commuters' "out and back"
  rides will be correctly captured; long point-to-point rides ending far
  away will *not* be excluded.
- Pagination of the rides list. The current 500-row cap stays.

---

## Open Questions (need user input before Phase 1 starts)

1. **Should free-text search also match `coach_comments`?** It contains AI-
   generated coaching markdown; matches there may surprise users who think
   they're searching their own text. Plan currently includes it — confirm or
   exclude.
2. **Should free-text search match `filename`?** Useful for power users
   ("icu_12345"), noisy for everyone else. Plan currently excludes it.
3. **Default unit for radius (km vs mi)?** Plan defers to the existing
   `useUnits()` hook. Confirm that hook covers this.
4. **Acceptable to send Nominatim queries from our Cloud Run backend?**
   Nominatim's policy requires a contact email in the User-Agent and ≤1
   req/sec. We will comply; just confirming the user is OK with this rather
   than provisioning a paid geocoder.
5. **Backfill blast radius:** running `scripts/backfill_ride_start_geo.py`
   against production will UPDATE potentially many rows. Confirm the user
   wants this run, and whether they want a dry-run mode first
   (`--dry-run` is easy to add).
6. **What does the user expect when a ride has no GPS?** Currently the plan
   silently excludes it from radius results. Alternative: include with a
   visual marker. Confirm.

---

## Branch Name Suggestion

`feat/rides-search`

(Phase 2 can land on the same branch with a second PR — or split into
`feat/rides-search-text` and `feat/rides-search-near` if the user prefers
two PRs.)

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| ICU-synced rides have no ride-level GPS → empty results | High | Step 2.A fixes ingest going forward; Step 2.B backfills history. |
| Nominatim rate-limits or blocks our IP | Medium | In-process cache + 1 req/sec limiter + proper User-Agent + `near_lat`/`near_lon` client-bypass param. |
| Substring `LIKE` is slow on large `post_ride_comments`/`coach_comments` | Low (single-athlete dataset) | Defer FTS until measured. The query already has a `start_time DESC LIMIT 500` ceiling. |
| Refactor of `list_rides()` regresses the existing date filter | Low | Step 1.A locks behaviour with golden tests *before* refactoring (Step 1.B). |
| Backfill mis-runs against prod | Medium | Script refuses to run without localhost or `--allow-remote`; AGENTS.md mandate enforced in code. |
