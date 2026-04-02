import { describe, it, expect } from 'vitest'
import { isoWeekToMonday, buildPlannedByMonday, calculateChartSampling } from './chart-helpers'

describe('isoWeekToMonday', () => {
  it('converts a standard ISO week to Monday date', () => {
    // 2026-W14 starts Monday March 30, 2026
    expect(isoWeekToMonday('2026-W14')).toBe('2026-03-30')
  })

  it('converts week 1 correctly', () => {
    // 2026-W01 starts Monday Dec 29, 2025
    expect(isoWeekToMonday('2026-W01')).toBe('2025-12-29')
  })

  it('converts a mid-year week', () => {
    // 2026-W26 starts Monday June 22, 2026
    expect(isoWeekToMonday('2026-W26')).toBe('2026-06-22')
  })

  it('returns empty string for invalid input', () => {
    expect(isoWeekToMonday('invalid')).toBe('')
    expect(isoWeekToMonday('2026-14')).toBe('')
    expect(isoWeekToMonday('')).toBe('')
  })
})

describe('buildPlannedByMonday', () => {
  it('aggregates planned TSS and hours by monday', () => {
    const mondays = ['2026-03-30', '2026-04-06']
    const weekPlans = [
      { planned: [{ planned_tss: 100, total_duration_s: 3600 }, { planned_tss: 50, total_duration_s: 1800 }] },
      { planned: [{ planned_tss: 200, total_duration_s: 7200 }] },
    ]
    const result = buildPlannedByMonday(mondays, weekPlans)
    expect(result.get('2026-03-30')).toEqual({ tss: 150, hours: 1.5 })
    expect(result.get('2026-04-06')).toEqual({ tss: 200, hours: 2 })
  })

  it('skips weeks with no planned data', () => {
    const mondays = ['2026-03-30']
    const weekPlans = [{ planned: [] }]
    const result = buildPlannedByMonday(mondays, weekPlans)
    expect(result.size).toBe(0)
  })

  it('handles empty arrays', () => {
    const result = buildPlannedByMonday([], [])
    expect(result.size).toBe(0)
  })

  it('handles mismatched array lengths', () => {
    const mondays = ['2026-03-30', '2026-04-06', '2026-04-13']
    const weekPlans = [{ planned: [{ planned_tss: 100, total_duration_s: 3600 }] }]
    const result = buildPlannedByMonday(mondays, weekPlans)
    expect(result.size).toBe(1)
    expect(result.get('2026-03-30')).toEqual({ tss: 100, hours: 1 })
  })
})

describe('calculateChartSampling', () => {
  const records = Array.from({ length: 1000 }, (_, i) => ({ timestamp_utc: `2024-01-01T00:00:${i}Z`, power: i }))

  it('samples correctly when records are longer than planned', () => {
    const plannedDuration = 500
    const maxPoints = 100
    const { sampled, step, maxDuration } = calculateChartSampling(records, plannedDuration, maxPoints)

    expect(maxDuration).toBe(1000)
    expect(step).toBe(10)
    expect(sampled.length).toBe(100)
    expect(sampled[0].power).toBe(0)
    expect(sampled[1].power).toBe(10)
  })

  it('samples correctly when planned is longer than actual', () => {
    const plannedDuration = 2000
    const maxPoints = 200
    const { sampled, step, maxDuration } = calculateChartSampling(records, plannedDuration, maxPoints)

    expect(maxDuration).toBe(2000)
    expect(step).toBe(10)
    expect(sampled.length).toBe(200)
    expect(sampled[0].power).toBe(0)
    expect(sampled[99].power).toBe(990)
    expect(sampled[100]).toEqual({})
  })

  it('handles planned only case', () => {
    const plannedDuration = 1000
    const maxPoints = 100
    const { sampled, step, maxDuration } = calculateChartSampling([], plannedDuration, maxPoints)

    expect(maxDuration).toBe(1000)
    expect(step).toBe(10)
    expect(sampled.length).toBe(100)
    expect(sampled[0]).toEqual({})
  })

  it('uses default maxPoints if not provided', () => {
    const { sampled, step } = calculateChartSampling(records, 0)
    expect(step).toBe(Math.floor(1000 / 600))
    expect(sampled.length).toBe(Math.ceil(1000 / step))
  })
})
