/**
 * Pure helpers for the Ride Map (Campaign 20).
 *
 * Kept free of any MapLibre / DOM imports so they unit-test without a
 * browser and don't bloat the main JS bundle.
 */
import type { RideRecord, RideLap } from '../types/api'

export const MAP_STYLE_URL =
  (import.meta.env.VITE_MAP_TILE_STYLE_URL as string | undefined)
  ?? 'https://tiles.openfreemap.org/styles/liberty'

/**
 * Reduce records to at most maxPoints `[lon, lat]` pairs (GeoJSON order)
 * by uniform stride sampling. Skips records with null lat/lon.
 *
 * Returns `[]` if fewer than 2 valid GPS points exist — callers should
 * treat that as "no map possible" (indoor / no-GPS ride).
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
  // Always include the final point so the polyline ends where the ride did.
  const last = valid[valid.length - 1]
  if (out[out.length - 1][0] !== last.lon || out[out.length - 1][1] !== last.lat) {
    out.push([last.lon, last.lat])
  }
  return out
}

/**
 * Compute the SW/NE bounding box for a list of `[lon, lat]` coords.
 * Returns `null` if coords is empty.
 *
 * Output shape matches `maplibregl.LngLatBoundsLike`:
 *   `[[minLon, minLat], [maxLon, maxLat]]`.
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

/**
 * For each chart sample (sample index 0..sampleCount-1) at a given downsample
 * step, return the index of the lap that contains it (or -1 if none).
 *
 * Lifted verbatim from the original inline copy in
 * `RideTimelineChart.tsx` so the chart and the map share one truth.
 *
 * Two strategies:
 *   - **Timestamp-based:** if both records and laps have ISO start times,
 *     compare absolute timestamps.
 *   - **Elapsed-time fallback:** otherwise, walk laps in order using their
 *     reported elapsed/timer durations.
 */
export function buildLapIndexMap(
  sampleCount: number,
  downsampleStep: number,
  records: { timestamp_utc?: string }[],
  laps: RideLap[],
): number[] {
  const firstRecordTs = records[0]?.timestamp_utc
  const firstLapTs = laps[0]?.start_time

  if (firstRecordTs && firstLapTs && firstRecordTs.length > 5 && firstLapTs.length > 5) {
    const lapTimes = laps.map(l => {
      const start = new Date(l.start_time || '').getTime()
      return { start, end: start + (l.total_elapsed_time || l.total_timer_time || 0) * 1000 }
    })

    const map: number[] = []
    for (let i = 0; i < sampleCount; i++) {
      const r = records[i * downsampleStep]
      if (!r || !r.timestamp_utc) { map.push(-1); continue }
      const t = new Date(r.timestamp_utc).getTime()
      map.push(lapTimes.findIndex(lt => t >= lt.start && t <= lt.end))
    }
    return map
  }

  let cumulative = 0
  const lapRanges = laps.map(l => {
    const start = cumulative
    const end = start + (l.total_elapsed_time || l.total_timer_time || 0)
    cumulative = end
    return { start, end }
  })

  const totalDuration = cumulative
  const totalRecords = records.length

  const map: number[] = []
  for (let i = 0; i < sampleCount; i++) {
    const recordIdx = i * downsampleStep
    const secs = totalRecords > 1 ? (recordIdx / (totalRecords - 1)) * totalDuration : 0
    const idx = lapRanges.findIndex(range => secs >= range.start && secs < range.end)
    map.push(idx)
  }
  return map
}

/**
 * Compute the [startIdx, endIdx] full-resolution record-array range
 * covered by a single lap.
 *
 * Returns `null` if the lap has no representative samples (e.g. the
 * record stream is shorter than the lap claims to be).
 *
 * Internally uses `buildLapIndexMap` with `downsampleStep = 1` so the
 * range is in *full-resolution* record indices, suitable for slicing
 * `RideDetail.records` and rendering on the map.
 */
export function lapRecordRange(
  records: { timestamp_utc?: string }[],
  laps: RideLap[],
  lapIndex: number,
): { startIdx: number; endIdx: number } | null {
  if (lapIndex < 0 || lapIndex >= laps.length) return null
  if (records.length === 0) return null
  const map = buildLapIndexMap(records.length, 1, records, laps)
  let firstIdx = -1
  let lastIdx = -1
  for (let i = 0; i < map.length; i++) {
    if (map[i] === lapIndex) {
      if (firstIdx === -1) firstIdx = i
      lastIdx = i
    }
  }
  if (firstIdx === -1) return null
  return { startIdx: firstIdx, endIdx: lastIdx }
}

/**
 * Slice a record array by full-resolution start/end indices and return
 * the corresponding `[lon, lat]` polyline (with nulls dropped).
 *
 * Used by the map to highlight a lap-slice or a drag-zoom-selected slice.
 */
export function sliceCoords(
  records: Pick<RideRecord, 'lat' | 'lon'>[],
  startIdx: number,
  endIdx: number,
): [number, number][] {
  const lo = Math.max(0, Math.min(startIdx, endIdx))
  const hi = Math.min(records.length - 1, Math.max(startIdx, endIdx))
  const out: [number, number][] = []
  for (let i = lo; i <= hi; i++) {
    const r = records[i]
    if (typeof r.lat === 'number' && typeof r.lon === 'number') {
      out.push([r.lon, r.lat])
    }
  }
  return out
}
