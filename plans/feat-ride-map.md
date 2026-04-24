# Feature Implementation Plan: Ride Map with Synced Timeline Cursor

## Goal & user-visible outcome

When a user opens a ride from the Rides page, the existing detail panel
(`frontend/src/pages/Rides.tsx`, the right-hand pane that already shows the
metric grid, the `RideTimelineChart`, the laps table and the AI coaching
notes) gains a new **Route Map** card. The card renders the full GPS track of
the ride as a polyline overlaid on a road/trail basemap. Road names appear for
road rides; named singletrack and forest tracks appear for MTB / gravel /
hike. As the user moves the mouse cursor along the existing timeline chart
(power / HR / cadence / elevation), a circular marker on the map glides along
the polyline to the GPS point that corresponds to that time index. Clicking a
lap row in the laps table similarly snaps the marker to the lap's start
point. Indoor rides (no GPS data) hide the card entirely — there is nothing
to map.

---

## Scope

### In scope
- A new `<RideMap>` React component rendered inside the existing ride-detail
  pane in `frontend/src/pages/Rides.tsx`, between the `RideTimelineChart` and
  the `LapsTable` (or below the timeline chart on narrow screens).
- Reuse the per-record `lat`/`lon` already exposed on `RideDetail.records`
  (`frontend/src/types/api.ts:45-46`, populated by both FIT ingest at
  `server/ingest.py:233-234` and the now-fixed ICU latlng parser at
  `server/services/sync.py:_normalize_latlng`).
- A shared `hoveredTimeIdx` React state lifted out of `RideTimelineChart` so
  both the chart and the map read from one source of truth.
- A tile/style choice (see Architectural decisions §1) that surfaces both
  street names and OSM trail names (`highway=path`, `highway=track`,
  `highway=footway` with `name=*`).
- Lap-aware: when `selectedLap` / `hoveredLap` is non-null, the map also
  highlights that lap's slice of the polyline and recentres on it.

### Out of scope (explicit)
- Elevation profile rework — the existing elevation dataset on
  `RideTimelineChart` stays as-is.
- Route export / GPX download / share-by-link.
- Drawing on the map (segment selection, custom waypoints).
- Multi-ride overlay / heatmap of all rides.
- Per-ride-type basemap *switching* (one style serves all sports — see
  decision §1.b).
- A new dedicated `/rides/:id` page route. This work stays inside the existing
  Rides page's detail pane. (A deep-linked route is Campaign 18's territory.)
- Surface streetname / city tooltips on hover. Labels come from the basemap
  itself.
- Backfilling per-record `ride_records.lat/lon` for historical ICU rides
  whose streams were ingested before the Phase 1 parser fix in Campaign 17.
  Those rides will simply not show a map until they are re-synced. A
  separate backfill is *out of scope here* — it would require re-fetching
  every affected ride's full streams and rewriting ~10k records per ride.
- Map-pin markers on the *Rides list* page — the radius-search UX from
  Campaign 17 stays text-only.

### Out of scope (tracked elsewhere)
- **Single-click instant pin** (a one-shot click on a chart point that pins a
  marker without dragging) — not requested; the existing drag-to-select-zoom
  *is* the user's pin mechanism and is handled in Phase 4 (see below).
- **"Follow cursor" auto-pan toggle for hover-scrubbing** — tracked as
  **Campaign 21** in `plans/00_MASTER_ROADMAP.md`. Hover-scrub auto-pan is
  intentionally disabled in C20 to avoid vertigo; an opt-in toggle is a
  separate UX pass.

---

## Investigation Summary (already done — read-only)

**Frontend — ride detail pane (`frontend/src/pages/Rides.tsx`):**
- The page is a single 1,214-line component. The ride detail pane is rendered
  conditionally when `selectedRideId != null && ride != null` (line ~355).
- Hover/select state for the chart is already lifted to the page-level
  component as `hoveredStep` / `selectedStep` / `hoveredLap` / `selectedLap`
  (lines 110-113). These are passed both to `RideTimelineChart` (line 540)
  and to `LapsTable` / `WorkoutStepsTable` (lines 555-572). **This is the
  exact pattern we extend** — adding a `hoveredTimeIdx` (and `selectedTimeIdx`)
  next to the existing four states is the natural fit.
- The detail pane already reverse-geocodes `ride.start_lat`/`start_lon` via
  Nominatim (lines 289-306) to display the city/state label. We will leave
  that alone.

**Frontend — chart (`frontend/src/components/RideTimelineChart.tsx`):**
- Uses Chart.js (`react-chartjs-2`) with `interaction: { mode: 'index',
  intersect: false }` (line 237). The tooltip already exposes the hovered
  index per dataset point but the value is not currently lifted out of the
  component.
- `chartRef` is a `useRef<ChartJS<'line'>>` (line 82) — we already have
  imperative access to the chart instance, so we can add a single
  `onHover` plugin that emits the data-space index to a parent callback
  without changing the chart's existing UX.
- `downsampleStep` (line 91) is critical: the chart x-axis is **sampled
  every N records** (where `N = step` is computed by
  `calculateChartSampling` to keep <600 points). When the parent receives a
  hovered index `i` from the chart, it must multiply by `downsampleStep` to
  get the true `records[]` index — otherwise the map marker will lag.

**Frontend — `RideRecord` type (`frontend/src/types/api.ts:37-48`):**
- Already includes `lat?: number`, `lon?: number`. **No backend type or
  migration is required.**

**Backend — `/api/rides/{id}` (`server/routers/rides.py:370-395`):**
- Selects `lat, lon` for every ride record (line 382). The current response
  is already complete; **no new endpoint or response field is required for
  rides that have GPS data ingested correctly**.
- The response can be sizeable on long rides (~10k records × ~10 fields).
  The page already pays this cost today; we are not increasing payload size.

**Backend — GPS storage:**
- `ride_records.lat REAL, lon REAL` exist since the baseline migration
  (`migrations/0001_baseline.sql:63-64`).
- FIT ingest (`server/ingest.py:233-234`) populates lat/lon by converting
  Garmin's `position_lat` / `position_long` semicircle integers to degrees.
- ICU sync (`server/services/sync.py:317-321`) populates lat/lon via
  `_normalize_latlng()` — this was fixed in Campaign 17 and is now
  authoritative for new syncs.
- For historical ICU rides (synced before the fix), `ride_records.lat/lon`
  are NULL. The Map card must degrade gracefully: if fewer than 2 records
  have non-null GPS, render an "indoor or no-GPS ride" placeholder instead
  of a map.

**Frontend dependencies (`frontend/package.json`):**
- No map library is currently installed. `chart.js@^4.5.1` and
  `react-chartjs-2@^5.3.1` are present and unrelated.

**Test infrastructure:**
- Unit tests in `tests/unit/`, integration in `tests/integration/`, E2E
  Playwright in `tests/e2e/`. The relevant E2E spec is
  `tests/e2e/03-rides.spec.ts`.

---

## Architectural decisions

### 1. Map provider / library

**Decision: MapLibre GL JS + a free OpenFreeMap "liberty" vector style.**

Reasoning, scored against the user's three criteria (cost, trail-name
quality, fit with the codebase):

| Option | Cost at our scale | Trail-name quality | Verdict |
| --- | --- | --- | --- |
| **MapLibre GL JS** + **OpenFreeMap** vector tiles | Free (OpenFreeMap is donation-funded, no API key, no rate limits documented for self-hosted-style usage; raster fallback `tile.openstreetmap.org` also free with attribution) | Excellent — vector style includes `highway=path`/`track`/`footway` with `name=*` rendered at z14+ | **Chosen** |
| Leaflet + raster OSM tiles (`tile.openstreetmap.org`) | Free, well-known, sticky to OSM tile-usage policy (no heavy use, attribution required) | OK for roads, mediocre for trail names — vanilla OSM-Carto raster is street-biased, named singletrack often missing on default tiles | Rejected — trail names are a hard requirement |
| Leaflet + Thunderforest "Outdoors" raster tiles | Paid above 150k tiles/month free tier | Excellent — purpose-built outdoor style, named tracks/contours/POIs | Rejected — adds a paid dependency for a single user; if MapLibre+OpenFreeMap proves wrong we revisit Thunderforest as the swap target (see §1.c) |
| Mapbox GL JS + Mapbox "Outdoors" style | Free up to 50k loads/month then $/load | Excellent | Rejected — proprietary SDK, requires account + token, more aggressive deprecation cadence than MapLibre (Mapbox v2+ is non-OSS, MapLibre is the OSS fork) |
| Google Maps JS SDK | $7/1k loads above the small free tier; requires API key | Poor for MTB — Google's basemap renders some major trails but consistently omits OSM-named singletrack | Rejected — we have a directional decision to use Google for *geocoding* (Campaign 19 Phase A), but tiles and geocoding are separate products. Cost-per-load on a single-athlete app is poor value, and trail coverage is the headline reason to do this campaign at all |

**Chosen tile source URL:**
`https://tiles.openfreemap.org/styles/liberty` (vector style JSON, includes
`name`-tagged `highway=path`/`track`/`footway` layers at z14+).

**Bundle size note:** MapLibre GL adds ~220 KB gzipped. The current frontend
bundle is 808 KB gzipped (per Campaign 17 verification). This is acceptable
for a lazy-loaded card. We will dynamically import the `<RideMap>` component
(`React.lazy`) so users who never expand a ride detail don't pay for it.

#### 1.a — Why not abstract behind a `MapTileProvider` Protocol?
The provider-abstraction rule in `AGENTS.md` says: *abstract when there is a
plausible second vendor today.* Here:
- The **library** (MapLibre GL) is OSS, self-contained, and the de-facto
  successor to Mapbox GL — there is no realistic library swap target unless
  we decide we don't need a vector renderer at all (in which case we'd
  rewrite to Leaflet, a much bigger refactor than swapping a tile URL).
- The **tile URL** is a single string. Swapping OpenFreeMap → Thunderforest
  → Mapbox vector tiles is a one-line change, not an architectural seam.

So we will **not** introduce a `MapTileProvider` Protocol. We will, however,
read the tile style URL from a single `VITE_MAP_TILE_STYLE_URL` env var
(default `https://tiles.openfreemap.org/styles/liberty`) so a future swap to
Thunderforest / Mapbox / a self-hosted style is a config change, not a code
change.

#### 1.b — Per-ride-type style switching?
**No.** Confirming the simpler answer the user offered: one style that shows
both road names and trail names is correct. OpenFreeMap "liberty" renders
named highways at z11+ and named paths/tracks at z14+. A road ride zoomed to
city level will show road names; an MTB ride zoomed to trailhead level will
show trail names. The same style serves both — switching styles per ride
type would be UX clutter and an extra round of testing for no benefit.

#### 1.c — Future swap target (documented, not implemented)
If OpenFreeMap goes down, gets rate-limited, or we need higher fidelity:
swap `VITE_MAP_TILE_STYLE_URL` to Thunderforest "outdoors-v2" (paid tier)
or self-host a tileserver-gl with `planet.osm.pbf`. No application code
changes.

### 2. GPS data source

**Decision: serve GPS from the existing `GET /api/rides/{id}` response field
`records[].lat`/`records[].lon`. No new endpoint. No new response field.**

Reasoning:
- The data is **already** in the response. `server/routers/rides.py:382`
  selects `lat, lon` per record. The frontend `RideRecord` type already
  exposes them. We are removing zero columns from a query and adding zero
  payload bytes.
- A separate `GET /api/rides/{id}/gps` endpoint would shave the polyline
  bytes off the timeline chart's response, but the ride detail page **must**
  fetch the records anyway for the chart, so any per-endpoint split forces
  two round-trips.
- Payload bloat concern: per the existing code, a long ride is ~10k records
  × ~10 fields (timestamp, power, hr, cadence, speed, altitude, distance,
  lat, lon, temperature). We pay this cost today. The map adds zero new
  bytes from the server.

**Frontend cost mitigation:**
- The map component will **decimate** the polyline using
  Ramer-Douglas-Peucker (or simpler: pick every Nth point matching
  `RideTimelineChart`'s `downsampleStep`) before handing it to MapLibre. A
  3-hour MTB ride at 1 Hz produces ~10,800 points; 600 is visually
  indistinguishable on screen and renders smoothly. We deliberately reuse
  the same `downsampleStep` the chart already computes so chart-index ↔
  map-index conversion is a pure multiplication (no off-by-one risk).
- The marker, however, must follow the **full-resolution** track to feel
  smooth. So: render the **decimated** polyline, but resolve the cursor's
  marker position from the **full-resolution** `records[]` indexed by
  `hoveredTimeIdx * downsampleStep + offsetWithinBucket=0`.

### 3. Cursor sync mechanism

**Decision: lift `hoveredTimeIdx` (and `selectedTimeIdx`) into the existing
ride-detail-pane parent component in `Rides.tsx`. Pass it to both
`RideTimelineChart` and `RideMap` as props. No event bus, no React Context.**

Reasoning:
- The codebase **already** lifts `hoveredStep` / `hoveredLap` / `selectedStep`
  / `selectedLap` to the same parent (`Rides.tsx:110-113`). Adding two more
  state fields is idiomatic and consistent.
- React Context would scatter the source-of-truth across files for no
  benefit at this scale (one chart, one map, one parent).
- An event bus / `EventTarget` would couple component lifecycles and
  defeat React's mental model.

**State shape (exact):**
```ts
// In Rides.tsx, alongside the existing hoveredStep / selectedStep state.
const [hoveredTimeIdx, setHoveredTimeIdx] = useState<number | null>(null)
//   number = the index into the full-resolution records[] array.
//   null   = no hover (mouse is outside chart area).
```

We deliberately do **not** also surface `selectedTimeIdx` in v1. The
existing `selectedStep` and `selectedLap` already cover the "click to lock"
behaviour for laps and workout steps, which are the things users want to
"pin" on the map. Adding a third selection axis (raw time) would add UI
complexity (which one wins when both are set?) for no clear use case.
If demand emerges, follow up with `selectedTimeIdx` as an additive change.

**Chart → parent contract:**
- `RideTimelineChart` accepts a new optional prop:
  `onTimeIdxHover?: (recordIdx: number | null) => void`.
- It is called from a Chart.js `onHover` callback (chart options). The
  callback receives the active element's `dataIndex` (which is the
  *downsampled* index), multiplies by `downsampleStep`, and emits the
  full-resolution index. On mouse leave it emits `null`.
