import { describe, it, expect } from 'vitest'
import { calculateStepActuals } from './workout-utils'
import type { WorkoutStep } from '../types/api'

describe('calculateStepActuals', () => {
  const mockStep: WorkoutStep = {
    type: 'work',
    label: 'Interval',
    start_s: 10,
    duration_s: 10,
    power_watts: 200,
    power_pct: 0.8
  }

  it('calculates average power and diff correctly', () => {
    const records = Array.from({ length: 30 }, (_, i) => ({
      power: i >= 10 && i < 20 ? 210 : 100
    }))

    const result = calculateStepActuals(mockStep, records)
    expect(result.actualPower).toBe(210)
    expect(result.powerDiff).toBe(10)
    expect(result.diffPct).toBe(5)
    expect(result.diffColor).toBe('text-green')
  })

  it('handles negative diff and red color', () => {
    const records = Array.from({ length: 30 }, (_, i) => ({
      power: i >= 10 && i < 20 ? 180 : 100
    }))

    const result = calculateStepActuals(mockStep, records)
    expect(result.actualPower).toBe(180)
    expect(result.powerDiff).toBe(-20)
    expect(result.diffPct).toBe(-10)
    expect(result.diffColor).toBe('text-red')
  })

  it('handles positive diff and yellow color', () => {
    const records = Array.from({ length: 30 }, (_, i) => ({
      power: i >= 10 && i < 20 ? 220 : 100
    }))

    const result = calculateStepActuals(mockStep, records)
    expect(result.actualPower).toBe(220)
    expect(result.powerDiff).toBe(20)
    expect(result.diffPct).toBe(10)
    expect(result.diffColor).toBe('text-yellow')
  })

  it('returns nulls when no records match', () => {
    const records: { power: number }[] = []
    const result = calculateStepActuals(mockStep, records)
    expect(result.actualPower).toBeNull()
    expect(result.powerDiff).toBeNull()
  })
})
