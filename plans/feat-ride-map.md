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