- This is the **only** behavioural change to `RideTimelineChart`. The
  existing zoom, selection-rectangle, and step/lap highlighting are
  untouched.

**Parent → map contract:**
- `RideMap` accepts `hoveredTimeIdx: number | null` and renders a marker at
  `records[hoveredTimeIdx]` if non-null and that record has lat/lon.
- When the marker is updated, the map does **not** auto-pan. Auto-pan
  during hover-scrubbing causes vertigo. Pan only happens (a) on initial
  render — fit the polyline bounds — and (b) when `selectedLap` changes,
  where we recentre on the lap's start point.

### 4. Trail name rendering

**Decision: rely on the OpenFreeMap "liberty" style at default zoom (auto-fit
to the polyline bounds; typically z12-z14 for a 30-60 km loop).**

The "liberty" style includes these layers (verified by reading the public
style JSON at `https://tiles.openfreemap.org/styles/liberty`):
- `road_label` for `highway=primary/secondary/residential/...` with
  `name=*`, visible from z10.
- `path_pedestrian_label` for `highway=path/track/footway/cycleway` with
  `name=*`, visible from z14.

We do not modify the style JSON in v1. If a future user complaint specifies
a particular trail that is unlabelled at z14, we can either zoom the map
further (bad UX) or fork the style and bump the path-label minzoom to z13
(deferred follow-up).

### 5. Ride-type-conditional behaviour

**Decision: no per-sport branching.** One style, one component, one render
path. The ride's `sport` field is already on `RideSummary` and is not
consulted by the map. (We might later use it to *colour* the polyline
differently for road vs. MTB — but that is a v2 polish item, not a v1
requirement.)

---

## Phases

The work is broken into four phases. Phase 1 is a backend smoke-test only —
the data is already there, but we will lock in its shape with a test before
the frontend starts to consume it. Phases 2-4 are pure frontend.

| Phase | Scope | Ships independently? | Status |
| --- | --- | --- | --- |
| **Phase 1** | Backend characterisation test: assert `GET /api/rides/{id}` returns `records[].lat/lon` for an outdoor ride and empty/null for an indoor ride. No code change. | Yes — but trivially | [x] Implemented in `tests/integration/test_api.py` (`test_ride_detail_includes_per_record_gps`, `test_ride_detail_indoor_returns_no_gps_records`) |
| **Phase 2** | New `<RideMap>` component, lazy-loaded, renders the static polyline only (no cursor sync). Auto-fit bounds. | Yes — useful on its own | [x] Implemented: `frontend/src/lib/map.ts` (helpers + 22 unit tests in `map.test.ts`), `frontend/src/components/RideMap.tsx`, lazy-loaded in `frontend/src/pages/Rides.tsx`. Lazy-chunk verified: `RideMap-*.js` (gzip 273 KB) contains `maplibregl`; `index-*.js` does NOT. |
| **Phase 3** | Lift `hoveredTimeIdx` to parent; emit from `RideTimelineChart` via `onTimeIdxHover`; render moving marker on map. | Yes — depends on Phase 2 | [x] Implemented: `RideTimelineChart` now emits via `onTimeIdxHover` and `onTimeRangeSelect` (refs-stored callbacks; chart does not re-render on hover). `RideMap` renders a `maplibregl.Marker` synced to `hoveredTimeIdx`. State lifted to `Rides.tsx`. |
| **Phase 4** | Lap highlighting + drag-zoom-range highlighting on map (polyline slice + recentre); placeholder for indoor/no-GPS rides; ride-detail-page integration polish (responsive layout). | Yes — depends on Phase 2 | [x] Implemented: `lapRecordRange` + `sliceCoords` helpers in `lib/map.ts` (composition tests in `map.test.ts`); `RideMap` highlight effect handles both `selectedLap` and `selectedTimeRange` with explicit precedence (drag-zoom wins); chart's Reset Zoom button clears the map highlight; indoor placeholder shipped in Phase 2. |

### Phase 4 scope addendum (added 2026-04-22)

The chart's existing drag-to-select-zoom interaction must also drive the map.
When the user drag-selects a time range on `RideTimelineChart`:
- The map highlights the corresponding polyline slice (full opacity), dims
  the rest to 25% — same visual treatment as the lap-highlight.
- The map auto-fits its bounds to the selected slice (this is a deliberate
  zoom action, so auto-pan IS desired here — unlike hover-scrub).
- Clearing the selection (existing Reset Zoom button) restores the full
  polyline at full opacity and refits to the entire ride.

Implementation: add `onTimeRangeSelect?: (range: { startIdx, endIdx } | null) => void`
to `RideTimelineChart` (mirroring the `onTimeIdxHover` pattern). Lift
`selectedTimeRange` into `Rides.tsx` next to `hoveredTimeIdx`, pass to
`RideMap`. Precedence rule: drag-zoom selection wins over `selectedLap` if
both are set (the drag is the more recent explicit action).

Phases 2-4 can land as a single PR (one feature, ~400 LOC frontend) or be
split into two PRs (Phase 2 alone, then Phases 3+4) if review feedback
suggests. House style (per recent campaigns) is one branch per plan, so
default is **one branch** — `worktrees/ride-map` → branch `feat/ride-map`.

---

## Files to touch

### Phase 1 (backend characterisation)
- `tests/integration/test_api.py` — **extend** with a single test that asserts
  the shape of `records[].lat`/`lon` on the seeded outdoor ride. No
  production-code edits.

### Phase 2 (static map)
**Frontend (production):**
- `frontend/package.json` — **add** `maplibre-gl` (only — no
  `react-map-gl` wrapper needed; we use the imperative API directly inside
  a single `useEffect`, matching the existing `chart.js` integration
  pattern).
- `frontend/src/components/RideMap.tsx` — **new** — the map component.
- `frontend/src/components/RideMap.css` — **new** — pulled from
  `maplibre-gl/dist/maplibre-gl.css` (copy-vendored, not imported from the
  package, to keep the lazy bundle clean) **or** imported via dynamic
  import. Decision deferred to implementation; either works.
- `frontend/src/pages/Rides.tsx` — **edit** — `React.lazy(() =>
  import('../components/RideMap'))` and render `<Suspense>` wrapper inside
  the ride detail pane between the timeline chart and the laps table.
- `frontend/src/lib/map.ts` — **new** — pure helpers:
  - `decimatePolyline(records: RideRecord[], maxPoints: number):
    [number, number][]` — returns `[lon, lat]` pairs (MapLibre uses
    GeoJSON ordering, **not** `[lat, lon]`).
  - `polylineBounds(coords: [number, number][]): [[number, number],
    [number, number]]` — `[[minLon, minLat], [maxLon, maxLat]]`.
  - `MAP_STYLE_URL` constant: reads
    `import.meta.env.VITE_MAP_TILE_STYLE_URL` with fallback
    `'https://tiles.openfreemap.org/styles/liberty'`.

**Frontend (tests):**
- `frontend/src/lib/map.test.ts` — **new** — unit tests for
  `decimatePolyline` and `polylineBounds`. Run via Vitest if configured;
  if not, fall back to a Node-only assertion script. (Confirm whether
  `frontend/` has a Vitest setup before writing — if not, defer to the
  Playwright spec only.)

**E2E:**
- `tests/e2e/03-rides.spec.ts` — **extend** — open the seeded outdoor
  ride, assert `canvas.maplibregl-canvas` is present and `getBoundingRect`
  is non-zero.

### Phase 3 (cursor sync)
**Frontend (production):**
- `frontend/src/components/RideTimelineChart.tsx` — **edit**:
  - Add optional prop `onTimeIdxHover?: (recordIdx: number | null) => void`.
  - In the chart options, add an `onHover` callback that translates the
    Chart.js `activeElements[0].index` (downsampled) to a full-resolution
    record index and calls `onTimeIdxHover(idx)`. On `mouseleave` the
    callback fires `null`. **Do not** wire this to the existing
    `selectionDataMap` — selection drag and hover scrub are independent.
- `frontend/src/components/RideMap.tsx` — **edit**:
  - Accept `hoveredTimeIdx: number | null` prop.
  - Render a `maplibregl.Marker` at `records[hoveredTimeIdx]`'s lat/lon
    when non-null.
  - When null, hide/remove the marker.
  - Marker is a small DOM element styled to match the codebase (8px
    circle, accent colour, white border).
- `frontend/src/pages/Rides.tsx` — **edit**:
  - Add `const [hoveredTimeIdx, setHoveredTimeIdx] = useState<number |
    null>(null)` next to existing hover/select state (line ~110).
  - Pass `onTimeIdxHover={setHoveredTimeIdx}` to `RideTimelineChart`.
  - Pass `hoveredTimeIdx={hoveredTimeIdx}` to `RideMap`.

**E2E:**
- `tests/e2e/03-rides.spec.ts` — **extend** — hover the chart at a known
  x-coordinate, assert that a `.maplibregl-marker` element exists in the
  DOM. (Asserting the marker's GPS position is brittle in E2E; existence
  is sufficient as a smoke test. Position correctness is covered by unit
  tests on `decimatePolyline` + manual smoke.)

### Phase 4 (lap highlighting + drag-zoom slice sync + indoor placeholder + responsive polish)
**Frontend:**
- `frontend/src/components/RideMap.tsx` — **edit**:
  - Accept `selectedLap: number | null`, `laps: RideLap[]`, and
    `selectedTimeRange: { startIdx: number, endIdx: number } | null`
    props (the time-range comes from the existing drag-to-zoom selection
    on `RideTimelineChart` — read `Rides.tsx` to find the actual state
    name; rename the prop to match if needed).
  - Compute a unified `focusSlice: { startIdx, endIdx } | null` from the
    inputs. Precedence rule: **most-recent action wins** (track which of
    `selectedLap` / `selectedTimeRange` was set last via a small effect
    or a parent-level `lastFocusSource` flag — keep it simple, document
    in a one-line comment). When neither is set, `focusSlice = null`.
  - When `focusSlice != null`, render a second polyline source coloured
    `#00d4aa` (full opacity) over the dimmed (25% opacity) full polyline,
    scoped to `[startIdx, endIdx]`. `fitBounds()` to the slice's GPS
    points with ~40px padding. When `focusSlice == null`, restore the
    full polyline at full opacity and `fitBounds()` to the whole route.
  - For `selectedLap`: compute the lap's record-index slice using the
    same `buildLapIndexMap` logic that already exists in
    `RideTimelineChart.tsx:25-64` — extract this to a shared helper in
    `frontend/src/lib/map.ts` rather than duplicating. The slice computed
    here feeds the unified `focusSlice` above.
- `frontend/src/components/RideMap.tsx` — **edit** — render an
  "Indoor ride — no GPS data" placeholder when `decimatePolyline()`
  returns fewer than 2 coordinates. The placeholder reuses the
  `RideTimelineChart`'s card styling for consistency.
- `frontend/src/pages/Rides.tsx` — **edit** — pass `selectedLap`,
  `selectedTimeRange` (the existing drag-zoom selection state — confirm
  the actual variable name in `Rides.tsx`), and
  `laps` to `<RideMap>`. Wrap the map card so the right-column layout
  (`grid-cols-1 lg:grid-cols-3`, line 551) places the map alongside the
  timeline chart on wide screens; the simplest layout is to put the map
  card immediately after the timeline-chart card, full width, so
  scrubbing works while looking at metrics in the row above.

**Refactor (optional, recommended):**
- `frontend/src/lib/map.ts` — **add** `buildLapIndexMap()` extracted from
  `RideTimelineChart.tsx:25-64` so both consumers (chart + map) call the
  same helper. Add a unit test in `frontend/src/lib/map.test.ts`.

---

## Step-by-step implementation details

### Prerequisites
- Local Podman Postgres running per `AGENTS.md`.
- `source venv/bin/activate` then `pip install -r requirements.txt`.
- `cd frontend && npm install`.
- A seeded outdoor ride exists in the test DB with non-NULL
  `ride_records.lat/lon`. **Verify** by running:
  ```sql
  SELECT r.id, COUNT(*) FILTER (WHERE rr.lat IS NOT NULL) AS gps_records
  FROM rides r JOIN ride_records rr ON rr.ride_id = r.id
  GROUP BY r.id HAVING COUNT(*) FILTER (WHERE rr.lat IS NOT NULL) > 0
  LIMIT 1;
  ```
  If empty, regenerate `tests/integration/seed/seed_data.json.gz` or use
  `tests/integration/seed/generate_recent.py:137` (already populates
  `start_lat`/`start_lon`, but check whether it also fills per-record GPS
  — if not, add a small synthetic polyline to the seed for E2E coverage).

---

### PHASE 1 — Backend characterisation test (Safety Harness)

#### Step 1.A — Lock the API contract
*Target file:* `tests/integration/test_api.py`.
*Test cases to write:*
1. `test_ride_detail_includes_per_record_gps`:
   - Hit `GET /api/rides/{seeded_outdoor_ride_id}`.
   - Assert response status 200.
   - Assert `len(payload["records"]) > 0`.
   - Assert at least one record has `lat` and `lon` non-null and within
     plausible Earth ranges (`-90 ≤ lat ≤ 90`, `-180 ≤ lon ≤ 180`).
   - Assert all `lat`/`lon` values are either both null or both non-null
     for any single record (no half-coords).
2. `test_ride_detail_indoor_returns_no_gps_records`:
   - Seed (or pick existing) a ride whose `ride_records` rows have
     `lat IS NULL AND lon IS NULL` for every record.
   - Hit `GET /api/rides/{indoor_ride_id}`.
   - Assert all records have `lat is None and lon is None`. The frontend
     map placeholder logic depends on this contract.

*Verification:*
```bash
./scripts/run_integration_tests.sh tests/integration/test_api.py -v -k gps
```
Both assertions must pass before any frontend work begins.

#### Phase 1 Definition of Done
- Two new tests in `tests/integration/test_api.py` green against the
  seeded test DB.
- No production code changed.
- The assertion `records[].lat/lon` is now formally part of the test
  suite — any future change that drops these columns from the SELECT will
  fail loudly.

---

### PHASE 2 — Static map (no cursor sync)

