import { describe, it, expect } from 'vitest'
import {
  decimatePolyline,
  polylineBounds,
  buildLapIndexMap,
  lapRecordRange,
  sliceCoords,
  detectGpsCorruption,
  MIN_GPS_RECORDS_FOR_DETECTION,
  CORRUPTION_RATIO_THRESHOLD,
} from './map'
import type { RideLap } from '../types/api'

describe('decimatePolyline', () => {
  it('returns [] for an empty array', () => {
    expect(decimatePolyline([])).toEqual([])
  })

  it('returns [] for a single point (need ≥ 2 to draw a line)', () => {
    expect(decimatePolyline([{ lat: 42, lon: -71 }])).toEqual([])
  })

  it('emits [lon, lat] order (GeoJSON), not [lat, lon]', () => {
    const out = decimatePolyline([
      { lat: 42, lon: -71 },
      { lat: 42.1, lon: -71.1 },
    ])
    expect(out).toEqual([[-71, 42], [-71.1, 42.1]])
  })

  it('passes through unchanged when count <= maxPoints', () => {
    const points = Array.from({ length: 50 }, (_, i) => ({ lat: 42 + i * 0.001, lon: -71 + i * 0.001 }))
    const out = decimatePolyline(points, 600)
    expect(out.length).toBe(50)
    expect(out[0]).toEqual([-71, 42])
    expect(out[49]).toEqual([-71 + 49 * 0.001, 42 + 49 * 0.001])
  })

  it('decimates a long track to roughly maxPoints, preserving endpoints', () => {
    // 1500 records / 600 maxPoints -> step = ceil(1500/600) = 3 -> ~500 samples
    // Always-include-last guarantees +1 if not already on an exact stride.
    const points = Array.from({ length: 1500 }, (_, i) => ({ lat: 42 + i * 0.0001, lon: -71 + i * 0.0001 }))
    const out = decimatePolyline(points, 600)
    // Stride of 3 across 1500 samples produces 500 stride-picks, +1 for last-point guarantee.
    expect(out.length).toBeGreaterThanOrEqual(500)
    expect(out.length).toBeLessThanOrEqual(601)
    // First record preserved
    expect(out[0]).toEqual([-71, 42])
    // Last record always included
    expect(out[out.length - 1]).toEqual([points[1499].lon, points[1499].lat])
  })

  it('decimates a 10000-point track down to ~600', () => {
    const points = Array.from({ length: 10000 }, (_, i) => ({ lat: 42 + i * 0.00001, lon: -71 + i * 0.00001 }))
    const out = decimatePolyline(points, 600)
    // step = ceil(10000/600) = 17, samples = ceil(10000/17) = 589, +1 last = 590
    expect(out.length).toBeLessThanOrEqual(602)
    expect(out.length).toBeGreaterThan(400)
    expect(out[out.length - 1]).toEqual([points[9999].lon, points[9999].lat])
  })

  it('skips records with null lat/lon', () => {
    const points: { lat: number | null | undefined; lon: number | null | undefined }[] = []
    for (let i = 0; i < 100; i++) {
      points.push(i % 2 === 0
        ? { lat: 42 + i * 0.001, lon: -71 + i * 0.001 }
        : { lat: null, lon: null })
    }
    const out = decimatePolyline(points as never)
    expect(out.length).toBe(50)
    // First valid point preserved
    expect(out[0]).toEqual([-71, 42])
  })

  it('returns [] when fewer than 2 points have GPS even if list is long', () => {
    const points = [
      { lat: null, lon: null },
      { lat: 42, lon: -71 },
      { lat: undefined, lon: undefined },
    ]
    expect(decimatePolyline(points as never)).toEqual([])
  })
})

describe('polylineBounds', () => {
  it('returns null for empty input', () => {
    expect(polylineBounds([])).toBeNull()
  })

  it('returns degenerate bounds for a single point', () => {
    expect(polylineBounds([[-71.5, 42.0]])).toEqual([[-71.5, 42.0], [-71.5, 42.0]])
  })

  it('computes [[minLon, minLat], [maxLon, maxLat]] for multiple points', () => {
    const out = polylineBounds([
      [-71.5, 42.0],
      [-71.0, 42.5],
      [-71.2, 42.1],
    ])
    expect(out).toEqual([[-71.5, 42.0], [-71.0, 42.5]])
  })
})

