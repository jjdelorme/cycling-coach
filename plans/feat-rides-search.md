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
- `ride_records` table has per-record `lat REAL`, `lon REAL` (lines 63-64).
- **No** PostGIS extension installed; no spatial index.
- Searchable text columns on `rides`: `title`, `post_ride_comments`,
  `coach_comments`, `filename`. There is no `description` column — ride text
  comes from the user-edited `title`/`post_ride_comments` and the agent-written
  `coach_comments`. There is no separate "notes" column on rides.

**Geo-data population — current state (re-investigated 2026-04-20, second pass):**

The first investigation pass concluded "the orchestrator already populates
`start_lat`/`start_lon` for new ICU rides; only historical rides need a
backfill." **That conclusion was wrong.** A live probe against the Neon dev DB
revealed an outdoor ride from 2026-04-04 (id 3233, "Natick Road Cycling",
filename `icu_i137210941`) with 10,892 stream records but **zero**
`ride_records.lat`/`lon` populated and `rides.start_lat IS NULL`. Root cause:

- `fetch_activity_streams()` returns `latlng` as a **flat array of alternating
  floats** (`[lat, lon, lat, lon, ...]`), not as nested `[lat, lon]` pairs.
- Both consumers handle only the pair format:
  - `server/services/sync.py:274` in `_store_streams` —
    `isinstance(latlng_raw[0], (list, tuple))` is False for a float, so
    `latlng_pairs` stays empty and every record is written with
    `lat=None, lon=None`.
  - `server/services/sync.py:320` in `_backfill_start_location` — same check,
    same silent skip.
- The inline comment at `sync.py:271` literally says "intervals.icu may return
  [lat, lng] pairs or flat values" — the author anticipated the flat case but
  only implemented the pair case. Either ICU changed payload format or this
  was always half-broken.

**Consequences:**
1. Every outdoor ICU-synced ride has `rides.start_lat IS NULL` AND
   `ride_records.lat/lon` empty. The Ride Details page's city/state label is
   therefore missing for *every* outdoor ICU ride, not just historical ones.
2. The original Phase 1 plan (pure-DB backfill from `ride_records`) **cannot
   work** because the source data isn't there either. We need to re-fetch
   streams from ICU.
3. The remaining FIT-ingested rides (`server/ingest.py:192-193`) DO have
   `start_lat`/`start_lon` correctly — those go through `fitparse`, not the
   ICU stream parser. That's why the city label appears for *some* rides.

**Other call sites for the broken pattern** (need the same fix or to be
verified):
- `server/services/sync.py:515` (bulk sync) — ICU path
- `server/services/single_sync.py:93` (single re-sync) — ICU path
- `scripts/backfill_icu_streams.py:64` — uses the same broken helpers
- `scripts/repair_missing_data.py:99` — same

**Ride-detail city/state display — not a frontend regression:**
- `frontend/src/pages/Rides.tsx:178-194` reverse-geocodes
  `ride.start_lat`/`ride.start_lon` via Nominatim. When NULL it silently shows
  nothing. No frontend change needed once the backend data is right.

**Existing backfill prior art (need fixing alongside the parser):**
- `scripts/backfill_icu_streams.py` — calls the broken `_backfill_start_location`
  via the broken `_extract_streams` interpretation. Will work correctly after
  the parser fix.
- `scripts/repair_missing_data.py` — same. Will work after the parser fix.
- **Once the parser is fixed**, re-running either script (or a new
  narrowly-scoped `scripts/backfill_ride_start_geo.py`) will populate
  `rides.start_lat/lon` for every historical outdoor ICU ride.

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

This work is split into **three separable phases**. Phase 1 is now a code-bug
fix + targeted backfill (not a pure-DB backfill — see investigation above) and
delivers immediate user-visible value: city/state labels reappear on Ride
Details for outdoor ICU rides. It is also a hard prerequisite for the radius
filter.

| Phase | Scope | Migrations | External services |
| --- | --- | --- | --- |
| **Phase 1** | (a) Fix the `latlng` flat-array parser in `server/services/sync.py`. (b) Backfill `rides.start_lat`/`start_lon` for every ICU ride with `start_lat IS NULL` by re-fetching streams (one ICU API call per affected ride). | None (data + code) | intervals.icu (read-only, rate-limited) |
| **Phase 2** | Free-text search (`?q=`) | None | None |
| **Phase 3** | Location radius (`?near=...&radius_km=...`) | One migration: partial index on `(start_lat, start_lon)` | Nominatim geocoder (server-side, cached) |

- Phase 1 ships independently and is the highest-leverage piece of this whole
  plan: it both fixes the visible bug (missing city names) AND removes the
  blocking discovery flagged in old Phase 2 AND prevents *future* outdoor ICU
  rides from regressing.
- Phase 2 (free-text) is unblocked as soon as Phase 1 is verified.
- Phase 3 should not start until Phase 1 has been run against the Neon dev
  DB and the audit query confirms remaining `start_lat IS NULL` rides are
  indoor/no-GPS only.