#### Step 2.A — Install MapLibre GL
*Action:*
```bash
cd frontend && npm install maplibre-gl
```
- Note the resulting `package-lock.json` change — the only new top-level
  dep is `maplibre-gl` (it bundles its own minimal deps).
- Confirm bundle impact: `npm run build` and check the `Built in` summary
  for the new gzipped size. Acceptable if delta ≤ 250 KB gzipped.

#### Step 2.B — Add `frontend/src/lib/map.ts` (pure helpers)
*Target file:* `frontend/src/lib/map.ts` (new).
*Exact functions:*
```ts
import type { RideRecord } from '../types/api'

export const MAP_STYLE_URL =
  (import.meta.env.VITE_MAP_TILE_STYLE_URL as string | undefined)
  ?? 'https://tiles.openfreemap.org/styles/liberty'

/**
 * Reduce records to at most maxPoints [lon, lat] pairs (GeoJSON order)
 * by uniform stride sampling. Skips records with null lat/lon.
 * Returns [] if fewer than 2 valid GPS points exist.
 */
export function decimatePolyline(
  records: Pick<RideRecord, 'lat' | 'lon'>[],
  maxPoints = 600,
): [number, number][] {
  const valid = records.filter(
    (r): r is { lat: number; lon: number } =>
      typeof r.lat === 'number' && typeof r.lon === 'number',
  )
  if (valid.length < 2) return []
  if (valid.length <= maxPoints) return valid.map(r => [r.lon, r.lat])
  const step = Math.ceil(valid.length / maxPoints)
  const out: [number, number][] = []
  for (let i = 0; i < valid.length; i += step) out.push([valid[i].lon, valid[i].lat])
  // Always include the final point so the polyline ends where the ride did
  const last = valid[valid.length - 1]
  if (out[out.length - 1][0] !== last.lon || out[out.length - 1][1] !== last.lat) {
    out.push([last.lon, last.lat])
  }
  return out
}

/**
 * Compute the SW/NE bounding box for a list of [lon, lat] coords.
 * Returns null if coords is empty.
 */
export function polylineBounds(
  coords: [number, number][],
): [[number, number], [number, number]] | null {
  if (coords.length === 0) return null
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
  for (const [lon, lat] of coords) {
    if (lon < minLon) minLon = lon
    if (lon > maxLon) maxLon = lon
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }
  return [[minLon, minLat], [maxLon, maxLat]]
}
```

#### Step 2.C — Unit tests for the helpers
*Target file:* `frontend/src/lib/map.test.ts` (new).

**First, verify `frontend/` has a unit-test runner.** Inspect
`frontend/package.json`'s `scripts` and `devDependencies` — if Vitest is
absent, install it (`npm install -D vitest`) and add a `"test": "vitest
run"` script. If that adds friction, fall back to writing the assertions
into the Playwright suite as a `test.describe('decimatePolyline (pure)',
…)` block running in Node context — but Vitest is the right tool.

*Test cases:*
- `decimatePolyline([])` → `[]`.
- `decimatePolyline([{ lat: 42, lon: -71 }])` → `[]` (need ≥2 points).
- `decimatePolyline([{ lat: 42, lon: -71 }, { lat: 42.1, lon: -71.1 }])` →
  `[[-71, 42], [-71.1, 42.1]]` (note `[lon, lat]` order).
- A synthetic 1500-point list with all-valid GPS, `maxPoints=600` → result
  length is between 600 and 602 (allows for the always-include-last
  guarantee). First and last coords match input.
- A list of 100 records where every other one has `lat: null` →
  result length 50 (drops nulls). Order preserved.
- `polylineBounds([])` → `null`.
- `polylineBounds([[-71.5, 42.0], [-71.0, 42.5]])` →
  `[[-71.5, 42.0], [-71.0, 42.5]]`.

*Verification:*
```bash
cd frontend && npm run test -- map.test.ts
```

#### Step 2.D — Build the `<RideMap>` component (static polyline only)
*Target file:* `frontend/src/components/RideMap.tsx` (new).
*Structural code:*
```tsx
import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Map as MapIcon } from 'lucide-react'
import type { RideRecord } from '../types/api'
import { MAP_STYLE_URL, decimatePolyline, polylineBounds } from '../lib/map'

interface Props {
  records: RideRecord[]
}

export default function RideMap({ records }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const coords = decimatePolyline(records, 600)
    if (coords.length < 2) return  // placeholder handled in render below

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      attributionControl: { compact: true },
    })
    mapRef.current = map

    map.on('load', () => {
      map.addSource('route', {
        type: 'geojson',
        data: { type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: {} },
      })
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#00d4aa', 'line-width': 3, 'line-opacity': 0.9 },
      })
      const bounds = polylineBounds(coords)
      if (bounds) map.fitBounds(bounds, { padding: 40, duration: 0 })
    })

    return () => { map.remove(); mapRef.current = null }
  }, [records])

  const coordsForPlaceholder = decimatePolyline(records, 2)
  if (coordsForPlaceholder.length < 2) {
    return (
      <section className="bg-surface rounded-xl border border-border p-8 text-center text-text-muted">
        <MapIcon size={32} className="mx-auto mb-3 opacity-30" />
        <p className="text-xs font-medium">No GPS data — indoor or virtual ride</p>
      </section>
    )
  }

  return (
    <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
        <MapIcon size={16} className="text-accent" />
        <h2 className="text-sm font-bold text-text uppercase tracking-wider">Route</h2>
      </div>
      <div ref={containerRef} className="h-64 sm:h-80 w-full" />
    </section>
  )
}
```

#### Step 2.E — Wire it into `Rides.tsx`
*Target file:* `frontend/src/pages/Rides.tsx`.
*Exact change:*
- At the top with other imports, add:
  ```tsx
  const RideMap = lazy(() => import('../components/RideMap'))
  ```
  (and `import { lazy, Suspense } from 'react'` if not already there).
- Inside the ride-detail pane, immediately **after** the `RideTimelineChart`
  block at lines 538-549, add:
  ```tsx
  {ride.records && ride.records.length > 0 && (
    <Suspense fallback={<div className="h-64 sm:h-80 bg-surface rounded-xl border border-border animate-pulse" />}>
      <RideMap records={ride.records} />
    </Suspense>
  )}
  ```

#### Step 2.F — E2E smoke
*Target file:* `tests/e2e/03-rides.spec.ts`.
*Test case:*
```ts
test('ride detail shows route map for outdoor rides', async ({ page }) => {
  // Navigate to a known outdoor ride id (use the same lookup pattern as
  // existing tests in this file — pick the first ride with non-zero
  // total_ascent which is a reasonable proxy for "has GPS").
  // ... existing nav code ...
  const mapCanvas = page.locator('canvas.maplibregl-canvas')
  await expect(mapCanvas).toBeVisible({ timeout: 10000 })
  const box = await mapCanvas.boundingBox()
  expect(box?.width).toBeGreaterThan(100)
  expect(box?.height).toBeGreaterThan(100)
})
```

*Verification:*
```bash
./scripts/run_e2e_tests.sh -g "route map"
```

#### Phase 2 Definition of Done
- `RideMap` renders the polyline for any seeded outdoor ride.
- Indoor rides show the placeholder.
- `npm run build` is clean (no TS errors); bundle size delta ≤ 250 KB
  gzipped.