describe('buildLapIndexMap', () => {
  it('uses timestamp matching when both records and laps have ISO timestamps', () => {
    // Boundary semantics: lap 0 spans [start, end] inclusive, so a record AT
    // lap 0's end (== lap 1's start) maps to lap 0 (findIndex returns first).
    const records = [
      { timestamp_utc: '2026-04-22T10:00:00Z' }, // in lap 0
      { timestamp_utc: '2026-04-22T10:00:30Z' }, // in lap 0
      { timestamp_utc: '2026-04-22T10:01:00Z' }, // boundary -> lap 0
      { timestamp_utc: '2026-04-22T10:01:30Z' }, // in lap 1
      { timestamp_utc: '2026-04-22T10:01:59Z' }, // in lap 1
    ]
    const laps: RideLap[] = [
      { lap_index: 0, start_time: '2026-04-22T10:00:00Z', total_elapsed_time: 60 },
      { lap_index: 1, start_time: '2026-04-22T10:01:00Z', total_elapsed_time: 60 },
    ]
    const map = buildLapIndexMap(5, 1, records, laps)
    expect(map).toEqual([0, 0, 0, 1, 1])
  })

  it('falls back to elapsed-time partitioning when timestamps are missing', () => {
    const records = Array.from({ length: 100 }, () => ({}))
    const laps: RideLap[] = [
      { lap_index: 0, total_elapsed_time: 30 },
      { lap_index: 1, total_elapsed_time: 30 },
    ]
    const map = buildLapIndexMap(10, 10, records, laps)
    expect(map.length).toBe(10)
    // First half should map to lap 0, second half to lap 1.
    expect(map[0]).toBe(0)
    expect(map[9]).toBe(1)
  })

  it('handles a single-lap ride (every sample maps to lap 0)', () => {
    const records = Array.from({ length: 20 }, (_, i) => ({
      timestamp_utc: `2026-04-22T10:00:${String(i).padStart(2, '0')}Z`,
    }))
    const laps: RideLap[] = [
      { lap_index: 0, start_time: '2026-04-22T10:00:00Z', total_elapsed_time: 30 },
    ]
    const map = buildLapIndexMap(20, 1, records, laps)
    expect(map.every(i => i === 0)).toBe(true)
  })

  it('handles no records (returns sampleCount entries of -1 in fallback)', () => {
    const map = buildLapIndexMap(5, 1, [], [
      { lap_index: 0, total_elapsed_time: 30 },
    ])
    expect(map.length).toBe(5)
  })
})

describe('lapRecordRange', () => {
  // Boundary record at t=30 (lap 0 end == lap 1 start) maps to lap 0
  // because lap 0 has the inclusive end semantics first.
  const records = [
    { timestamp_utc: '2026-04-22T10:00:00Z' },
    { timestamp_utc: '2026-04-22T10:00:10Z' },
    { timestamp_utc: '2026-04-22T10:00:20Z' },
    { timestamp_utc: '2026-04-22T10:00:30Z' }, // boundary -> lap 0
    { timestamp_utc: '2026-04-22T10:00:40Z' },
    { timestamp_utc: '2026-04-22T10:00:50Z' },
  ]
  const laps: RideLap[] = [
    { lap_index: 0, start_time: '2026-04-22T10:00:00Z', total_elapsed_time: 30 },
    { lap_index: 1, start_time: '2026-04-22T10:00:30Z', total_elapsed_time: 30 },
  ]

  it('returns the first/last record indices belonging to a lap', () => {
    expect(lapRecordRange(records, laps, 0)).toEqual({ startIdx: 0, endIdx: 3 })
    expect(lapRecordRange(records, laps, 1)).toEqual({ startIdx: 4, endIdx: 5 })
  })

  it('returns null for an out-of-range lap index', () => {
    expect(lapRecordRange(records, laps, 99)).toBeNull()
    expect(lapRecordRange(records, laps, -1)).toBeNull()
  })

  it('returns null when records list is empty', () => {
    expect(lapRecordRange([], laps, 0)).toBeNull()
  })
})