**Note on `ride_records.lat/lon`:** Phase 1 deliberately does **not**
re-populate per-record GPS in `ride_records` for historical rides. That would
require deleting and re-inserting ~10k rows per ride, multiplied by every
affected ride. The current downstream features (ride-detail city, future
radius search) only need `rides.start_lat/lon`. If a future feature needs
per-record GPS for historical rides (route geometry, heatmaps), do that
backfill in a separate phase against the same re-fetched streams.

**Worktree convention:** When this plan is implemented, do the work in a
dedicated git worktree (e.g. `worktrees/rides-search`) so the data-only
Phase 1 PR can land independently of the API/UX phases.

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

### Phase 1 (parser fix + ICU re-fetch backfill)
**Backend (code fix)**
- `server/services/sync.py` — fix `_extract_streams` / `_store_streams` /
  `_backfill_start_location` to handle the flat-array `latlng` format ICU
  actually returns. Extract a shared helper `_normalize_latlng_pairs(raw)` that
  accepts either `[(lat, lon), ...]` or `[lat, lon, lat, lon, ...]` and
  always returns `[(lat, lon), ...]`. Both consumers call it.
- `tests/unit/test_sync_streams.py` — **new** (or extend existing) — unit test
  the helper across three inputs: nested pairs, flat alternating floats,
  empty/None. Also test that `_backfill_start_location` skips `(0, 0)` and
  `None` entries.

**Backend / scripts (backfill)**
- `scripts/backfill_ride_start_geo.py` — **new** — for every ride with
  `start_lat IS NULL` AND `filename LIKE 'icu_%'`, calls
  `fetch_activity_streams(icu_id)` and runs the (now-fixed)
  `_backfill_start_location`. **Does not** rewrite `ride_records` — only
  updates `rides.start_lat/start_lon`. Idempotent. Prints
  `scanned/backfilled/no_streams/no_gps_in_streams/skipped_already_populated`
  counts. Refuses to run unless `DATABASE_URL` points to localhost or
  `--allow-remote` is passed (per AGENTS.md mandate). Supports `--dry-run`.
  Respects ICU's 1 req/sec courtesy rate (intervals.icu is more permissive
  than Nominatim, but be a good citizen).
- `tests/unit/test_backfill_ride_start_geo.py` — **new** — unit test against
  a mocked connection + monkeypatched `fetch_activity_streams`: asserts the
  ride-selection SQL, the localhost guard, and the no-op behaviour when the
  re-fetched streams have no GPS.
- `tests/integration/test_backfill_ride_start_geo.py` — **new** — seed three
  rides (one with NULL `start_lat`, one with NULL but no ICU id, one already
  populated), monkeypatch `fetch_activity_streams` to return a synthetic
  flat-array `latlng`, run the script, assert only the first ride was
  updated and the second/third were untouched.

**Note on existing scripts (will work after the parser fix):**
- `scripts/backfill_icu_streams.py` and `scripts/repair_missing_data.py` both
  call the broken helpers. After the Phase 1 parser fix they will produce
  correct results, but they scope-creep into power-bests / metrics recompute.
  The new `backfill_ride_start_geo.py` is intentionally narrow.

### Phase 2 (free-text search)
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

### Phase 3 (radius)
**Backend**
- `server/routers/rides.py` — extend `list_rides()` further; add Haversine
  post-filter helper.
- `server/services/geocoding.py` — **new** — thin Nominatim wrapper with
  in-process LRU cache (TTL 24h) and a 1-req/sec rate limiter (Nominatim
  policy). Falls back to a stub in tests.
- `migrations/0008_rides_start_lat_lon_index.sql` — **new** — partial B-tree
  index `CREATE INDEX IF NOT EXISTS idx_rides_start_lat_lon ON rides (start_lat, start_lon) WHERE start_lat IS NOT NULL;`
- `tests/unit/test_haversine.py` — **new** — unit test for the distance helper.
- `tests/unit/test_geocoding_cache.py` — **new** — unit test for the cache and
  rate-limiter (with mocked HTTP).
- `tests/integration/test_api.py` — extend to cover `?near_lat=&near_lon=&radius_km=`.

**Frontend**
- `frontend/src/lib/api.ts` — add `near` / `near_lat` / `near_lon` /
  `radius_km` to `fetchRides` params.
- `frontend/src/pages/Rides.tsx` — add an "Advanced" disclosure panel below
  the existing toolbar containing the place + radius inputs.

**Removed from old plan:**
- ~~`server/services/intervals_icu.py` — populate `start_lat`/`start_lon` from
  the `start_latlng` field~~ — the orchestrator already calls
  `_backfill_start_location` in both sync paths. The actual problem is the
  `latlng` flat-array parser in `server/services/sync.py` (now Phase 1.B).
