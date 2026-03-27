# Plan 02: Maps, Heatmap & Route Builder

This campaign brings the full geospatial power of the `../tcx` engine into WT-Coach, enabling trail discovery via Heatmaps and a sophisticated Route Builder.

## 🥅 Objective
*   Implement a **Historical Heatmap** (Backend streaming + Frontend rendering).
*   Port the **Geospatial Engine** (Climb detection, Gradient analysis).
*   Implement the **Route Stitcher** (Extracting and merging segments from previous rides).

## 🧱 Key Features

### Historical Heatmap
*   **Backend:** New `GET /api/maps/heatmap` to stream coordinate pairs from `ride_records`.
*   **Frontend:** MapLibre `heatmap` and `line` layers to visualize ride density.

### Route Stitcher (The "Stitch Bin")
*   **Extraction:** Scrub any previous ride via the elevation profile and "Extract" a segment.
*   **Merge:** Join extracted segments into a new route, handling coordinate gaps.
*   **Export:** Generate valid TCX/GPX for external device use.

---

## 📋 Micro-Step Checklist

### 1. Geospatial Engine Port (The Foundation)
- [ ] **Step 1.1:** Initialize `src/features/maps/lib/`.
- [ ] **Step 1.2:** Copy and adapt `tcxParser.ts`, `climbDetection.ts`, `trackAnalysis.ts`, and `tcxExporter.ts` from `../tcx`.
- [ ] **Step 1.3:** Install dependencies: `maplibre-gl`, `react-map-gl`, `@turf/turf`, `@mapbox/togeojson`, `@xmldom/xmldom`.

### 2. Historical Heatmap (Backend & UI)
- [ ] **Step 2.1:** Backend implementation of `GET /api/maps/heatmap`.
  - Stream `lat, lon` from `ride_records`.
  - Use downsampling (e.g., every 5th point) to prevent browser crashing.
- [ ] **Step 2.2:** Create `<HeatmapLayer />` for MapLibre.
  - Test rendering performance with large datasets.

### 3. Segment Extraction UI
- [ ] **Step 3.1:** Integrate `ElevationProfile` with a range-scrubber.
- [ ] **Step 3.2:** Add "Extract Segment" action.
  - Store selected range coordinates in a temporary "Stitch Bin" (Pinia/Context/State).

### 4. Route Builder & Persistence
- [ ] **Step 4.1:** Build the `RouteBuilder` sidebar.
  - List extracted segments.
  - Add "Merge & Stitch" logic using `tcxExporter`.
- [ ] **Step 4.2:** Database schema for `planned_routes`.
  - Table: `id, name, user_id, route_geojson, route_tcx, created_at`.
- [ ] **Step 4.3:** Implement `POST /api/maps/routes` to save stitched paths.

---

## 🎯 Verification Criteria
*   The map successfully renders a **Heatmap** representing historical rides.
*   A user can **Extract** a segment from a ride, **Stitch** it with another, and **Save** the result.
*   The saved route is exportable and valid (verified via external TCX validator or `../tcx` tests).