describe('sliceCoords', () => {
  const records = [
    { lat: 42, lon: -71 },
    { lat: 42.1, lon: -71.1 },
    { lat: null, lon: null },
    { lat: 42.3, lon: -71.3 },
    { lat: 42.4, lon: -71.4 },
  ]

  it('returns [lon, lat] coords for the inclusive slice, dropping nulls', () => {
    const out = sliceCoords(records as never, 0, 4)
    expect(out).toEqual([
      [-71, 42],
      [-71.1, 42.1],
      [-71.3, 42.3],
      [-71.4, 42.4],
    ])
  })

  it('clamps out-of-range indices to the record array', () => {
    const out = sliceCoords(records as never, -5, 99)
    expect(out.length).toBe(4)
  })

  it('handles reversed indices (treats as low/high)', () => {
    const out = sliceCoords(records as never, 4, 1)
    expect(out).toEqual([
      [-71.1, 42.1],
      [-71.3, 42.3],
      [-71.4, 42.4],
    ])
  })

  it('returns [] when the slice has no GPS points', () => {
    const noGps = [
      { lat: null, lon: null },
      { lat: null, lon: null },
    ]
    expect(sliceCoords(noGps as never, 0, 1)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Composition tests — exercise the same helper sequence that <RideMap>'s
// highlight effect runs at runtime. Locks in the contract that Phase 4's
// drag-zoom-range and lap-selection paths produce a usable polyline slice.
// ---------------------------------------------------------------------------

describe('drag-zoom + lap highlight composition', () => {
  // 10-record synthetic outdoor ride with 2 laps.
  const records = Array.from({ length: 10 }, (_, i) => ({
    timestamp_utc: `2026-04-22T10:00:${String(i * 10).padStart(2, '0')}Z`,
    lat: 42 + i * 0.001,
    lon: -71 + i * 0.001,
  }))
  const laps: RideLap[] = [
    { lap_index: 0, start_time: '2026-04-22T10:00:00Z', total_elapsed_time: 50 },
    { lap_index: 1, start_time: '2026-04-22T10:00:50Z', total_elapsed_time: 50 },
  ]

  it('drag-zoom range -> sliceCoords yields the expected polyline', () => {
    // User drag-selected indices 2..7 (full-resolution).
    const out = sliceCoords(records, 2, 7)
    expect(out.length).toBe(6)
    expect(out[0]).toEqual([-71 + 2 * 0.001, 42 + 2 * 0.001])
    expect(out[5]).toEqual([-71 + 7 * 0.001, 42 + 7 * 0.001])
  })

  it('lap selection -> lapRecordRange + sliceCoords yields the lap polyline', () => {
    const range = lapRecordRange(records, laps, 0)
    expect(range).not.toBeNull()
    const out = sliceCoords(records, range!.startIdx, range!.endIdx)
    // Lap 0 covers records 0..5 (boundary record at t=50 maps to lap 0).
    expect(out.length).toBeGreaterThanOrEqual(5)
    expect(out[0]).toEqual([-71, 42])
  })

  it('drag-zoom precedence: when both selectedTimeRange and selectedLap exist, the time-range slice is what we use', () => {
    // This mirrors RideMap's effect: if selectedTimeRange is set, prefer it.
    const selectedTimeRange = { startIdx: 1, endIdx: 3 }
    const selectedLap: number | null = 0

    const slice = selectedTimeRange
      ? sliceCoords(records, selectedTimeRange.startIdx, selectedTimeRange.endIdx)
      : selectedLap != null
        ? (() => {
            const r = lapRecordRange(records, laps, selectedLap)
            return r ? sliceCoords(records, r.startIdx, r.endIdx) : []
          })()
        : []

    expect(slice.length).toBe(3)
    // First coord is record index 1, not record index 0 (the lap-0 start).
    expect(slice[0]).toEqual([-71 + 0.001, 42 + 0.001])
  })

  it('clearing both selections produces an empty highlight slice (full route restored)', () => {
    const selectedTimeRange = null
    const selectedLap: number | null = null
    const slice: [number, number][] = selectedTimeRange
      ? sliceCoords(records, 0, 0)
      : selectedLap != null
        ? sliceCoords(records, 0, 0)
        : []
    expect(slice).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// detectGpsCorruption (Phase 10 / D4)
//
// Mirrors the backend constants in `server/services/sync.py`:
//   MIN_GPS_RECORDS_FOR_DETECTION = 60
//   GPS_CORRUPTION_RATIO_THRESHOLD = 0.5
// Same numeric values must live on both sides — backend write-time guard
// (Phase 7), backfill detector (Phase 9), and this frontend safeguard.
// ---------------------------------------------------------------------------

describe('detectGpsCorruption', () => {
  it('returns { total: 0, suspect: 0, corrupt: false } for an empty array', () => {
    expect(detectGpsCorruption([])).toEqual({ total: 0, suspect: 0, corrupt: false })
  })

  it('flags 100 records with lat ≈ lon as corrupt', () => {
    const records = Array.from({ length: 100 }, () => ({ lat: 39.75, lon: 39.75 }))
    const result = detectGpsCorruption(records)
    expect(result.total).toBe(100)
    expect(result.suspect).toBe(100)
    expect(result.corrupt).toBe(true)
  })

  it('passes 100 real US records (lat positive, lon negative) as not corrupt', () => {
    const records = Array.from({ length: 100 }, () => ({ lat: 39.75, lon: -105.3 }))
    const result = detectGpsCorruption(records)
    expect(result.total).toBe(100)
    expect(result.suspect).toBe(0)
    expect(result.corrupt).toBe(false)
  })

  it('does NOT flag 30 lat ≈ lon records — below the MIN_GPS_RECORDS gate', () => {
    const records = Array.from({ length: 30 }, () => ({ lat: 39.75, lon: 39.75 }))
    const result = detectGpsCorruption(records)
    expect(result.total).toBe(30)
    expect(result.corrupt).toBe(false)
  })

  it('exposes the threshold constants for cross-module reuse', () => {
    // Locked at the same numeric values as the backend constants.
    expect(MIN_GPS_RECORDS_FOR_DETECTION).toBe(60)
    expect(CORRUPTION_RATIO_THRESHOLD).toBe(0.5)
  })
})