- ~~`scripts/backfill_ride_start_geo.py` as a pure-DB backfill from
  `ride_records`~~ — `ride_records.lat/lon` are also empty due to the same
  parser bug. Phase 1 now re-fetches streams from ICU instead.

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

### PHASE 1 — Fix `latlng` parser + backfill `start_lat`/`start_lon`

> **Why this is Phase 1 now.** The `latlng` parser in
> `server/services/sync.py` only handles the nested-pair format (`[[lat,lon],
> …]`) but intervals.icu returns a flat array of alternating floats
> (`[lat, lon, lat, lon, …]`). This silently drops every GPS point — so
> `ride_records.lat/lon` are NULL for every ICU ride AND `rides.start_lat/lon`
> are never populated. The Ride Details city/state label is therefore missing
> for every outdoor ICU-synced ride.
>
> The fix has two parts:
> 1. **Code fix** — teach the parser to handle the flat format so new syncs
>    work going forward.
> 2. **Backfill** — for existing rides, re-fetch the `latlng` stream from ICU
>    and populate `rides.start_lat/lon`. (A pure-DB backfill from
>    `ride_records` is **not possible** because `ride_records.lat/lon` are also
>    empty due to the same parser bug.)

#### Step 1.A — Audit the gap (read-only)
*Goal:* Quantify how many rides need backfilling.
*Action:* Run against the Neon dev DB (read-only):

```sql
-- Total rides missing start_lat
SELECT count(*) AS missing FROM rides WHERE start_lat IS NULL;

-- Of those, how many are ICU-sourced outdoor rides (likely have GPS)?
SELECT count(*) AS icu_missing
FROM rides WHERE start_lat IS NULL AND filename LIKE 'icu_%';

-- Of those, how many have ride_records at all (streams were fetched)?
SELECT count(DISTINCT r.id) AS has_records
FROM rides r
JOIN ride_records rr ON rr.ride_id = r.id
WHERE r.start_lat IS NULL AND r.filename LIKE 'icu_%';

-- How many rides already have start_lat (FIT-ingested)?
SELECT count(*) AS populated FROM rides WHERE start_lat IS NOT NULL;
```

Record the numbers in the PR description so the blast radius is clear.

#### Step 1.B — Fix the `latlng` parser
*Target file:* `server/services/sync.py`.
*Change:* Extract a shared helper that normalises the `latlng` stream:

```python
def _normalize_latlng(raw: list) -> list[tuple[float, float]]:
    """Convert ICU latlng data to [(lat, lon), ...].

    ICU returns EITHER nested pairs [[lat,lon], ...] OR a flat array
    [lat, lon, lat, lon, ...]. Handle both.
    """
    if not raw:
        return []
    if isinstance(raw[0], (list, tuple)):
        return [(p[0], p[1]) for p in raw if p and len(p) >= 2]
    # Flat alternating floats
    return [(raw[i], raw[i + 1]) for i in range(0, len(raw) - 1, 2)]
```

Update both consumers:
1. `_store_streams` (line ~269-275): replace the inline pair-detection with
   `latlng_pairs = _normalize_latlng(latlng_raw)`.
2. `_backfill_start_location` (line ~314-322): same — iterate
   `_normalize_latlng(latlng_raw)` instead of the raw list.

*Why fix `_store_streams` too?* Without it, future ride-records are still
written with `lat=None, lon=None`. This matters for route geometry,
heatmaps, and the existing `/api/analysis/route-matches` endpoint.

*Empty/missing latlng (indoor rides) must remain a no-op:* If `latlng` is
absent, empty, or `None`, both consumers must do nothing — `_store_streams`
must continue to write `lat=None, lon=None` per record (current behaviour),
and `_backfill_start_location` must leave `start_lat`/`start_lon` untouched.
The unit tests in Step 1.C explicitly cover this regression case.

*Verification:* Existing unit/integration tests must still pass — no
behavioural change for rides that already had correct data (FIT-ingested)
nor for indoor rides without GPS streams.

#### Step 1.C — Unit tests for the parser fix
*Target file:* `tests/unit/test_sync_latlng.py` (new).
*Test cases:*

**`_normalize_latlng`:**
- `[]` → `[]`.
- `[[42.29, -71.35], [42.30, -71.36]]` → `[(42.29, -71.35), (42.30, -71.36)]`.
- `[42.29, -71.35, 42.30, -71.36]` → `[(42.29, -71.35), (42.30, -71.36)]`.
- `[42.29, -71.35, 42.30]` (odd length) → truncates to `[(42.29, -71.35)]`.
- `[None, None]` → depends on design — either skip or include; document.

**`_store_streams` with flat latlng:**
- Build a minimal streams dict with `time: [0,1,2]` and
  `latlng: [42.29, -71.35, 42.30, -71.36, 42.31, -71.37]`.
- Mock the DB connection and assert the `INSERT INTO ride_records` rows
  contain `lat=42.29, lon=-71.35` for the first record (not `None`).

