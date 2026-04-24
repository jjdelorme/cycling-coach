import { useEffect, useMemo, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { AlertTriangle, Map as MapIcon } from 'lucide-react'
import type { RideRecord, RideLap } from '../types/api'
import {
  MAP_STYLE,
  decimatePolyline,
  detectGpsCorruption,
  polylineBounds,
  lapRecordRange,
  sliceCoords,
} from '../lib/map'

interface Props {
  records: RideRecord[]
  laps?: RideLap[]
  /**
   * Full-resolution `records[]` index of the chart's hovered time, or null
   * when the cursor is outside the chart. Drives the moving marker.
   * (Campaign 20 — Phase 3.)
   */
  hoveredTimeIdx?: number | null
  /**
   * Index into `laps[]` that the user has clicked. When set, the map dims
   * the full route and highlights the lap's slice + recentres on it.
   * (Campaign 20 — Phase 4.)
   */
  selectedLap?: number | null
  /**
   * Full-resolution start/end indices for a drag-zoom-selected time range
   * on the timeline chart. When set, the map highlights this slice and
   * auto-fits to its bounds.
   *
   * Precedence: drag-zoom range wins over `selectedLap` if both are set —
   * the drag is the more recent explicit action.
   * (Campaign 20 — Phase 4 scope addendum.)
   */
  selectedTimeRange?: { startIdx: number; endIdx: number } | null
}

const HIGHLIGHT_COLOR = '#00d4aa'

/**
 * Route map for the ride detail pane.
 *
 * Behaviour:
 * - Renders the decimated GPS polyline on an OpenFreeMap "liberty" basemap.
 * - Auto-fits initial bounds to the polyline.
 * - Hover-syncs a marker from the timeline chart (no auto-pan — that would
 *   feel like vertigo while scrubbing).
 * - Highlights the selected lap or drag-zoom-selected slice and refits.
 *
 * Indoor / no-GPS rides (< 2 valid lat/lon records) render a placeholder
 * card instead of an empty map.
 */
export default function RideMap({
  records,
  laps = [],
  hoveredTimeIdx = null,
  selectedLap = null,
  selectedTimeRange = null,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markerRef = useRef<maplibregl.Marker | null>(null)
  // Tracks whether the map's `load` event has fired — sources/layers can
  // only be added after that.
  const mapLoadedRef = useRef(false)

  const coords = useMemo(() => decimatePolyline(records, 600), [records])
  const fullBounds = useMemo(() => polylineBounds(coords), [coords])
  // Campaign 20 D4 — frontend safeguard. If the per-record GPS trips the
  // corruption signature (≥60 records, >50% with |lat-lon|<1°), render a
  // banner instructing the operator to re-sync rather than displaying a
  // wrong polyline. Wraps the same numeric thresholds as the backend
  // write-time guard and the historical backfill detector.
  const corruption = useMemo(() => detectGpsCorruption(records), [records])

  // ── Map init / teardown ────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return
    if (coords.length < 2) return // placeholder rendered in JSX path below

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      attributionControl: { compact: true },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.FullscreenControl(), 'top-right')
    // Surface tile / style failures so they're visible in DevTools rather
    // than silently leaving the basemap blank.
    map.on('error', (e) => {
      console.error('[RideMap] MapLibre error:', e?.error || e)
    })
    mapRef.current = map
    mapLoadedRef.current = false

    map.on('load', () => {
      mapLoadedRef.current = true
      map.addSource('route', {
        type: 'geojson',
        data: {
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: coords },
          properties: {},
        },
      })
      // Highlighted slice — empty until a lap or range is selected.
      map.addSource('route-highlight', {
        type: 'geojson',
        data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] }, properties: {} },
      })
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': HIGHLIGHT_COLOR, 'line-width': 3, 'line-opacity': 0.9 },
      })
      map.addLayer({
        id: 'route-highlight-line',
        type: 'line',
        source: 'route-highlight',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': HIGHLIGHT_COLOR, 'line-width': 5, 'line-opacity': 1.0 },
      })
      if (fullBounds) map.fitBounds(fullBounds, { padding: 40, duration: 0 })
    })

    return () => {
      markerRef.current?.remove()
      markerRef.current = null
      map.remove()
      mapRef.current = null
      mapLoadedRef.current = false
    }
    // We deliberately key this effect on `coords` (not `records`) so a parent
    // re-render that doesn't change coordinates doesn't tear down the map.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coords])

  // ── Hover marker (Phase 3) ─────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const r = hoveredTimeIdx != null ? records[hoveredTimeIdx] : undefined
    const lat = r?.lat
    const lon = r?.lon
    if (typeof lat !== 'number' || typeof lon !== 'number') {
      markerRef.current?.remove()
      markerRef.current = null
      return
    }
    if (!markerRef.current) {
      const el = document.createElement('div')
      el.className = 'maplibregl-marker'
      el.style.cssText =
        'width:14px;height:14px;border-radius:50%;background:#00d4aa;' +
        'border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,0.4);' +
        'pointer-events:none'
      markerRef.current = new maplibregl.Marker({ element: el })
        .setLngLat([lon, lat])
        .addTo(map)
    } else {
      markerRef.current.setLngLat([lon, lat])
    }
    // Note: we deliberately do NOT pan/fly the map on hover. Auto-pan during
    // scrub causes vertigo. Pan only happens on init and on selection changes.
  }, [hoveredTimeIdx, records])

  // ── Highlighted slice + auto-fit (Phase 4) ─────────────────────────────
  // Precedence: drag-zoom-selected range wins over a lap selection if both
  // are set — the drag is the more recent explicit user action.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    // Resolve which slice (if any) to highlight.
    let slice: [number, number][] = []
    if (selectedTimeRange) {
      slice = sliceCoords(records, selectedTimeRange.startIdx, selectedTimeRange.endIdx)
    } else if (selectedLap != null && laps.length > 0) {
      const range = lapRecordRange(records, laps, selectedLap)
      if (range) slice = sliceCoords(records, range.startIdx, range.endIdx)
    }

    const apply = () => {
      const src = map.getSource('route-highlight') as maplibregl.GeoJSONSource | undefined
      const lineLayer = map.getLayer('route-line')
      if (!src || !lineLayer) return
      src.setData({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: slice },
        properties: {},
      })
      // Dim the full route only when something is highlighted.
      map.setPaintProperty('route-line', 'line-opacity', slice.length >= 2 ? 0.25 : 0.9)
      if (slice.length >= 2) {
        const sliceBounds = polylineBounds(slice)
        if (sliceBounds) map.fitBounds(sliceBounds, { padding: 40, duration: 400 })
      } else if (fullBounds) {
        map.fitBounds(fullBounds, { padding: 40, duration: 400 })
      }
    }

    if (mapLoadedRef.current) {
      apply()
    } else {
      // The map's `load` event hasn't fired yet — defer until it has so the
      // source/layer exist. `once` cleans itself up.
      map.once('load', apply)
    }
  }, [selectedLap, selectedTimeRange, records, laps, fullBounds])

  if (corruption.corrupt) {
    // D7 — exact copy locked in plan: do NOT auto-trigger a re-sync, just
    // explain the action so the user knows where to fix it. The map is
    // intentionally NOT rendered (better than a wrong polyline).
    // Theme note: there is no `warning` color token in the index.css
    // palette, so we use `yellow` (the existing "caution" hue at #f5c518)
    // which is what other warning-style UIs in this codebase reach for.
    return (
      <section className="bg-surface rounded-xl border border-yellow/30 p-6 text-center">
        <AlertTriangle size={28} className="mx-auto mb-3 text-yellow" />
        <p className="text-xs font-medium text-yellow">
          GPS data appears corrupted for this ride.
        </p>
        <p className="text-[11px] text-text-muted mt-1">
          Re-sync this ride to fix (Settings → Sync → Re-sync this ride).
        </p>
      </section>
    )
  }

  if (coords.length < 2) {
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