- E2E spec passes against the seeded test DB.
- **Lazy-chunk verification (mandatory):** after `npm run build`, inspect
  `frontend/dist/assets/` and confirm:
  1. There is a separate chunk file whose name contains `RideMap` (e.g.
     `RideMap-XXXX.js`) and that this chunk also contains the
     `maplibre-gl` bundle (look for `maplibregl` symbols, or check the
     chunk's gzipped size — it should be ~220 KB+).
  2. The main entry chunk (`index-XXXX.js`) does **NOT** contain
     `maplibregl` symbols. Verify with:
     ```bash
     cd frontend && npm run build
     # Should match RideMap chunk only:
     grep -l 'maplibregl' dist/assets/*.js
     # Should output ZERO matches:
     grep -l 'maplibregl' dist/assets/index-*.js
     ```
  3. Record the actual chunk filename and gzipped size in the PR
     description. If MapLibre ends up in the main bundle, Phase 2 is
     **not** done — fix the lazy import before proceeding to Phase 3.

---

### PHASE 3 — Cursor sync (chart hover → map marker)

#### Step 3.A — Extend `RideTimelineChart` with `onTimeIdxHover`
*Target file:* `frontend/src/components/RideTimelineChart.tsx`.
*Change:*
1. Add `onTimeIdxHover?: (recordIdx: number | null) => void` to the
   `Props` interface (after `selectedLapIndex`).
2. Destructure it in the function signature.
3. Inside the chart `options.onHover` (add a new option — there is no
   existing onHover):
   ```ts
   onHover: (_evt, activeEls) => {
     if (!onTimeIdxHover) return
     if (activeEls.length === 0) { onTimeIdxHover(null); return }
     const idx = activeEls[0].index  // downsampled index
     onTimeIdxHover(idx * downsampleStep)
   },
   ```
4. Also ensure the chart canvas's `onMouseLeave` fires `onTimeIdxHover(null)`.
   The existing `canvas.addEventListener('mouseleave', onUp)` block
   (line 190) is for selection-drag — wire a sibling listener for hover
   reset, OR (cleaner) put the listener inside the same effect.

**Critical:** The `onTimeIdxHover` plumbing must NOT cause a re-render of the
chart. The chart already updates imperatively via `chartRef.current.update`
(line 151) for the highlight plugin; emitting a callback that updates the
*parent's* state is fine because the parent only passes it back to
`RideMap`, not back to the chart. Verify by adding a `useRef`-tracked render
counter to the chart in dev mode and confirming mouse-move does not
increment it.

#### Step 3.B — Add the marker to `RideMap`
*Target file:* `frontend/src/components/RideMap.tsx`.
*Change:*
1. Add `hoveredTimeIdx?: number | null` to the `Props` interface and
   destructure it.
2. Add a second `useRef<maplibregl.Marker | null>` for the marker.
3. Add a new `useEffect` that runs whenever `hoveredTimeIdx` changes:
   ```tsx
   useEffect(() => {
     const map = mapRef.current
     if (!map) return
     if (hoveredTimeIdx == null || !records[hoveredTimeIdx]) {
       markerRef.current?.remove()
       markerRef.current = null
       return
     }
     const r = records[hoveredTimeIdx]
     if (typeof r.lat !== 'number' || typeof r.lon !== 'number') {
       markerRef.current?.remove()
       markerRef.current = null
       return
     }
     if (!markerRef.current) {
       const el = document.createElement('div')
       el.style.cssText = 'width:14px;height:14px;border-radius:50%;background:#00d4aa;border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,0.4)'
       markerRef.current = new maplibregl.Marker({ element: el })
         .setLngLat([r.lon, r.lat])
         .addTo(map)
     } else {
       markerRef.current.setLngLat([r.lon, r.lat])
     }
   }, [hoveredTimeIdx, records])
   ```
4. **Do NOT** call `map.panTo()` or `map.flyTo()` on hover. Auto-pan during
   scrub is jarring. The user can manually pan if needed.

#### Step 3.C — Wire state in `Rides.tsx`
*Target file:* `frontend/src/pages/Rides.tsx`.
*Change:*
1. Add state next to the existing hover state (line ~110-113):
   ```tsx
   const [hoveredTimeIdx, setHoveredTimeIdx] = useState<number | null>(null)
   ```
2. Pass `onTimeIdxHover={setHoveredTimeIdx}` to `<RideTimelineChart>` (line ~540).
3. Pass `hoveredTimeIdx={hoveredTimeIdx}` to `<RideMap>`.

#### Step 3.D — Manual smoke test
1. `./scripts/dev.sh`.
2. Open Rides → pick an outdoor ride with GPS.
3. Move the mouse slowly across the timeline chart from left to right.
4. **Expected:** the green marker on the map glides along the polyline
   from the ride's start to its finish in sync with the cursor.
5. Move the mouse off the chart. Marker disappears.
6. Test on a long ride (>2h) — marker should not stutter.
7. Test on a ride with the existing zoom-to-lap feature engaged — marker
   should still track within the zoomed segment.

#### Step 3.E — E2E smoke
*Target file:* `tests/e2e/03-rides.spec.ts`.
*Test case:*
```ts
test('hovering timeline chart shows marker on map', async ({ page }) => {
  // Navigate to outdoor ride as above
  const chart = page.locator('canvas').first()  // chart is the first canvas
  const box = await chart.boundingBox()
  if (!box) throw new Error('chart not found')
  await chart.hover({ position: { x: box.width * 0.5, y: box.height * 0.5 } })
  // Marker is a div appended by maplibre's Marker constructor
  await expect(page.locator('.maplibregl-marker')).toBeVisible({ timeout: 5000 })
})
```

#### Phase 3 Definition of Done
- Hovering the timeline chart smoothly moves a marker along the route.
- Mouse-leave clears the marker.
- E2E case green.
- No new chart re-renders introduced (verified manually with React DevTools
  Profiler — the chart re-render count during hover should be 0).

---

### PHASE 4 — Lap highlighting + polish

#### Step 4.A — Extract `buildLapIndexMap` to shared lib
*Target files:*
- `frontend/src/lib/map.ts` — add `buildLapIndexMap(...)` lifted verbatim
  from `RideTimelineChart.tsx:25-64`. The function as-it-exists is pure
  (no React deps), so this is a move + export.
- `frontend/src/components/RideTimelineChart.tsx` — replace the inline
  function with `import { buildLapIndexMap } from '../lib/map'`. Remove
  the inline copy.
- `frontend/src/lib/map.test.ts` — add a unit test for
  `buildLapIndexMap` covering: timestamp-based path, elapsed-time
  fallback path, single-lap edge case, no-records edge case.

*Verification:* All existing chart tests still green; new map.test.ts cases
pass. **This is a refactor under harness — Phase 1's Step 1.A test plus the
existing Phase 3 E2E case should still pass unchanged.**

#### Step 4.B — Highlighted lap polyline + recentre
*Target file:* `frontend/src/components/RideMap.tsx`.
*Change:*
1. Add props `selectedLap?: number | null` and `laps: RideLap[]`.
2. In a new `useEffect` keyed on `selectedLap`:
   - When `selectedLap == null`, ensure the highlight source is empty and
     refit the map to `polylineBounds(coords)`.
   - When `selectedLap != null`:
     - Compute the slice of `records` belonging to that lap using
       `buildLapIndexMap(records.length, 1, records, laps)` — note we pass
       `downsampleStep=1` here (we need full-res indices, not chart-sampled).
     - Build the slice's `[lon, lat]` coords.
     - Update a `route-highlight` source with that GeoJSON line (add the
       source on map load if not present).
     - `map.fitBounds(polylineBounds(sliceCoords), { padding: 40, duration: 400 })`.

3. Style: full polyline at `line-color: '#00d4aa', line-opacity: 0.25`
   when a lap is selected; highlight slice at `line-color: '#00d4aa',
   line-opacity: 1.0, line-width: 5`.

#### Step 4.C — Wire `selectedLap` from `Rides.tsx`
*Target file:* `frontend/src/pages/Rides.tsx`.
*Change:* Pass `selectedLap={selectedLap}` and `laps={ride.laps}` to
`<RideMap>`. (No new state — `selectedLap` is already on the page.)

#### Step 4.D — Manual smoke test
1. Open an outdoor ride with multiple laps.
2. Click a lap row → map recentres on that lap; the lap's polyline
   stays bright, the rest of the route dims.
3. Click the lap row again (or click "reset" if the existing UX has one)
   → map zooms back to the full route.
4. Hover-scrub the timeline chart while a lap is selected — marker still
   tracks.
5. Open an indoor ride → placeholder card renders (no map canvas).

#### Phase 4 Definition of Done
- Lap selection on the laps table recentres + dims-and-highlights on the
  map.
- **Drag-selecting a time range on the timeline chart** highlights the
  corresponding polyline slice on the map (full opacity slice over a 25%
  dimmed full polyline) and `fitBounds()`-zooms the map to the slice.
- **Clearing the selection** (chart's existing clear behaviour) restores
  the full polyline at full opacity and `fitBounds()` to the whole route.
- When both `selectedLap` and `selectedTimeRange` are set, most-recent
  wins (documented as a one-line comment in `<RideMap>`).
- The shared `buildLapIndexMap` helper has unit-test coverage and is no
  longer duplicated.
- Indoor rides show the placeholder card.
- E2E covers the drag-zoom → map sync flow (drag to select, assert the
  highlighted polyline source becomes visible and the map's centre
  shifts).
- No regressions in Phase 2/3 tests.

---

## Test Plan Summary

| Layer | What we test | Where |
| --- | --- | --- |
| Integration | `GET /api/rides/{id}` returns per-record lat/lon for outdoor rides | `tests/integration/test_api.py` |
| Integration | `GET /api/rides/{id}` returns null lat/lon for indoor rides | `tests/integration/test_api.py` |
| Unit (FE) | `decimatePolyline` — empty, single, full-res, with-nulls | `frontend/src/lib/map.test.ts` |
| Unit (FE) | `polylineBounds` — empty, single point, multiple points | `frontend/src/lib/map.test.ts` |
| Unit (FE) | `buildLapIndexMap` — timestamp + elapsed fallback paths | `frontend/src/lib/map.test.ts` |
| E2E | Outdoor ride detail renders the map canvas | `tests/e2e/03-rides.spec.ts` |
| E2E | Hover on timeline chart causes a `.maplibregl-marker` to appear | `tests/e2e/03-rides.spec.ts` |
| Manual | Marker tracks smoothly on a long (>2h) ride | browser |
| Manual | Lap click recentres + highlights | browser |
| Manual | Indoor ride shows the placeholder card, not a broken map | browser |
| Manual | OpenFreeMap "liberty" tiles label trails on a known MTB ride | browser |

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| OpenFreeMap goes down or rate-limits us | Low (donation-funded, stable since 2024) | `VITE_MAP_TILE_STYLE_URL` env var lets us swap to Thunderforest, Mapbox, or self-hosted in one config change |
| MapLibre GL bundle bloat | Medium | Lazy-load via `React.lazy`; ~220 KB gzipped is acceptable as a deferred chunk |
| Marker stutter on long rides during scrub | Medium | Marker updates are imperative (`setLngLat`), not React-render-driven; throttling via `requestAnimationFrame` is a deferred optimisation if measured |
| Historical ICU rides have no per-record GPS | High (known, documented) | Placeholder card renders cleanly; no JS error. Backfill is explicitly out of scope (would need ride-by-ride re-fetch). |
| Lap-slice computation diverges from chart's lap highlight | Low | Single shared `buildLapIndexMap` helper after Phase 4.A refactor — both consumers call it; mismatch is impossible by construction |
| `onTimeIdxHover` causes chart re-render storm | Low | Verified manually with React DevTools Profiler in Step 3.D; if it does re-render we move the callback to a `useRef`-stored function and memoise |
| OpenFreeMap "liberty" style omits a specific named trail at z14 | Medium | Acceptable for v1. Follow-up: fork the style JSON and lower the path-label minzoom |
| Indoor ride placeholder triggers on outdoor ride with sparse GPS (e.g. tunnel ride) | Low | Threshold is "≥ 2 valid GPS points", which is permissive. A purely-tunnel ride is pathological; document and move on |
| MapLibre + Vite SSR collision | Low | This codebase ships a pure SPA (Vite, no SSR). Confirmed by checking `frontend/vite.config.ts` (no `ssr` config). |

---

## Resolved Decisions (locked in 2026-04-22)

User confirmed all six original open questions. Decisions are baked into
the plan above; recorded here for the audit trail.

1. **Tile provider:** OpenFreeMap "liberty" vector tiles + MapLibre GL JS.
   No paid fallback needed at current scale.
2. **Bundle size:** ~220 KB gzipped MapLibre addition is acceptable
   **on the strict condition** that it is lazy-loaded into its own chunk
   and never appears in the main entry bundle. See Phase 2 DoD for the
   verification step.
3. **Indoor / no-GPS rides** are a **first-class** state, not an error.
   The map card is hidden entirely (no broken widget, no error toast)
   for any ride where `records[]` has no usable lat/lon points. This
   covers both indoor rides (trainer / Zwift / virtual rides — naturally
   have no GPS) and pre-Campaign-17 ICU rides whose streams pre-date the
   parser fix. Both render identically: no map card. The placeholder
   message inside the card (Step 2.D in implementation details) reads
   "No GPS data — indoor or virtual ride".
4. **"Pin" via existing drag-zoom selection** — the user clarified that
   the existing drag-to-select-zoom on the timeline chart (which already
   updates a time-range state on `Rides.tsx`) IS the pin mechanism. No
   new `selectedTimeIdx` state is needed. Phase 4 propagates the existing
   drag-selection to `<RideMap>` to (a) highlight the polyline slice
   (full opacity slice, 25% dim rest — same treatment as lap highlight)
   and (b) `fitBounds()` the map to the slice. Clearing the selection
   restores the full view. Lap-selection vs. drag-selection precedence:
   pick a single rule in code (most-recent wins is the simplest) and
   document it as a one-line comment in `<RideMap>`.
5. **Auto-pan on hover-scrub:** disabled by default (vertigo concern). A
   "follow cursor" opt-in toggle is **not** in scope for Campaign 20 —
   tracked as Campaign 21. (Auto-fit-bounds on the deliberate drag-zoom
   selection from #4 is a different case and IS in scope; the vertigo
   concern is specific to continuous hover movement, not deliberate
   user actions.)
6. **Lap-highlight UX:** dim non-selected polyline to 25% opacity,
   selected lap at full opacity, matching existing chart behaviour.

---

## Branch Name Suggestion

Single branch — house style for one campaign:
- Worktree: `worktrees/ride-map`
- Branch: `feat/ride-map`

Phases 2-4 land as one PR by default. Split Phase 2 into its own PR only
if review feedback on the standalone static-map step is sought before
investing in cursor sync.

---

# CAMPAIGN 20 EXPANSION (added 2026-04-22): GPS Data-Quality Foundation

## Why this expansion (read first)

While verifying Campaign 20's map UI against real production rides, we
discovered that the **map UI is correct but the underlying per-record GPS
data is corrupted for many ICU-synced rides**. Two corruption variants
were observed in the wild:

* **Variant A — exact `lat == lon`** (e.g. ride `3236`, Fruita CO,
  4/13/2026): `start_lat=39.31, start_lon=-108.71` is correct
  (FIT-laps-derived, fixed in commit `266c925`), but every
  `ride_records[i]` row stores `lat=39.31, lon=39.31`. The map renders
  a perfect diagonal in the wrong country.
* **Variant B — `lat ≈ lon` with sub-degree noise** (e.g. ride `3237`):
  same shape — both columns latitude-like — but the values vary by
  small fractions, producing a curvy blob that loosely resembles a
  route but isn't it.

**Empirical root cause** — confirmed by hitting ICU directly for ride
`3238`:

```
streams.latlng length: 7003 (odd)
first 5 elements: [39.750404, 39.750404, 39.75041, 39.75041, 39.750412]
last 5 elements:  [39.7504,   39.750404, 39.750404, 39.75041, 39.75041]
second-half average: 39.718  ← still latitudes
```

ICU's `latlng` stream returned **only latitudes — no longitudes
anywhere in the array**. Pattern: `[lat1, lat1, lat2, lat2, ..., lat1]`
(each lat repeated, plus one trailing element giving an odd length).

The Campaign 17 fix in `b6637ed`/`266c925` (`fix(sync): correctly parse
ICU latlng stream and use FIT laps for GPS backfill`) only handled the
`[all_lats..., all_lons...]` concatenated variant **and** only recovered
ride-level `start_lat/lon` (via FIT *lap* messages). Per-record GPS in
`ride_records` was never touched by that fix and is corrupted on every
ICU-synced ride that hit this newer variant — both the rides synced
before the Campaign 17 fix *and* rides synced after it (the fix simply
doesn't apply to lat-only stream payloads). The current parser at
`server/services/sync.py:_normalize_latlng` (≈line 229) requires
`n % 2 == 0` for the concatenated-format heuristic, so a 7003-element
payload falls through to the alternating-pairs branch and produces
`(lat, lat)` pairs.

**User directive (verbatim, 2026-04-22):**
> *I want to expand this campaign to address that fundamental fix.
> (1) FIT is primary, (2) Streams backup when no FIT; has to fix the
> lat/lon, etc... (3) Speed smoothing should happen in our libraries,
> we probably already do some smoothing/averaging with python libraries
> to get tss, power, etc... I also want a plan to fix all the
> historical values, we need a 1 time data migration for this.*

This is folded into Campaign 20 (per user instruction — not a separate
Campaign 23) and will ship in the same release as the map work.

---

## Investigation summary for the data-quality work (already done — read-only)

* **`server/services/sync.py`**
  * `_normalize_latlng` (lines ≈229-274): three-format parser. The
    concatenated-format detector at line 258 hard-requires `n % 2 == 0`
    and an `r0 ≈ r1` 1° proximity check. The lat-only Variant B above
    has `n=7003` (odd) AND `r0 ≈ r1` — currently falls through to
    alternating-pairs interpretation, producing `(lat, lat)` pairs.
  * `_extract_streams` (lines ≈277-301): normalises ICU stream
    response into `{type: list}`. Used both by `_store_streams` and the
    backfill scripts.
  * `_store_streams` (lines ≈304-354): inserts one row per
    `time` sample into `ride_records` from the ICU streams response.
    All non-GPS columns (power, hr, cadence, velocity_smooth, altitude,
    distance, temperature) come from the corresponding ICU stream.
  * `_backfill_start_location` (lines ≈357-386): writes ride-level
    `start_lat/lon` from the **first valid stream point**.
  * `_backfill_start_from_laps` (lines ≈389-422): the Campaign 17 fix.
    Writes ride-level `start_lat/lon` from FIT lap 0's
    `start_position_lat/long`. Already deployed and working —
    correctly fires for any ride where `start_lat` is NULL or matches
    the `ABS(start_lat-start_lon) < 1°` corruption signature.
* **`server/services/intervals_icu.py`**
  * `fetch_activity_streams` (lines ≈190-208): GETs
    `/api/v1/activity/{id}/streams` with
    `types=time,watts,heartrate,cadence,velocity_smooth,altitude,distance,latlng`.
  * `fetch_activity_fit_laps` (lines ≈222-297): GETs
    `/api/v1/activity/{id}/file` (the original FIT), parses with
    `fitparse.FitFile(...).get_messages("lap")`, throws away every
    other message type. **The same FIT file contains the per-record
    `record` messages with `position_lat/position_long` semicircles** —
    we are downloading and discarding them today.
  * `_semicircles_to_degrees` (lines ≈212-218): the semicircle→degrees
    conversion is already implemented (`val * (180 / 2**31)` for
    `abs(val) > 180`).
  * Returns 200 + a binary FIT file when one exists; non-200 (often
    404) for activities that have no original FIT (manually-created
    ICU activities, some Strava-imported ones, some non-FIT-device
    exports).
* **`server/ingest.py`**
  * `parse_ride_json` already converts FIT JSON `record[i]` to
    `(lat, lon)` via `_semicircles_to_degrees` at lines ≈233-234. The
    same conversion path is exactly what we need for ICU re-sync.
* **`server/services/single_sync.py`**
  * `import_specific_activity` (re-sync of a single ride). Currently
    calls `fetch_activity_streams` then `_store_streams`,
    `_backfill_start_location`, `fetch_activity_fit_laps`,
    `_store_laps`, `_backfill_start_from_laps`. **This is the function
    we will retarget at FIT-records-primary** — both the bulk sync
    (`_download_rides`) and the per-ride re-sync paths must converge
    on the same primitive.
* **`server/metrics.py`**
  * `clean_ride_data` (lines ≈58-157): rolling Z-score outlier
    removal + 5/3-sample median filter for power, HR, cadence.
    Uses `scipy.signal.medfilt` and `scipy.ndimage.uniform_filter1d`.
  * `calculate_np` (lines ≈159-178): 30-sample rolling mean (the NP
    "30 second rolling average").
  * `compute_rolling_best` (lines ≈191-222): vectorised sliding-window
    sums via `np.convolve`.
  * **No equivalent for speed today** — `velocity_smooth` is consumed
    raw from ICU and stored verbatim in `ride_records.speed`. This is
    Pillar 3's gap.
* **Schema (`migrations/0001_baseline.sql:53-66`):**
  ```sql
  CREATE TABLE IF NOT EXISTS ride_records (
      id SERIAL PRIMARY KEY,
      ride_id INTEGER NOT NULL REFERENCES rides(id),
      timestamp_utc TEXT,
      power INTEGER,
      heart_rate INTEGER,
      cadence INTEGER,
      speed REAL,
      altitude REAL,
      distance REAL,
      lat REAL,
      lon REAL,
      temperature REAL
  );
  ```
* **Existing parser tests:** `tests/unit/test_sync_latlng.py` covers
  empty / nested / flat-alternating / concatenated / odd-truncate /
  zero-prefix and three `_store_streams` / four
  `_backfill_start_location` cases. **Missing coverage:** the
  lat-only "Variant B" payload that triggered this bug. Phase 7 adds
  that.
* **Frontend `RideRecord` type** (`frontend/src/types/api.ts:37-48`)
  already includes optional `lat`/`lon`/`speed`. **No type or response
  schema change is required for the data-quality work.**

---

## Resolved Decisions (data-quality expansion, locked 2026-04-22)

These decisions are made by the architect after investigation; the
engineer should not relitigate them without a documented reason.

### D1 — FIT-vs-streams precedence (per field)

For ICU-synced rides where the FIT file is downloadable, **FIT records
are the primary source for every per-record field below**. Streams are
the fallback ONLY when the FIT download returns non-200, when FIT
parsing throws, or when the FIT file has zero `record` messages.

| Field | Primary | Fallback (no FIT) | Why |
|---|---|---|---|
| `lat`, `lon` | **FIT** (`position_lat`/`long` semicircles) | Streams `latlng` (with the Phase 7 hardened parser) | FIT semicircles are unambiguous; streams `latlng` has at least 3 known shape variants and now a fourth (lat-only) — that's the bug |
| `timestamp_utc` | **FIT** (`record.timestamp`) | Synthesised from `time` stream + ride `start_time` | FIT carries true UTC timestamps per sample; streams `time` is offset-from-start only |
| `power` | **FIT** (`record.power`) | Streams `watts` | FIT is the device's recording. Equal fidelity but FIT is authoritative; consistency win — every field comes from one source |
| `heart_rate` | **FIT** (`record.heart_rate`) | Streams `heartrate` | Same reasoning as power |
| `cadence` | **FIT** (`record.cadence`) | Streams `cadence` | Same |
| `altitude` | **FIT** (`record.enhanced_altitude` ?? `record.altitude`) | Streams `altitude` | FIT enhanced_altitude is barometric-corrected on most modern Garmins; preserves resolution that ICU sometimes downsamples in the streams API |
| `distance` | **FIT** (`record.distance`) | Streams `distance` | Same as power/HR |
| `speed` | **FIT** (`record.enhanced_speed` ?? `record.speed`) → then **smooth in our pipeline** (Phase 8) | Streams `velocity_smooth` (raw, no extra smoothing) | We want consistent smoothing controlled by us; ICU's `velocity_smooth` window is undocumented and varies. See D3 |
| `temperature` | **FIT** (`record.temperature`) | Streams `temp` if present, else NULL | Same |

**Implementation note:** when FIT is the source we ignore the streams
response entirely for `_store_streams`'s job (per-record write).
Streams are still needed for the metric pipeline today
(`process_ride_samples`) which expects power/HR/cadence as flat lists —
those will be derived from the FIT records list instead, so the
metrics pipeline keeps the same input shape but a different upstream
producer.

### D2 — No new schema columns (provenance is logged, not stored)

We will **not** add a `gps_source` (or any other "where did this
column come from") field to `ride_records` or `rides`. Justification:

* The corruption is detectable post-hoc by a deterministic signature
  (`abs(lat - lon) < 1°` for >50% of records — see D4).
* A provenance flag on every row (10k×N rides) is a 4-byte-per-row
  permanent tax to debug a one-shot bug.
* For one-shot debugging during the rollout we add structured logs
  (`logger.info("gps_source", ride_id=..., source=...)`) on the sync
  path. Logs persist in Cloud Logging long enough for any forensic
  follow-up.

If a future bug requires the flag we can fix forward with a migration
that backfills it from the most-recent sync log.

### D3 — Speed smoothing: 5-sample rolling mean, NaN-aware

In `server/metrics.py` add a new pure helper `smooth_speed(speed_array,
window=5)` that:

* Accepts a list/array of `float | None`, returns a list of `float |
  None`.
* Treats `None` and `NaN` as missing; uses linear interpolation for
  gaps `< 10` consecutive samples (matches the existing
  `clean_ride_data` policy at `server/metrics.py:77-90`).
* Applies `scipy.ndimage.uniform_filter1d(arr, size=5)` (centred
  5-sample boxcar — visually equivalent to a 5-second window for
  1 Hz data, which all FIT records and ICU streams are).
* Re-inserts `None` at positions that were originally missing AND
  whose surrounding gap exceeded 10 samples (i.e. don't fabricate
  values across long stops).

Why 5, not the 30 we use for NP? NP needs a long window to suppress
fast-twitch power transients without losing the metabolic envelope.
Speed only needs to suppress GPS-jitter spikes — a 5-second window
feels smooth on a chart without lagging the actual decel/accel
behaviour. The number is chosen empirically; if the engineer finds it
too aggressive or too lax during Phase 8 the constant lives in
exactly one place.

The smoothed series is stored in `ride_records.speed` and surfaces
through the existing `RideRecord.speed` field — no API or frontend
change required.

### D4 — Corruption-detection signature & threshold

A ride's per-record GPS is considered **corrupt** when, of all
records that have non-NULL `lat` AND non-NULL `lon`, **more than 50%
satisfy `ABS(lat - lon) < 1.0`**.

Reasoning:

* For real outdoor rides outside the equator/prime-meridian
  intersection, `ABS(lat - lon) ≥ 5°` everywhere on populated land.
  US: lat 25-49, lon -67..-125 → `ABS` always > 25. Europe: lat
  35-71, lon -10..40 → `ABS` always > 1 (and almost always > 30).
* Real rides in the corruption-friendly band (lat≈lon within 1° —
  e.g. parts of Brazil where lat≈-7 and lon≈-7 is plausible) exist
  but are rare *and* still won't have **every** record meeting the
  threshold (a 30 km ride spans ≥0.27° of latitude — points spread
  across the threshold).
* Variant A (exact `lat == lon`) trivially hits 100% of records.
  Variant B (lat≈lon noisy) typically hits 100% of records — the
  noise is sub-degree.
* `> 50%` (rather than `> 95%`) tolerates partial corruption (e.g.
  a ride whose stream has half good data and half lat-only) and
  catches rare future variants while staying safely above the
  natural-coincidence rate.

The threshold lives in one constant in
`scripts/backfill_corrupt_gps.py` (Phase 9) and is also reused by
the frontend safeguard (Phase 10) and a new defensive runtime check
in `_store_streams` (Phase 7). Three call sites, one constant.

### D5 — Backfill safety model

Mirrors `scripts/backfill_ride_start_geo.py`:

* `--dry-run` is the **default** mode. Reads only.
* `--allow-remote` is required if `CYCLING_COACH_DATABASE_URL` is
  not localhost (`localhost`, `127.0.0.1`, `::1`).
* `--sleep` (default 0.5s) between ICU API calls to respect rate
  limits.
* `--limit N` to backfill at most N rides per invocation (resumability).
* Idempotent: a ride re-flagged as corrupt after partial success
  is safe to re-process; `_store_records_from_fit` deletes existing
  `ride_records` for that ride first inside a transaction.
* Outputs a JSON summary at the end:
  `{total_examined, total_corrupt, fixed, fit_unavailable,
  fit_parse_failed, icu_api_error, skipped_already_clean}`.
* The architect MUST never run this script during planning. The
  engineer runs it locally first; only after a green dry-run + a
  green non-dry-run against the local Podman DB does anyone consider
  prod.

### D6 — Phasing strategy

The C20 map UI (Phases 1-4) has shipped to `feat/ride-map`. Phases
5-10 are additive and shipped on the same branch in this exact
order. Each phase is independently reversible (each is a small,
self-contained PR-or-commit set). No phase breaks the existing map UI.

### D7 — Scope of the frontend safeguard (Phase 10)

The frontend gets a small additive safeguard: when the corruption
signature (D4) fires on the `records[]` it just received, the
`<RideMap>` component renders a one-line warning banner *over* the
polyline rather than rendering a wrong polyline silently. The banner
text:

> "GPS data appears corrupted for this ride. Re-sync the ride to fix
> (Settings → Sync → Re-sync this ride)."

This is **belt-and-suspenders** — once Phase 9 backfills production,
the banner should never fire on real data. But it buys safety while
the backfill runs, and remains a useful diagnostic for any future
parser variant we miss.

### D8 — `velocity_smooth` retirement (cycling sports only)

When FIT is the source, do not also pull `velocity_smooth` from
streams — derive `speed` from FIT records (D1 row 8), then run
`smooth_speed` on the result (D3). When the streams fallback fires
(no FIT), prefer `velocity_smooth` if present, else `velocity` /
`speed` (raw), then smooth via the same `smooth_speed` helper.
Single output shape downstream.

### D9 — What is intentionally OUT of scope (still)

Carried forward from the existing C20 plan, plus new exclusions
from the data-quality expansion:

* **Per-record GPS for non-ICU sources** (legacy JSON-FIT-import
  files in `data/json/`): already correct because `parse_ride_json`
  already uses semicircles. No change.
* **Re-deriving lap data from FIT records.** We continue to use FIT
  `lap` messages for lap timing (existing path). Phase 5+ only
  changes how `record` messages are consumed.
* **Re-running PMC after backfill.** Per-record GPS does not affect
  TSS / NP / CTL / ATL — those are computed from power and HR
  streams which are unaffected by this bug. No PMC recomputation
  required.
* **Adding new ICU API stream types.** We do not introduce a new
  fetch — the FIT file is the same one we already download for
  laps; we just stop discarding the records.

---

## Phase Overview (data-quality additions)

| Phase | Scope | Ships independently? | Risk |
| --- | --- | --- | --- |
| **Phase 5** | New `fetch_activity_fit_records()` in `intervals_icu.py` + unit tests; pure addition, no callers wired yet. | Yes — dead code that's just tested. | Low |
| **Phase 6** | New `_store_records_from_fit()` in `sync.py`; switch `_download_rides` and `single_sync.import_specific_activity` to FIT-primary with streams fallback. Behaviour change for new syncs. | Yes — gated by feature flag for one release if engineer prefers, otherwise direct cutover. | Medium |
| **Phase 7** | Harden `_normalize_latlng` to detect lat-only payloads and emit empty (better to render nothing than render wrong). New unit tests for the Variant B payload. Defensive guard in `_store_streams` rejects writes that would trip the D4 corruption signature. | Yes | Low |
| **Phase 8** | Add `smooth_speed()` to `server/metrics.py` + unit tests; wire into both FIT and streams ingest paths. | Yes | Low |
| **Phase 9** | New `scripts/backfill_corrupt_gps.py` + integration tests against the disposable test DB with mocked ICU/FIT fixtures. | Yes | Low (until run) |
| **Phase 10** | Frontend safeguard: detect D4 signature in `RideMap`, render warning banner instead of polyline; add unit test for the detector. Operator action: run Phase 9 backfill against prod (separate from code release). | Yes | Low |

---

## PHASE 5 — FIT-records fetch path (no behaviour change)

### Goal
Add a single pure-function downloader/parser for FIT `record` messages.
No call site is wired yet. The result is dead but tested code that
becomes the single source of truth for Pillar 1 (D1) in Phase 6.

### Files to touch
* `server/services/intervals_icu.py` — **edit** — add
  `fetch_activity_fit_records(activity_id: str) -> list[dict]` next to
  `fetch_activity_fit_laps`. Refactor to share the FIT download +
  tempfile dance via a small private helper
  `_download_fit_temp(activity_id) -> str | None` returning the local
  tempfile path (or `None` on non-200 / parse error). Both
  `fetch_activity_fit_laps` and `fetch_activity_fit_records` consume
  it. **Do not** change the existing `fetch_activity_fit_laps` return
  shape.
* `tests/unit/test_intervals_icu_fit_records.py` — **new** — pin the
  parser using a small synthetic FIT file (or mocked
  `fitparse.FitFile`).

### Step-by-step

#### Step 5.A — Extract the FIT-download helper (refactor under harness)
*Target:* `server/services/intervals_icu.py`.
*Test the existing behaviour first:* `pytest tests/unit/test_fit_laps.py
tests/integration/test_laps.py -v` must be green BEFORE the refactor.
*Refactor:* extract the `tempfile.mkstemp + httpx.get + os.write +
FitFile + try/finally unlink` block from `fetch_activity_fit_laps` into
a new private context manager `_open_fit(activity_id: str) ->
fitparse.FitFile | None`. Use `contextlib.contextmanager` so the temp
file is always cleaned up.
*Verification:* re-run the same command — all green, zero behaviour
change.

#### Step 5.B — Implement `fetch_activity_fit_records`
*Target file:* `server/services/intervals_icu.py`.
*Signature:*
```python
def fetch_activity_fit_records(activity_id: str) -> list[dict]:
    """Download the FIT file from intervals.icu and extract `record` messages.

    Returns a list of dicts in the same flat shape as parse_ride_json
    builds today, ready for _store_records_from_fit:
        {
            "timestamp_utc": str | None,  # ISO-8601 UTC
            "power": int | None,
            "heart_rate": int | None,
            "cadence": int | None,
            "speed": float | None,         # m/s, raw (smoothed in Phase 8)
            "altitude": float | None,      # m
            "distance": float | None,      # m
            "lat": float | None,           # degrees
            "lon": float | None,           # degrees
            "temperature": float | None,
        }

    Returns [] when the FIT is unavailable, the file fails to parse,
    or it contains zero `record` messages.
    """
```
*Implementation notes for the engineer:*
* Use the existing `_semicircles_to_degrees` helper for `position_lat`
  / `position_long`.
* `record.timestamp` from `fitparse` is a `datetime` (UTC) — emit
  `value.isoformat() + 'Z'` (or `.replace(tzinfo=timezone.utc).isoformat()`)
  so the column matches the existing `timestamp_utc TEXT` shape.
* Prefer `enhanced_speed` over `speed`, `enhanced_altitude` over
  `altitude` (D1).
* Skip records with no `timestamp` field (extremely rare; defensively
  defended).
* No power/HR/cadence default. Missing field → `None`. The downstream
  metrics pipeline already tolerates `None`.

#### Step 5.C — Unit tests
*Target file:* `tests/unit/test_intervals_icu_fit_records.py`.
*Test cases:*

1. `test_fetch_records_happy_path`: monkeypatch `httpx.get` to return
   200 + a known FIT byte payload (use `tests/fixtures/sample.fit` —
   create a tiny 5-record FIT file via `fit_tool.py` once or commit
   one of the existing test FITs already in `data/`). Assert returned
   list length matches the FIT's record count and field types.
2. `test_fetch_records_semicircle_conversion`: assert a known
   `position_lat = 469000000` (semicircles) maps to ~39.31° degrees.
3. `test_fetch_records_no_fit_returns_empty_list`: monkeypatch
   `httpx.get` to return 404. Assert `== []` (no exception).
4. `test_fetch_records_parse_error_returns_empty_list`: monkeypatch
   `_open_fit` to raise `fitparse.FitParseError`. Assert `== []`.
5. `test_fetch_records_uses_enhanced_fields_when_present`: assert
   `enhanced_speed` wins over `speed` and `enhanced_altitude` wins
   over `altitude`.
6. `test_fetch_records_emits_iso_utc_timestamps`: assert every
   `timestamp_utc` is a string ending in `Z` or `+00:00`.

*Verification:*
```bash
pytest tests/unit/test_intervals_icu_fit_records.py -v
```
All 6 cases must pass. The pre-existing `tests/unit/test_fit_laps.py`
must still pass (refactor regression guard).

### Phase 5 Definition of Done
* [x] `fetch_activity_fit_records` exists, is exported, has a docstring
  matching D1's field semantics.
* [x] `fetch_activity_fit_laps` shares the FIT-download path with the
  new function and still returns identical output (regression-tested).
* [x] Unit-test coverage for the 6 cases above (8 cases shipped — added
  zero-records and missing-timestamp defensive cases).
* [x] No call site changes anywhere — `git grep
  fetch_activity_fit_records server` returns only the definition.

**Status: ✅ Implemented in `server/services/intervals_icu.py` (refactored
`_open_fit` context manager + new `fetch_activity_fit_records`) + new
`tests/unit/test_intervals_icu_fit_records.py` (8 cases). All 18
existing FIT-laps tests + 18 streams-latlng tests still green.**

---

## PHASE 6 — Switch ICU re-sync to FIT-primary

### Goal
Wire `fetch_activity_fit_records` into both the bulk sync
(`_download_rides` in `server/services/sync.py`) and the per-ride
re-sync (`single_sync.import_specific_activity`). Streams remain the
fallback when FIT is unavailable.

### Files to touch
* `server/services/sync.py` — **edit** — add
  `_store_records_from_fit(ride_id, fit_records, conn)` and a
  `_store_records_or_fallback(ride_id, icu_id, conn) -> str` that
  encapsulates the FIT-then-streams decision and returns the
  `gps_source` ("fit" / "streams" / "none") for logging.
* `server/services/single_sync.py` — **edit** — replace the
  unconditional `_store_streams` + `_backfill_start_location`
  sequence with `_store_records_or_fallback`. Keep the
  `_backfill_start_from_laps` call afterwards (still useful — laps are
  more reliable than even FIT records for ride-start geo because the
  first `record` is sometimes a pre-ride GPS lock attempt).
* `tests/integration/test_sync.py` — **extend** — add a test asserting
  the FIT-primary path writes `ride_records` from FIT and ignores the
  streams `latlng` even if it's malformed.

### Step-by-step

#### Step 6.A — Add `_store_records_from_fit`
*Target file:* `server/services/sync.py`.
*Signature:*
```python
def _store_records_from_fit(
    ride_id: int,
    fit_records: list[dict],
    conn,
) -> int:
    """Insert FIT-derived per-record rows, returns the count written.

    Replaces any existing ride_records for this ride id (DELETE first,
    then INSERT) so the call is safe to re-run during re-sync. Caller
    owns the transaction.
    """
```
*Implementation:*
1. `conn.execute("DELETE FROM ride_records WHERE ride_id = %s",
   (ride_id,))` first — idempotent for re-syncs.
2. Build rows tuple in the same column order as the existing
   `_store_streams` insert. Use the FIT record dict produced by
   Phase 5 directly (one-to-one field map).
3. `conn.executemany(...)` with the existing INSERT statement.
4. Log `logger.info("gps_source", ride_id=ride_id, source="fit",
   record_count=len(rows))`.
5. Return `len(rows)`.

#### Step 6.B — Add `_store_records_or_fallback`
*Target file:* `server/services/sync.py`.
*Signature:*
```python
def _store_records_or_fallback(
    ride_id: int,
    icu_id: str,
    conn,
) -> tuple[str, dict | None]:
    """Decide FIT vs streams for per-record GPS, write the records, return the chosen source + the stream dict (or None) so callers that still need streams for the metric pipeline don't re-fetch.

    Returns:
        ("fit", streams_dict_or_None) when FIT was used. streams_dict is
            still fetched & returned so the metric pipeline can use the
            unsmoothed power/HR series; pass None to skip that fetch.
        ("streams", streams_dict) when FIT failed and streams were used.
        ("none", None) when both failed (rare).
    """
```
*Implementation:*
1. Try `fit_records = fetch_activity_fit_records(icu_id)`. Wrap in
   `try / except Exception`; on exception treat as empty.
2. If `fit_records`: call `_store_records_from_fit(ride_id, fit_records,
   conn)`. Then call `fetch_activity_streams(icu_id)` (still needed
   for the metric pipeline's `process_ride_samples` input — power /
   HR / cadence flat lists). Return `("fit", streams)`.
3. Else: fall back. `streams = fetch_activity_streams(icu_id)`. If
   streams: `_store_streams(ride_id, streams, conn=conn)` (existing
   code path) AND `_backfill_start_location(ride_id, streams,
   conn=conn)` (existing). Log
   `logger.warning("gps_source_fallback_streams", ride_id=ride_id,
   reason="fit_unavailable")`. Return `("streams", streams)`.
4. Else: log `logger.warning("gps_source_none", ride_id=ride_id)`.
   Return `("none", None)`.

**Important:** when FIT is the source we deliberately do NOT call
`_backfill_start_location(streams, ...)` because the streams `latlng`
might be the corrupt lat-only variant. We always call
`_backfill_start_from_laps(...)` afterwards (existing path) which is
the authoritative ride-start source.

#### Step 6.C — Wire into `_download_rides` (bulk sync)
*Target file:* `server/services/sync.py`, ≈line 600 (inside the
`for activity in activities` loop's stream-download block).
*Change:* Replace the existing
`streams = await asyncio.to_thread(fetch_activity_streams, icu_id)`
+ `_store_streams` + `_backfill_start_location` block with:

```python
gps_source, streams = await asyncio.to_thread(
    _store_records_or_fallback, ride_db_id, icu_id, conn,
)
log_lines.append(_tlog(f"  + stored per-record data via {gps_source} for {ride_date_str}"))
```

The downstream metric pipeline (the `_extract_streams(streams)` calls
+ `process_ride_samples` block) is unchanged; it still receives the
streams dict from the helper's second return value.

#### Step 6.D — Wire into `single_sync.import_specific_activity`
*Target file:* `server/services/single_sync.py`.
*Change:* same shape as 6.C — replace the
`fetch_activity_streams` + `_store_streams` +
`_backfill_start_location` sequence with a single call to
`_store_records_or_fallback`. Keep the subsequent
`fetch_activity_fit_laps` + `_store_laps` +
`_backfill_start_from_laps` chain unchanged.

#### Step 6.E — Backfill the streams script for the same path
*Target file:* `scripts/backfill_icu_streams.py`.
*Change:* update the script's `_store_streams + _backfill_start_location`
calls to use `_store_records_or_fallback` so the existing operational
"fix missing streams" tool also benefits from the new behaviour.
Document the script's mode in its docstring as "FIT-primary, streams-fallback".

#### Step 6.F — Integration test (FIT wins over malformed streams)
*Target file:* `tests/integration/test_sync.py` (extend or add a new
file `test_sync_fit_primary.py` if the existing file is unwieldy).
*Test case:*
```python
def test_fit_primary_overrides_corrupt_streams_latlng(client, db_conn, monkeypatch):
    """When the FIT records resolve, ignore the streams latlng even if it is the lat-only Variant B."""
    fake_fit_records = _build_fit_records(...)  # helper that produces the dict-shape expected by _store_records_from_fit
    fake_corrupt_streams = {
        "time": list(range(len(fake_fit_records))),
        # Lat-only Variant B: every "lon" is actually a latitude
        "latlng": [39.75, 39.75, 39.75, 39.75, ...],
    }
    monkeypatch.setattr("server.services.sync.fetch_activity_fit_records",
                        lambda icu_id: fake_fit_records)
    monkeypatch.setattr("server.services.sync.fetch_activity_streams",
                        lambda icu_id: fake_corrupt_streams)

    _store_records_or_fallback(ride_id=42, icu_id="i999", conn=db_conn)

    rows = db_conn.execute(
        "SELECT lat, lon FROM ride_records WHERE ride_id = 42 ORDER BY id"
    ).fetchall()
    # Assert: every row matches FIT, NOT 39.75 (the streams latlng)
    assert all(r["lat"] != 39.75 or r["lon"] != 39.75 for r in rows)
    # Assert: the values match the FIT-derived expectations (e.g. lon negative for a US ride)
    assert all(r["lon"] < 0 for r in rows)
```

#### Step 6.G — Verification
```bash
pytest tests/unit/test_intervals_icu_fit_records.py tests/unit/test_sync_latlng.py -v
./scripts/run_integration_tests.sh tests/integration/test_sync.py -v
```
Manual smoke (operator):
```bash
# Re-sync the known-corrupt ride 3238 against local DB
python -c "import asyncio; from server.services.single_sync import import_specific_activity; asyncio.run(import_specific_activity('i_<actual_icu_id_for_3238>'))"
# Inspect:
psql $CYCLING_COACH_DATABASE_URL -c "SELECT lat, lon FROM ride_records WHERE ride_id = 3238 LIMIT 5;"
# Expect: lat≈39.75, lon negative (US ride). NOT (lat, lat).
```

### Phase 6 Definition of Done
* [x] `_store_records_or_fallback` exists, has integration coverage
  (`test_sync.py::test_store_records_from_fit_writes_one_row_per_record`,
  `test_fit_primary_overrides_corrupt_streams_latlng`,
  `test_store_records_or_fallback_uses_streams_when_fit_unavailable`,
  `test_store_records_or_fallback_returns_none_when_both_fail`).
* [x] Both bulk sync (`_download_rides`) and single re-sync
  (`single_sync.import_specific_activity`) go through it. The operational
  `scripts/backfill_icu_streams.py` was switched too (Step 6.E).
* [x] Logging emits structured `gps_source` event with
  `source=fit|streams|none` for every ride synced. Streams-fallback path
  also emits `gps_source_fallback_streams`; both-failed path emits
  `gps_source_none`.
* [x] The FIT-vs-corrupt-streams integration test is green
  (`test_fit_primary_overrides_corrupt_streams_latlng` confirms an 80-pt
  lat-only Variant B streams payload is ignored when FIT records resolve).
* [x] No regression in existing `test_sync_latlng.py` cases (18/18 still
  green); existing two FIT-laps integration tests updated to also mock
  `fetch_activity_fit_records=[]` so they remain on the streams-fallback
  branch and continue asserting their original behaviour.

**Status: ✅ Implemented.** New helpers in `server/services/sync.py`,
call-site changes in `server/services/sync.py::_download_rides` and
`server/services/single_sync.py::import_specific_activity`, plus a
matching update in `scripts/backfill_icu_streams.py`. Step 6.G manual
smoke is **deferred to operator** — Phases 5-7 are code-only per the
team-lead brief.

---

## PHASE 7 — Streams parser hardening (defence in depth)

### Goal
When streams are the fallback (no FIT), do not produce
garbage `(lat, lat)` pairs from a lat-only payload. Instead detect
and drop the GPS portion entirely (records get NULL lat/lon — the
indoor-placeholder UX in Phase 4 already handles that gracefully).
Add a defensive guard in `_store_streams` that refuses to write
records when the resulting series trips the D4 corruption signature.

### Files to touch
* `server/services/sync.py` — **edit**
  * `_normalize_latlng` (≈line 229): add a new branch after the
    existing concatenated detector that catches the lat-only variant.
  * `_store_streams` (≈line 304): after `latlng_pairs =
    _normalize_latlng(...)`, run the D4 detection on the pairs. If
    >50% of pairs satisfy `abs(lat-lon) < 1.0` AND the ride has more
    than `MIN_GPS_RECORDS_FOR_DETECTION = 60` total pairs (avoid
    flagging tiny test fixtures), discard `latlng_pairs` (set to
    empty list) and log
    `logger.warning("streams_latlng_corruption_detected",
    ride_id=ride_id, total=N, suspect=K)`.
* `tests/unit/test_sync_latlng.py` — **extend**
  * Add 4 new test cases covering the lat-only Variant B and the
    `_store_streams` corruption guard.

### Step-by-step

#### Step 7.A — Detection logic in `_normalize_latlng`
*Target file:* `server/services/sync.py`.
*Change:* between the existing concatenated-format branch (line ≈258)
and the alternating-pairs fallback (line ≈270), insert:

```python
# Detect the "lat-only" payload variant (the Variant B observed on
# ride 3238 in 2026-04-22). Heuristic: if the second half of the
# array is statistically still latitudes (not longitudes), the
# payload is corrupt and we have no usable GPS. Better to return
# nothing than to fabricate (lat, lat) pairs.
if n >= 60:  # only check if we have enough samples to be confident
    half = n // 2
    second_half = [v for v in raw[half:] if isinstance(v, (int, float))]
    if second_half:
        avg_second = sum(second_half) / len(second_half)
        # A real longitude in any populated region has |lon| > 1°
        # (the equator/prime-meridian corner is the rare exception).
        # Latitudes in populated regions have |lat| in [25°, 71°].
        # If the mean of "what should be longitudes" is in the
        # latitude range and within 5° of the mean of "what should
        # be latitudes", the payload is corrupt.
        first_half = [v for v in raw[:half] if isinstance(v, (int, float))]
        if first_half:
            avg_first = sum(first_half) / len(first_half)
            if abs(avg_first - avg_second) < 5.0 and abs(avg_second) < 90:
                logger.warning(
                    "latlng_lat_only_payload_detected",
                    n=n,
                    first_half_avg=round(avg_first, 3),
                    second_half_avg=round(avg_second, 3),
                )
                return []
```

#### Step 7.B — Defensive guard in `_store_streams`
*Target file:* `server/services/sync.py`.
*Change:* after `latlng_pairs = _normalize_latlng(latlng_raw)` (line
≈321), add:

```python
# Belt-and-suspenders: if the parser returned pairs that nonetheless
# trip the D4 signature, refuse to write them. Streams will then
# render as "no GPS" which is far better than rendering wrong GPS.
MIN_GPS_RECORDS_FOR_DETECTION = 60
if len(latlng_pairs) >= MIN_GPS_RECORDS_FOR_DETECTION:
    suspect = sum(
        1 for lat, lon in latlng_pairs
        if lat is not None and lon is not None and abs(lat - lon) < 1.0
    )
    if suspect / len(latlng_pairs) > 0.5:
        logger.warning(
            "streams_latlng_corruption_guard_triggered",
            ride_id=ride_id,
            total=len(latlng_pairs),
            suspect=suspect,
        )
        latlng_pairs = []
```

#### Step 7.C — New unit tests
*Target file:* `tests/unit/test_sync_latlng.py`.
*Test cases to add:*

1. `test_normalize_latlng_lat_only_variant_returns_empty`:
   Build a 100-element list `[39.75, 39.75, 39.751, 39.751, ...,
   39.75, 39.75]` (no longitudes anywhere). Assert
   `_normalize_latlng(raw) == []`.

2. `test_normalize_latlng_lat_only_short_payload_passes_through`:
   Build a 10-element same-shape list. Because `n < 60` we don't
   trigger the new detector — the existing alternating-pairs
   fallback fires, producing `(lat, lat)` pairs. Assert that
   behaviour is preserved (no false-positive on tiny fixtures used
   in other tests). Document in a comment that this is intentional.

3. `test_normalize_latlng_real_us_ride_passes`:
   Build a 100-element concatenated payload `[lat × 50, lon × 50]`
   for a real Boulder, CO ride (lat≈40.0, lon≈-105.3). Assert the
   parser returns 50 valid pairs with `abs(lat - lon) > 100` for
   each.

4. `test_store_streams_corruption_guard_drops_lat_lat_pairs`:
   Construct a `_FakeConn`. Call `_store_streams(ride_id=99,
   streams={"time": list(range(80)), "latlng":
   [[39.75, 39.75]] * 80}, ...)`. Assert that the resulting
   `executemany` rows all have `lat is None and lon is None` (the
   guard fired and stripped the GPS columns), but other columns are
   still written.

#### Step 7.D — Verification
```bash
pytest tests/unit/test_sync_latlng.py -v
```
All existing 18 cases plus 4 new = 22 cases green.

### Phase 7 Definition of Done
* [x] `_normalize_latlng` returns `[]` for the lat-only variant
  (n>=60, both halves statistically still latitudes).
* [x] `_store_streams` refuses to write rows that would trip the D4
  signature (guard runs after parser, before INSERT; non-GPS columns
  are still written so power/HR/cadence aren't lost).
* [x] Existing test suite untouched + 4 new green tests
  (22/22 green in `tests/unit/test_sync_latlng.py`).
* [x] Two new structured-log channels (`latlng_lat_only_payload_detected`,
  `streams_latlng_corruption_guard_triggered`) emit so we can
  monitor in Cloud Logging post-deploy.

**Status: ✅ Implemented.** Plan placement note: the lat-only detector
had to be hoisted to run BEFORE the existing concatenated-format
branch (not between concat and alternating as the plan originally
sketched), because the concatenated detector's `abs(r0 - r1) < 1°`
trigger ALSO matches lat-only payloads (consecutive latitudes are
always within 1° of each other) and would fire first. Gating the
new detector on the same `r0 ≈ r1` proximity means legitimate
alternating data — where lat and lon differ by far more than 1° for
any real outdoor ride — is never inspected. The constants
`MIN_GPS_RECORDS_FOR_DETECTION = 60` and
`GPS_CORRUPTION_RATIO_THRESHOLD = 0.5` are defined once at module
scope in `server/services/sync.py` for re-use by Phase 9 (backfill)
and the `_store_streams` guard.

---

## PHASE 8 — Speed smoothing in our libraries

### Goal
Pillar 3 (D3): own the speed-smoothing pipeline so we are not
dependent on ICU's undocumented `velocity_smooth` window. Apply the
same smoothing on both the FIT path (raw `record.enhanced_speed`)
and the streams fallback path (raw `velocity` if `velocity_smooth`
is absent).

### Files to touch
* `server/metrics.py` — **edit** — add `smooth_speed(speed_array,
  window: int = 5) -> list[float | None]`.
* `server/services/sync.py` — **edit** —
  * In `_store_records_from_fit`: collect `speed_raw` from the FIT
    records, run through `smooth_speed`, write the smoothed series
    into the rows.
  * In `_store_streams` (the fallback path): same — accept the
    streams `velocity_smooth` if present (already smoothed by ICU)
    OR `velocity` (if not), then run our `smooth_speed` for
    consistency. Document that for streams we prefer running it
    even on `velocity_smooth` to normalise window across rides.
* `tests/unit/test_metrics.py` — **extend** — add `smooth_speed`
  cases.

### Step-by-step

#### Step 8.A — Implement `smooth_speed`
*Target file:* `server/metrics.py`.
*Signature:*
```python
def smooth_speed(speed_array, window: int = 5):
    """Apply a centred uniform rolling-mean smoothing to a speed series.

    - None/NaN treated as missing.
    - Gaps < 10 samples linearly interpolated (matches clean_ride_data policy).
    - Gaps >= 10 samples preserved as None in the output (no fabrication
      across long stops).
    - Returns a list of float|None matching the input length.
    """
```
Use `scipy.ndimage.uniform_filter1d` for the smoothing, mirroring
the existing rolling-mean pattern at `metrics.py:108`.

#### Step 8.B — Unit tests
*Target file:* `tests/unit/test_metrics.py`.
*Cases:*
1. `test_smooth_speed_empty_returns_empty`.
2. `test_smooth_speed_passthrough_for_constant_signal`: `[5.0]*20` →
   `[5.0]*20` (small float tolerance).
3. `test_smooth_speed_single_spike_attenuated`: `[5.0]*10 + [50.0] +
   [5.0]*10` → output center value is much closer to 5 than 50.
4. `test_smooth_speed_short_gap_interpolated`: input has 3
   consecutive None in the middle of constant 5.0 — output replaces
   them with ~5.0.
5. `test_smooth_speed_long_gap_preserved_as_none`: input has 12
   consecutive None — output keeps None at those positions.
6. `test_smooth_speed_window_size_validated`: `window=0` or
   negative raises `ValueError`.

#### Step 8.C — Wire into FIT path
*Target file:* `server/services/sync.py`,
`_store_records_from_fit`.
*Change:* before building the executemany rows, run:
```python
from server.metrics import smooth_speed
raw_speeds = [r.get("speed") for r in fit_records]
smoothed = smooth_speed(raw_speeds, window=5)
# Then in the row-build loop, use smoothed[i] instead of fit_records[i]["speed"].
```

#### Step 8.D — Wire into streams fallback path
*Target file:* `server/services/sync.py`, `_store_streams`.
*Change:* after `velocity = stream_map.get("velocity_smooth", [])`,
add a fallback to `velocity = stream_map.get("velocity", velocity)
or velocity` and then `velocity = smooth_speed(velocity, window=5)`.

#### Step 8.E — Verification
```bash
pytest tests/unit/test_metrics.py -v -k smooth_speed
./scripts/run_integration_tests.sh tests/integration/test_sync.py -v
```

### Phase 8 Definition of Done
* [x] `smooth_speed` exists with 6 green unit tests.
* [x] Both ingest paths use it (`server/services/sync.py:370` for the
  streams fallback path, `server/services/sync.py:463` for the
  FIT-primary path).
* [x] Re-syncing a known ride yields a `speed` series that is monotonic
  smoother than ICU's raw `velocity_smooth` (manual eyeball gate is
  dev-only; the unit tests are the hardness gate).

**Status: ✅ Implemented.** New `smooth_speed(speed_array, window=5)`
helper at `server/metrics.py:160-233` (NaN-aware, gaps <10 samples
linearly interpolated, scipy `uniform_filter1d` size=5, gaps ≥10
preserved as None). Wired into `_store_records_from_fit` and
`_store_streams`. 6 unit tests in `tests/unit/test_metrics.py`.
Window locked at 5 per D3.

---

## PHASE 9 — Historical backfill script

### Goal
Pillar 4: a one-time, idempotent, dry-run-by-default script that
walks every ride in the DB, detects the D4 corruption signature, and
re-fetches from ICU (FIT-primary via the Phase 6 helpers) to
overwrite `ride_records.lat/lon` and the other affected per-record
fields.

### Files to touch
* `scripts/backfill_corrupt_gps.py` — **new** — modeled after
  `scripts/backfill_ride_start_geo.py`. Uses
  `_store_records_or_fallback` (Phase 6).
* `tests/integration/test_backfill_corrupt_gps.py` — **new** —
  drives `run_backfill(dry_run=True)` and `run_backfill(dry_run=False)`
  against the test DB with monkeypatched ICU/FIT responses.
* `server/services/intervals_icu.py` — **edit** — fold in the
  FIT-download dedup that was deferred from Phase 5 (Q1 in the
  Resolved Open Questions section). Add `fetch_activity_fit_all(icu_id)
  -> {laps, records}` that downloads the FIT once and returns both,
  then update `_store_records_or_fallback` to use it. Saves ~500 ms
  per ride × N rides during the backfill sweep — that is the call
  site where the perf cost actually compounds. Engineer punted from
  Phase 5 (auditor accepted) on the basis that it buys nothing
  material until the backfill runs; bundling here ties the
  optimization to the work where it pays off.

### Step-by-step

#### Step 9.A — Skeleton (mirror `backfill_ride_start_geo.py`)
*Target file:* `scripts/backfill_corrupt_gps.py`.
*Public surface:*
```python
def detect_corruption(records: list[dict]) -> dict:
    """Return {total, suspect, corrupt: bool}.

    `corrupt` is True iff total >= MIN_GPS_RECORDS_FOR_DETECTION (60)
    AND suspect/total > 0.5.
    """

def run_backfill(*, dry_run: bool, sleep_seconds: float = 0.5,
                 limit: int | None = None) -> dict:
    """Walk corrupt rides; re-sync via _store_records_or_fallback.

    Returns: {
        total_examined, total_corrupt, fixed,
        fit_unavailable, fit_parse_failed, icu_api_error,
        skipped_already_clean,
    }
    """

def main(argv: list[str] | None = None) -> int:
    # Same arg shape as backfill_ride_start_geo.py:
    # --dry-run (default True), --allow-remote, --sleep N, --limit N.
```

*Detection query:*
```sql
SELECT r.id, r.filename, COUNT(*) AS total,
       SUM(CASE WHEN ABS(rr.lat - rr.lon) < 1.0 THEN 1 ELSE 0 END) AS suspect
  FROM rides r
  JOIN ride_records rr ON rr.ride_id = r.id
 WHERE r.filename LIKE 'icu_%'
   AND rr.lat IS NOT NULL AND rr.lon IS NOT NULL
 GROUP BY r.id, r.filename
HAVING COUNT(*) >= 60
   AND SUM(CASE WHEN ABS(rr.lat - rr.lon) < 1.0 THEN 1 ELSE 0 END)::float / COUNT(*) > 0.5
 ORDER BY r.start_time DESC
[ LIMIT %s ]
```

For each suspect ride: extract `icu_id` from filename (mirror
`backfill_ride_start_geo._icu_id_from_filename`); if `dry_run`,
log "WOULD re-sync"; else call `_store_records_or_fallback(ride_id,
icu_id, conn)`. Sleep `sleep_seconds` between rides.

#### Step 9.B — Localhost guard + arg parsing
Mirror `backfill_ride_start_geo.py` lines 165-225 line-for-line. Same
LOCALHOST_HOSTNAMES allowlist, same `--allow-remote` requirement.

#### Step 9.C — Integration tests
*Target file:* `tests/integration/test_backfill_corrupt_gps.py`.
*Cases:*
1. `test_detect_corruption_flags_lat_lat_pairs`: insert 100
   `ride_records` with `lat=lon=39.75`; assert
   `detect_corruption(...)` returns `corrupt=True`.
2. `test_detect_corruption_passes_real_us_ride`: insert 100
   `ride_records` with `lat=39.75, lon=-105.3`; assert
   `corrupt=False`.
3. `test_detect_corruption_passes_short_ride`: 30 records all
   `lat=lon`; `corrupt=False` (below `MIN_GPS_RECORDS_FOR_DETECTION`).
4. `test_run_backfill_dry_run_makes_no_writes`: seed corrupt rides,
   monkeypatch `fetch_activity_fit_records` and
   `fetch_activity_streams`. Run `dry_run=True`. Assert no rows
   changed.
5. `test_run_backfill_writes_when_not_dry_run`: same seed,
   monkeypatched FIT returns valid US lat/lon. Run `dry_run=False`.
   Assert previously-corrupt records now have correct values.
6. `test_run_backfill_handles_no_fit_no_streams`: monkeypatch FIT
   to return `[]` and streams to return `{}`. Run; assert
   `fit_unavailable + icu_api_error` is incremented and the row is
   left untouched (still corrupt) so the next run can retry.
7. `test_run_backfill_respects_limit`: seed 5 corrupt rides; run
   with `limit=2`; assert only 2 are touched.

#### Step 9.D — Verification
```bash
./scripts/run_integration_tests.sh tests/integration/test_backfill_corrupt_gps.py -v
# Then a real local-DB dry-run (operator). Dry-run is the default per D5,
# so the explicit --dry-run flag is optional but documents intent.
python scripts/backfill_corrupt_gps.py --dry-run
# Then a real local-DB write run — --no-dry-run is REQUIRED to write.
python scripts/backfill_corrupt_gps.py --no-dry-run
# Sanity:
psql $CYCLING_COACH_DATABASE_URL -c "
  SELECT COUNT(DISTINCT r.id)
    FROM rides r JOIN ride_records rr ON rr.ride_id = r.id
   WHERE rr.lat IS NOT NULL AND ABS(rr.lat - rr.lon) < 1.0
   GROUP BY r.id HAVING COUNT(*) > 60;"
# Expect: 0.
```

### Phase 9 Definition of Done
* [x] Script lives at `scripts/backfill_corrupt_gps.py` (381 lines).
* [x] 7 integration tests green
  (`tests/integration/test_backfill_corrupt_gps.py`).
* [x] FIT-download dedup landed: new
  `fetch_activity_fit_all(icu_id) -> {laps, records}` at
  `server/services/intervals_icu.py:469-512`; `_store_records_or_fallback`
  consumes it once and returns a 3-tuple `(source, streams, fit_laps)`
  so callers skip the second `fetch_activity_fit_laps` round-trip when
  FIT records succeeded. `test_fetch_all_downloads_only_once` asserts
  `mock_get.call_count == 1`. 4 new unit tests in
  `tests/unit/test_intervals_icu_fit_all.py`.
* [x] Dry-run is the default mode (D5); `--no-dry-run` is required
  to write. `--allow-remote` enforced for non-localhost DB URLs.
  All 7 counters emitted in the end-of-run summary.
* [x] Local-DB sanity runs (dry-run reports count, `--no-dry-run`
  reduces to 0) are operator steps — verified locally during dev.
* [x] Script does NOT run against prod (D5 mandate); operator runs
  Step 10.E post-deploy.

**Status: ✅ Implemented.** New script + tests; FIT-download dedup
bundled in per the plan tweak in commit `eca8edf`. The `_open_fit`
context manager from Phase 5 is the single FIT HTTP call site;
`fetch_activity_fit_all` returns `{laps, records}` from a single
download. Backfill summary logged in `key=value` shape (not strict
JSON — a minor polish item, not a blocker).

---

## PHASE 10 — Frontend safeguard + production rollout

### Goal
* Frontend: detect the D4 signature in the records the API returned;
  if tripped, render a banner over the polyline rather than rendering
  wrong GPS.
* Operator: run the Phase 9 backfill against the prod DB after the
  v1.14.x release containing Phases 5-9 ships and bakes for ≥24h.

### Files to touch
* `frontend/src/lib/map.ts` — **edit** — add a pure helper
  `detectGpsCorruption(records: { lat?: number | null; lon?: number
  | null }[]): { corrupt: boolean; total: number; suspect: number }`.
  Same threshold as D4 / backend.
* `frontend/src/components/RideMap.tsx` — **edit** — call the helper
  on render; if `corrupt`, render the banner overlay AND skip the
  polyline.
* `frontend/src/lib/map.test.ts` — **extend** — add 4 cases for
  `detectGpsCorruption`.
* `tests/e2e/03-rides.spec.ts` — **extend** — one E2E case that
  seeds a corrupt-GPS ride into the test DB (or monkey-patches the
  API response in the page test) and asserts the banner is visible.

### Step-by-step

#### Step 10.A — `detectGpsCorruption` helper
*Target file:* `frontend/src/lib/map.ts`.
*Signature:*
```ts
export const MIN_GPS_RECORDS_FOR_DETECTION = 60
export const CORRUPTION_RATIO_THRESHOLD = 0.5

export function detectGpsCorruption(
  records: Array<{ lat?: number | null; lon?: number | null }>,
): { corrupt: boolean; total: number; suspect: number } {
  let total = 0
  let suspect = 0
  for (const r of records) {
    if (typeof r.lat === 'number' && typeof r.lon === 'number') {
      total++
      if (Math.abs(r.lat - r.lon) < 1.0) suspect++
    }
  }
  return {
    total,
    suspect,
    corrupt:
      total >= MIN_GPS_RECORDS_FOR_DETECTION
      && suspect / total > CORRUPTION_RATIO_THRESHOLD,
  }
}
```

#### Step 10.B — Render the banner in `<RideMap>`
*Target file:* `frontend/src/components/RideMap.tsx`.
*Change:* near the top of the render function, before computing
`coords`:
```tsx
const corruption = useMemo(() => detectGpsCorruption(records), [records])
if (corruption.corrupt) {
  return (
    <section className="bg-surface rounded-xl border border-warning/30 p-6 text-center">
      <AlertTriangle size={28} className="mx-auto mb-3 text-warning" />
      <p className="text-xs font-medium text-warning">
        GPS data appears corrupted for this ride.
      </p>
      <p className="text-[11px] text-text-muted mt-1">
        Re-sync this ride to fix (Settings → Sync → Re-sync this ride).
      </p>
    </section>
  )
}
```
The existing indoor-placeholder path stays as-is.

#### Step 10.C — Unit tests
*Target file:* `frontend/src/lib/map.test.ts`.
*Cases:*
1. `detectGpsCorruption(empty array)` → `{ total: 0, suspect: 0,
   corrupt: false }`.
2. `detectGpsCorruption(100 lat≈lon records)` → `corrupt: true`.
3. `detectGpsCorruption(100 real US records)` → `corrupt: false`.
4. `detectGpsCorruption(30 lat≈lon records)` → `corrupt: false` (below
   `MIN_GPS_RECORDS_FOR_DETECTION`).

#### Step 10.D — E2E
*Target file:* `tests/e2e/03-rides.spec.ts`.
*Case:* seed (or monkey-patch the API response for) a ride whose
records have `lat == lon` for every entry; navigate to the ride
detail; assert the warning text "GPS data appears corrupted" is
visible AND the `canvas.maplibregl-canvas` is NOT rendered.

#### Step 10.E — Operator rollout (post-merge, post-deploy)
*Pre-conditions:* v1.14.x containing Phases 5-9 deployed to prod and
baked for ≥24h with no error spike.
*Sequence:*
1. `python scripts/backfill_corrupt_gps.py --dry-run --allow-remote`
   from a workstation with prod credentials. Inspect the summary
   counts (`total_corrupt`).
2. If `total_corrupt > 100`, run with `--limit 50` first to verify
   end-to-end before doing the full sweep.
3. `python scripts/backfill_corrupt_gps.py --no-dry-run --allow-remote`.
   `--no-dry-run` is REQUIRED to actually write — dry-run is the
   default per D5. Monitor Cloud Logging for `gps_source=fit` (good)
   vs `gps_source_fallback_streams` (degraded but acceptable) vs
   `gps_source=none` (failure — investigate per ride).
4. Verify post-state with the SQL query in Phase 9.D.
5. Spot-check 3 rides on the live map UI.

### Phase 10 Definition of Done
* [x] Frontend detects corruption and shows the warning banner instead
  of the polyline (`frontend/src/components/RideMap.tsx:217-235`,
  branch placed before the existing indoor-placeholder check so it's
  strictly additive).
* [x] 5 new Vitest cases green (superset of the planned 4 — added
  a numeric-equality assertion against the backend constants).
* [x] 1 new Playwright case green
  (`tests/e2e/03-rides.spec.ts` — monkey-patches a corrupt-GPS ride,
  asserts banner visible AND `canvas.maplibregl-canvas` not rendered).
* [x] Constants in `frontend/src/lib/map.ts:47-48`
  (`MIN_GPS_RECORDS_FOR_DETECTION = 60`,
  `CORRUPTION_RATIO_THRESHOLD = 0.5`) numerically match the backend
  source-of-truth at `server/services/sync.py:39-40` (D4 single
  source of truth — frontend can't import from Python, asserted by
  test instead).
* [ ] Operator runbook captured in `plans/00_MASTER_ROADMAP.md`
  Campaign 20 entry as a follow-up action item (auditor's
  recommended action #5; team-lead to add).

**Status: ✅ Implemented.** Banner copy locked per D7. Theme color
uses `yellow` token (no `--color-warning` token exists in the
palette today; `yellow` is the closest semantic match — adding a
dedicated warning token can be a one-line follow-up). Step 10.E
(operator-driven prod backfill execution) is correctly out of scope
for the engineer; user runs it post-deploy.

---

## Updated Test Plan Summary (data-quality additions only)

| Layer | What we test | Where |
| --- | --- | --- |
| Unit (BE) | `fetch_activity_fit_records` happy path + 5 edge cases | `tests/unit/test_intervals_icu_fit_records.py` |
| Unit (BE) | `_normalize_latlng` lat-only Variant B | `tests/unit/test_sync_latlng.py` (extend) |
| Unit (BE) | `_store_streams` corruption guard | `tests/unit/test_sync_latlng.py` (extend) |
| Unit (BE) | `smooth_speed` 6 cases | `tests/unit/test_metrics.py` (extend) |
| Integration | FIT-primary overrides corrupt streams `latlng` | `tests/integration/test_sync.py` (extend) |
| Integration | Backfill detection + dry-run + write paths (7 cases) | `tests/integration/test_backfill_corrupt_gps.py` (new) |
| Unit (FE) | `detectGpsCorruption` 4 cases | `frontend/src/lib/map.test.ts` (extend) |
| E2E | Corrupt-GPS ride shows warning banner, no canvas | `tests/e2e/03-rides.spec.ts` (extend) |
| Manual | Ride 3238 (the original repro) re-syncs to a correct US polyline | local DB after Phase 6 |
| Manual | Prod backfill dry-run shows N corrupt rides; non-dry-run fixes them all | prod DB after Phase 10.E |

---

## Updated Risks & Mitigations (data-quality additions)

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| FIT file is truthful but records contain `(0,0)` GPS pre-fix entries | Medium | The existing `_backfill_start_from_laps` path uses lap GPS for the ride-level start (immune). For per-record we let `(0,0)` flow through as data — frontend already tolerates it (the 0.0 fallback is rare and a single point on a polyline is invisible) |
| FIT records exist but `position_lat/long` are absent (some Garmin Edge older firmwares for indoor recordings) | Low | `_semicircles_to_degrees(None) → None`; rows get NULL lat/lon; map placeholder fires. Same UX as a true indoor ride |
| `fitparse` chokes on a malformed FIT file mid-stream | Low | `_open_fit` context manager wraps in try/except, returns `None`; FIT path returns `[]`; streams fallback engages. No data lost |
| Corruption-detection threshold flags a real ride near the equator/prime-meridian intersection | Very low | Real rides at lat≈lon spread across degrees as the ride progresses; the detector requires >50% of records to satisfy the threshold AND a minimum 60-record sample. We accept the false-positive risk of 1 banner-misfire per ~100k rides as preferable to a silent wrong-polyline render |
| `MIN_GPS_RECORDS_FOR_DETECTION = 60` excludes very short rides from the detector | Low | A <60s ride is a stop-after-start mishap or a deliberate calibration ride. Hiding the map for such rides via the indoor placeholder is acceptable; rendering a 5-point wrong polyline isn't a meaningful UX degradation either way |
| Backfill exhausts ICU rate limits | Medium | `--sleep 0.5` between requests = 2 req/s. ICU's published limit is ~10 req/s. `--limit` allows resumable batches. 429 responses surface as `icu_api_error` in the summary |
| Backfill partial failure leaves a ride with mixed-source records | Low | `_store_records_from_fit` deletes existing records first inside a transaction; the next backfill run rewrites them atomically |
| FIT file is downloaded twice per re-sync (once for laps, once for records) | High | Phase 5.A's `_open_fit` context manager downloads once and the engineer is encouraged to plumb a single download into both `fetch_activity_fit_laps` and `fetch_activity_fit_records` (e.g. via a `fetch_activity_fit(activity_id) -> tuple[list[dict], list[dict]]` combined call). This is an optimisation, not a correctness requirement — defer if it complicates the diff. Doc the perf cost (one extra GET per ride re-sync = ~500ms) so the operator running the prod backfill knows to expect it |
| Deploying Phases 5-8 changes the byte-for-byte output of new syncs (downstream PMC sensitivity) | Low | PMC depends on TSS, which depends on power and HR — both unaffected. Speed smoothing affects only the `speed` column displayed on the chart and used for nothing else |
| Schema migration for `gps_source` column rejected (D2) but a future bug needs it | Low | Sync logs in Cloud Logging carry the `gps_source` channel; for a future bug we can correlate the error to the source via timestamp lookup. If that proves insufficient, fix forward with a migration that backfills the column from logs |

---

## Open Questions for the User (must answer before engineering starts)

1. **FIT-download dedup (Risk row 8).** OK to add a small refactor in
   Phase 5 that combines `fetch_activity_fit_laps` +
   `fetch_activity_fit_records` into a single download per ride
   (`fetch_activity_fit_all(icu_id) -> {laps, records}`)? Strictly
   optional, saves ~500ms per re-sync at the cost of a slightly
   bigger Phase 5 diff. Default: **yes, do it** (the extra LOC pays
   for itself the first time the prod backfill runs).
2. **`gps_source` schema flag (D2).** Confirmed NOT adding it. If the
   user wants the option for future debugging, say so now and we
   add a migration in Phase 6.
3. **Frontend banner copy (Phase 10.B).** Wording: "GPS data appears
   corrupted for this ride. Re-sync this ride to fix (Settings →
   Sync → Re-sync this ride)." OK as-is, or shorter?
4. **Backfill rollout risk appetite.** Default plan is: ship code in
   v1.14.x, bake 24h, then operator runs backfill against prod with
   `--limit 50` then full sweep. Acceptable, or want a more
   conservative phased rollout (e.g. backfill last-30-days only on
   day 1, last-180-days on week 2, full history on week 3)?
5. **Speed-smoothing window (D3).** Locked at 5 samples. If the user
   has a strong opinion (e.g. 10 for cyclocross, 3 for crit racing),
   say so; otherwise the engineer ships 5.

These are real open questions. Engineering should not start Phases
5+ without explicit answers to #1-#5 (or an explicit "go with
defaults" from the user).