**`_backfill_start_location` with flat latlng:**
- Same streams as above. Assert the `UPDATE rides SET start_lat=42.29,
  start_lon=-71.35 WHERE id=? AND start_lat IS NULL` is called.
- With `latlng: [0.0, 0.0, 42.29, -71.35]` — assert the `(0, 0)` point is
  skipped and `42.29, -71.35` is used (fix the falsy-zero bug: replace
  `if lat and lon:` with `if lat is not None and lon is not None and
  (lat != 0.0 or lon != 0.0):`).

*Verification:*
```bash
source venv/bin/activate && pytest tests/unit/test_sync_latlng.py -v
```

#### Step 1.D — Write the backfill script
*Target file:* `scripts/backfill_ride_start_geo.py` (new).
*Required behaviour:*
1. Print the resolved `DATABASE_URL` and the host. **Parse the URL with
   `urllib.parse.urlparse`** and check `parsed.hostname`. Refuse to run
   unless `parsed.hostname` is one of `{"localhost", "127.0.0.1", "::1"}`
   OR `--allow-remote` is passed. Do **not** substring-match — that gives
   false positives like `localhost.example.com` and false negatives like a
   valid `127.0.0.1` URL with credentials in the userinfo.
2. Support `--dry-run`: read everything, print what would be updated, write
   nothing.
3. Query: `SELECT id, filename FROM rides WHERE start_lat IS NULL AND
   filename LIKE 'icu_%' ORDER BY start_time DESC`.
4. For each ride:
   a. Extract the ICU activity id from the filename. Filenames in the wild
      look like `icu_i137210941` (note the `i` prefix on the ICU id itself,
      so the full string starts with `icu_i`). Use
      `icu_id = filename.removeprefix('icu_')` — the resulting `icu_id`
      (e.g. `i137210941`) is what `fetch_activity_streams()` expects.
      Verify against the same call site already used by
      `scripts/backfill_icu_streams.py` to confirm the prefix convention
      before relying on it.
   b. Call `fetch_activity_streams(icu_id)`.
   c. Call the (now-fixed) `_backfill_start_location(ride_id, streams, conn)`.
   d. Log the result per-ride.
5. Rate-limit: `time.sleep(0.5)` between ICU API calls (courtesy, not a hard
   limit — ICU is more permissive than Nominatim but we have many rides).
6. Print final counts: `total`, `backfilled`, `no_streams`, `no_gps_in_streams`,
   `already_populated` (should be 0 given the WHERE, but good for idempotency
   on re-runs).
7. Idempotent: `_backfill_start_location` already has the `start_lat IS NULL`
   guard, so a second run finds zero candidates.
8. Exit non-zero on any DB error.

#### Step 1.E — Tests for the backfill script
*Target file:* `tests/unit/test_backfill_ride_start_geo.py` (new).
- Assert the localhost guard rejects a non-localhost `DATABASE_URL` without
  `--allow-remote`.
- Monkeypatch `fetch_activity_streams` to return a synthetic flat-array
  `latlng` response. Assert `_backfill_start_location` is called with the
  correct args.
- Monkeypatch to return `{}` (no streams). Assert the ride is counted as
  `no_streams` and not updated.

*Target file:* `tests/integration/test_backfill_ride_start_geo.py` (new).
- Seed three rides directly in the test DB:
  1. `filename='icu_test1'`, `start_lat IS NULL` → monkeypatch
     `fetch_activity_streams('test1')` to return flat-array latlng
     `[42.29, -71.35, 42.30, -71.36]`. Expect `start_lat=42.29`,
     `start_lon=-71.35` after backfill.
  2. `filename='icu_test2'`, `start_lat IS NULL` → monkeypatch returns `{}`
     (indoor ride, no streams). Expect untouched.
  3. `filename='icu_test3'`, `start_lat=35.69` already populated → expect
     untouched (not even selected by the query).
- Run the script's main function in-process. Assert results.
- Re-run; assert `backfilled == 0`.

*Verification:*
```bash
source venv/bin/activate
pytest tests/unit/test_backfill_ride_start_geo.py -v
./scripts/run_integration_tests.sh tests/integration/test_backfill_ride_start_geo.py -v
```

#### Step 1.F — Manual smoke test
1. Run existing tests to confirm the parser fix didn't break anything:
   ```bash
   pytest tests/unit -v
   ./scripts/run_integration_tests.sh -v
   ```
2. Trigger a single-ride re-sync for the Natick ride (filename
   `icu_i137210941`) via the UI or `POST /api/sync/ride/{icu_id}` — note the
   path param is the icu_id *after* the `icu_` prefix is stripped, i.e.
   `POST /api/sync/ride/i137210941` (the `i` belongs to the icu_id, not the
   filename prefix). See `server/routers/sync.py:80`. Confirm the Ride
   Details page now shows the city/state label (Natick, MA or similar).
3. Run the backfill against local dev DB:
   ```bash
   python scripts/backfill_ride_start_geo.py --dry-run
   python scripts/backfill_ride_start_geo.py
   ```
   Re-run → `backfilled=0`.

#### Step 1.G — Production run (gated on user approval)
- Show the user the `--dry-run` output from local.
- Confirm the user wants the script run against the Neon dev DB.
- `python scripts/backfill_ride_start_geo.py --allow-remote` against Neon.
- Re-run to verify idempotency.
- Run the Step 1.A audit query again to confirm remaining `start_lat IS NULL`
  rides are indoor/no-GPS only.

#### Phase 1 Definition of Done
- `_normalize_latlng()` helper exists in `server/services/sync.py`, handles
  both flat-float and nested-pair formats.
- `_store_streams` writes correct `lat`/`lon` into `ride_records` for new
  ICU syncs going forward.
- `_backfill_start_location` correctly populates `rides.start_lat/lon` for
  new ICU syncs going forward.
- `scripts/backfill_ride_start_geo.py` exists, has unit + integration tests,
  is idempotent, refuses non-localhost without `--allow-remote`, and supports
  `--dry-run`.
- After running against the Neon dev DB: every outdoor ICU ride that previously had
  `start_lat IS NULL` now has `start_lat`/`start_lon` populated.
- The Ride Details page city/state label renders for all affected rides
  without any frontend changes.
- A post-run audit confirms remaining `start_lat IS NULL` rides are
  indoor/virtual only.

---

### PHASE 2 — Free-text search

#### Step 2.A — Characterise current `/api/rides` behaviour (Safety Harness)
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

#### Step 2.B — Extract a pure query-builder helper (Refactor under harness)
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
yielding *exactly* the current SQL — verified by tests in 2.A).

**Placeholder convention (mandatory):** All bind parameters must use `?`
placeholders, **never** `%s`. The project's psycopg2 wrapper at
`server/database.py:47` translates `?` → `%s` at execute time. Mixing the two,
or worse — using f-strings to inline values — will silently break parameter
binding and re-introduce SQL-injection risk on the new free-text path. The
unit tests in Step 2.C must assert the returned SQL contains `?` and not
`%s`.

*Verification:* Re-run the harness from 2.A. No behaviour change yet.

#### Step 2.C — Unit tests for the helper
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

#### Step 2.D — Wire `q` into the endpoint
*Target file:* `server/routers/rides.py`.
*Change:*
- Add `q: Optional[str] = Query(None)` to `list_rides()`.
- Call `_build_rides_query(..., q=q, ...)` instead of inline SQL building.
- Trim/lowercase `q` once at the top of the helper so the SQL is always
  case-insensitive.

**Multi-word semantics — exact SQL fragment:** Split the trimmed `q` on
whitespace into N words. Each word becomes its own parenthesised OR-group
across the three searched columns; the N groups are then ANDed together.
For `q="hard climb"` (two words) the appended WHERE fragment must be
literally:

```
AND (LOWER(title) LIKE ? OR LOWER(post_ride_comments) LIKE ? OR LOWER(coach_comments) LIKE ?)
AND (LOWER(title) LIKE ? OR LOWER(post_ride_comments) LIKE ? OR LOWER(coach_comments) LIKE ?)
```

with params `['%hard%', '%hard%', '%hard%', '%climb%', '%climb%', '%climb%']`
(in that exact order — three copies per word, words appended in input order).
This must NOT be `LIKE '%hard climb%'` (substring of the joined phrase) nor
a single OR-group with both words. The Step 2.C unit tests must lock this
exact shape, including param order.

`coach_comments` IS included in the searched columns (resolution of Open
Question #2 below). Rationale: users browsing their ride history routinely
remember a phrase the coach used (e.g. "tempo block") more vividly than
their own title — excluding it would mask the most distinctive text on most
rides. The Rides UI search placeholder text in Step 2.G should make this
behaviour discoverable ("Search by name or notes…").

*Verification:*
```bash
./scripts/run_integration_tests.sh tests/integration/test_api.py -v
```
Existing tests must still pass.

#### Step 2.E — Integration tests for `?q=`
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

#### Step 2.F — Frontend API client
*Target file:* `frontend/src/lib/api.ts`.
*Change:* Add `q?: string` to the `fetchRides` params type and append it to
the `URLSearchParams` if non-empty (mirror existing pattern lines 73-80).

#### Step 2.G — Frontend search input
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

#### Step 2.H — E2E test
*Target file:* `tests/e2e/03-rides.spec.ts`.
*Test case:*
```
test('search box filters rides by title', ...)
```
Type a substring known to exist in seeded data, press Enter, assert row count
decreased OR "No rides match" appears.

*Verification:* `./scripts/run_e2e_tests.sh -g "search"`.

#### Phase 2 Definition of Done
- All unit + integration + E2E tests green.
- `GET /api/rides?q=foo` returns case-insensitive substring matches across
  `title`, `post_ride_comments`, `coach_comments`.
- The existing date filter and the new `?q=` filter compose without surprise.
- The Rides page UI has a working search box that visually matches the
  existing toolbar style.

---

### PHASE 3 — Location radius

> **Prerequisite check.** Phase 1 (data backfill) must have been run against
> the target environment first. After Phase 1, the only `rides` rows with
> `start_lat IS NULL` should be those that genuinely have no GPS data
> (indoor / virtual rides). The radius filter will silently exclude those,
> which is the correct behaviour. The old plan's "Step 2.A: Fix forward in
> `intervals_icu.py`" has been **dropped** — investigation 2026-04-20 confirmed
> the orchestrator (`server/services/sync.py:515` and
> `server/services/single_sync.py:93`) already calls `_backfill_start_location`
> after `_store_streams`, so new ICU syncs already populate the columns.

#### Step 3.A — Add the spatial-ish index
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
- After Step 3.D is wired, run `EXPLAIN (ANALYZE, BUFFERS) SELECT ... FROM
  rides WHERE start_lat BETWEEN ... AND start_lon BETWEEN ...` against the
  local DB and confirm the planner uses `idx_rides_start_lat_lon` (Index
  Scan or Bitmap Index Scan, not Seq Scan). Postgres may choose to use the
  index on the leading `start_lat` column only and post-filter on
  `start_lon`; that is acceptable. If the planner refuses the index entirely
  (e.g. on a near-empty test DB), document it and move on — the production
  data set has enough rows for the planner to prefer the index.

#### Step 3.B — Geocoding service module
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
- **Concurrency:** `geocode_place()` is a synchronous blocking call (network
  + sleep for rate limit). It is invoked from the sync `list_rides()`
  handler. FastAPI runs sync endpoint functions on its threadpool, so the
  call does not block the event loop — no explicit `asyncio.to_thread`
  wrapper is required. Document this in the module docstring so a future
  refactor to an `async def` handler remembers to add the wrapper.

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

#### Step 3.C — Haversine helper + query-builder extension
*Target file:* `server/routers/rides.py`.
*Change:*
- Extend `_build_rides_query()` from Phase 2 to optionally accept
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

#### Step 3.D — Wire `near` / `near_lat` / `near_lon` / `radius_km` into the endpoint
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

#### Step 3.E — Unit tests
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

#### Step 3.F — Integration tests
*Target file:* `tests/integration/test_api.py`.

**Anchor to the actual seed coordinates, not assumptions.** The seed
generator at `tests/integration/seed/generate_recent.py:137` places
synthetic rides at approximately `(44.166893, -71.164314)` (White
Mountains, NH). However, the committed `seed_data.json.gz` may or may
not include rides with non-NULL `start_lat`/`start_lon` (depending on
when the seed was last regenerated). **Before asserting any radius
behaviour, run a preflight query inside the test:**

```python
def _seed_anchor(db_conn):
    """Return (lat, lon) of any seeded ride with non-NULL GPS, or fail
    the test loudly if none exists."""
    row = db_conn.execute(
        "SELECT start_lat, start_lon FROM rides "
        "WHERE start_lat IS NOT NULL AND start_lon IS NOT NULL LIMIT 1"
    ).fetchone()
    assert row is not None, (
        "Test seed has no rides with start_lat/start_lon populated. "
        "Regenerate seed_data.json.gz from generate_recent.py and re-run."
    )
    return row[0], row[1]
```

Use the returned anchor as the centre of the radius queries — do **not**
hard-code `(44.166, 0.0)` (which is ~5,500 km from the actual seed
location and would silently return zero results).

*Test cases:*
- `anchor_lat, anchor_lon = _seed_anchor(db_conn)`. `GET
  /api/rides?near_lat={anchor_lat}&near_lon={anchor_lon}&radius_km=10`
  returns at least one seeded ride.
- `GET /api/rides?near_lat=0.0&near_lon=0.0&radius_km=1` returns `[]`
  (nothing in the seed near the Null Island point — verified safe because
  the seed anchor is in NH, not at (0,0)).
- `GET /api/rides?radius_km=10` (no `near*`) → 400.
- `GET /api/rides?near_lat={anchor_lat}&near_lon={anchor_lon}&radius_km=20000`
  returns every seeded ride that has GPS (sanity — 20000 km > half Earth
  circumference).
- `GET /api/rides?near_lat={anchor_lat}&near_lon={anchor_lon}&radius_km=10
  &q=<seeded word>&start_date=2026-01-01&end_date=2026-12-31` composes all
  three filters.

*Verification:* `./scripts/run_integration_tests.sh tests/integration/test_api.py -v`.

#### Step 3.G — Frontend API client
*Target file:* `frontend/src/lib/api.ts`.
*Change:* Extend `fetchRides` params type with `near?: string`, `near_lat?:
number`, `near_lon?: number`, `radius_km?: number` and append them to the
query string.

#### Step 3.H — Frontend "Advanced" UI
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

#### Step 3.I — E2E test
*Target file:* `tests/e2e/03-rides.spec.ts`.
- Open Advanced panel.
- Fill place + radius (use a known seed lat/lon expressed as a place — or use
  the `near_lat`/`near_lon` escape hatch by populating the inputs via
  `page.evaluate` to bypass Nominatim in CI).
- Click Go, assert filtered count.

*Verification:* `./scripts/run_e2e_tests.sh -g "near"`.

#### Phase 3 Definition of Done
- Phase 1 backfill has been run against the target DB; remaining
  `start_lat IS NULL` rides are confirmed indoor/no-GPS only.
- Migration `0008` applied, index visible.
- `GET /api/rides?near=Santa+Fe%2C+NM&radius_km=50` works end-to-end.
- The Advanced panel on the Rides screen returns sensible results for at
  least three known places.

---

## Test Plan Summary

| Layer | What we test | Where |
| --- | --- | --- |
| Unit | `_normalize_latlng` — flat array, nested pairs, empty, odd-length | `tests/unit/test_sync_latlng.py` |
| Unit | `_store_streams` writes correct lat/lon from flat latlng | `tests/unit/test_sync_latlng.py` |
| Unit | `_backfill_start_location` uses normalised latlng, skips (0,0) | `tests/unit/test_sync_latlng.py` |
| Unit | Backfill script localhost guard + stream dispatch (mocked) | `tests/unit/test_backfill_ride_start_geo.py` |
| Integration | Backfill populates only NULL-start_lat ICU rides | `tests/integration/test_backfill_ride_start_geo.py` |
| Unit | Pure query-builder (`_build_rides_query`) — every param combination | `tests/unit/test_rides_search.py` |
| Unit | Haversine distance helper | `tests/unit/test_haversine.py` |
| Unit | Geocoding cache + rate limiter (mocked HTTP) | `tests/unit/test_geocoding_cache.py` |
| Integration | `/api/rides?q=` composes with date and sport filters | `tests/integration/test_api.py` |
| Integration | `/api/rides?near_lat=&near_lon=&radius_km=` | `tests/integration/test_api.py` |
| E2E | Search box filters list | `tests/e2e/03-rides.spec.ts` |
| E2E | Advanced panel filters list | `tests/e2e/03-rides.spec.ts` |
| Manual | Re-sync Natick ride → city/state label appears | browser |
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
- Pagination of the rides list. The current 500-row cap (`limit=500`
  default in `list_rides()`) stays. **Implication for users:** a search
  whose date+`q`+`near` filters still match more than 500 rides will
  silently truncate to the 500 most recent (`ORDER BY start_time DESC`).
  No UI affordance is added in v1 to surface this. If/when the corpus or
  user complaints warrant it, add either a "showing N of many" indicator
  or proper cursor pagination.

---

## Open Questions (need user input before Phase 1 starts)

1. **Phase 1 Neon run:** Confirm the user wants
   `scripts/backfill_ride_start_geo.py --allow-remote` run against the Neon
   dev DB. The script will call `fetch_activity_streams` once per affected ICU
   ride (those with `start_lat IS NULL`), re-parse the latlng stream with the
   fixed parser, and write `start_lat`/`start_lon` on the parent ride. This
   is read-only against ICU (streams endpoint) and a targeted UPDATE against
   Neon. The expected blast radius is every outdoor ICU ride — indoor rides
   will be skipped (no latlng in streams).
2. ~~**Should free-text search also match `coach_comments`?**~~ **Resolved
   2026-04-20: YES, include `coach_comments` in v1.** Rationale: users
   browsing their ride history routinely remember a phrase the coach used
   (e.g. "tempo block") more vividly than their own title. Excluding it
   would mask the most distinctive text on most rides. Discoverability
   handled by the placeholder text "Search by name or notes…".
3. **Should free-text search match `filename`?** Useful for power users
   ("icu_12345"), noisy for everyone else. Plan currently excludes it.
   *(Phase 2.)*
4. ~~**Default unit for radius (km vs mi)?**~~ **Resolved 2026-04-20:**
   read from the existing `useUnits()` hook. If `useUnits()` returns
   `'imperial'`, display the radius input in miles and convert to km
   client-side before sending to the API (the API contract is `radius_km`
   only — the server stays unit-agnostic). If `useUnits()` returns
   `'metric'` or is unavailable, default to km. The numeric default of
   `25` is in *whatever unit is being displayed* (so 25 mi for imperial
   users, 25 km for metric users) — round numbers feel native.
5. **Acceptable to send Nominatim queries from our Cloud Run backend?**
   Nominatim's policy requires a contact email in the User-Agent and ≤1
   req/sec. We will comply; just confirming the user is OK with this rather
   than provisioning a paid geocoder. *(Phase 3.)*
6. **What does the user expect when a ride has no GPS?** After Phase 1 the
   only `start_lat IS NULL` rides should be indoor/virtual. Currently the plan
   silently excludes them from radius results. Alternative: include with a
   visual marker. Confirm. *(Phase 3.)*

---

## Branch Name Suggestion

**Default: two worktrees, not three.** The house style in this repo
(see e.g. `plans/feat-calendar-ride-names.md`) is one branch per plan, and
three PRs for one feature is heavier than necessary here.

- Phase 1: `worktrees/rides-geo-backfill` → branch `data/rides-geo-backfill`
  *(must ship and run against Neon before Phase 3 can start, so it really
  is a separate branch)*
- Phases 2 + 3: `worktrees/rides-search` → branch `feat/rides-search`
  *(both touch the same `list_rides()` helper and the same Rides.tsx
  toolbar — splitting them produces a guaranteed merge-conflict diff)*

Only split Phases 2 and 3 into separate branches if review feedback on the
Phase 2 PR suggests landing it in isolation, or if a user-visible release
needs to gate Phase 3 separately.

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Parser fix breaks FIT-ingested rides (different latlng format) | Low | FIT-ingested rides don't go through `_store_streams`/`_backfill_start_location` — they use `server/ingest.py` which reads `start_position_lat/long` from the FIT session directly. No regression path. Unit tests cover both formats. |
| Backfill hits ICU rate limits | Medium | 0.5s sleep between calls. ICU is more permissive than Nominatim, but we're polite. Script can be stopped and re-run (idempotent). |
| Backfill mis-runs against wrong DB | Medium | Script prints `DATABASE_URL`, refuses without localhost or `--allow-remote`; supports `--dry-run`; idempotent via `start_lat IS NULL` guard. |
| First GPS point is a bad fix (transient (0,0) or null) | Low | `_backfill_start_location` fix will skip `(0,0)` points (replacing the `if lat and lon:` falsy check with an explicit `(0,0)` guard). First *valid* point is used — matches what Garmin head units report as `start_position_lat/long`. |
| ICU-synced rides have no GPS after Phase 1 → empty radius results | Low (only true indoor rides remain) | Confirmed by Step 1.A audit; remaining NULL rows are expected (indoor/virtual). |
| Nominatim rate-limits or blocks our IP | Medium | In-process cache + 1 req/sec limiter + proper User-Agent + `near_lat`/`near_lon` client-bypass param. |
| Substring `LIKE` is slow on large `post_ride_comments`/`coach_comments` | Low (single-athlete dataset) | Defer FTS until measured. The query already has a `start_time DESC LIMIT 500` ceiling. |
| Refactor of `list_rides()` regresses the existing date filter | Low | Step 2.A locks behaviour with golden tests *before* refactoring (Step 2.B). |

---

## Implementation Status

Implemented on branch `worktree-agent-a637d1df`.

### Commits

| Commit | Scope |
| --- | --- |
| `d2a6dae` | feat(rides): add free-text search across title and notes — Phase 2 of the plan (`?q=`). |
| `6ff1d17` | feat(rides): add location radius search with Nominatim geocoding — Phases 1 (parser fix + backfill) and 3 (`?near=&radius_km=`). |
| `8de094c` | refactor(geocoding): introduce `GeocodingProvider` Protocol for pluggable providers — adds the `GEOCODER` env var, keeps Nominatim as the only real implementation, no caller changes. |
| `7783f5e` | feat(geocoding): add `MockProvider` and E2E radius test — closes the deferred E2E coverage item below. |
| `5aa66db` | chore(plans): record commit SHA for MockProvider follow-up. |
| `6fbf2b9` | fix(rides): add search clear button; fix backfill script portability. |
| `9ef3098` | fix(e2e): correct metric card label in 03-rides spec; update plan status — 13/13 E2E pass, 387 unit, 219 integration (10 pre-existing failures). |

### Closed Follow-ups

- **E2E coverage of the radius filter.** `MockProvider` is now registered under `GEOCODER=mock` in `server/services/geocoding.py`; it exposes a fixed table of place names plus an `__unreachable__` sentinel that raises a transport error. `tests/e2e/03-rides.spec.ts` adds a Playwright case that opens the Advanced panel, types `North Pole` (a fixture far from any real ride), clicks Apply, and asserts the empty-results UI. The test `test.skip()`s itself when the backend wasn't started with `GEOCODER=mock`, so a forgetful operator gets a clear signal instead of a flake. Run via:
  ```bash
  GEOCODER=mock uvicorn server.main:app --host 0.0.0.0 --port 8080 &
  GEOCODER=mock npx playwright test --config tests/e2e/playwright.config.ts 03-rides
  ```

### Deferred / Open Items

- **Postgres-backed geocoder cache.** The current cache is in-process; multi-instance deployments will hit Nominatim more than once per place. Defer until traffic warrants.
- **Backfill production run.** `scripts/backfill_ride_start_geo.py --allow-remote` against Neon still requires operator approval per AGENTS.md mandates. Until run, ICU outdoor rides without `start_lat` won't be findable via the radius filter.
