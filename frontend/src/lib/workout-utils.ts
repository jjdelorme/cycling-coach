import type { WorkoutStep } from '../types/api'

export interface StepActuals {
  actualPower: number | null
  powerDiff: number | null
  diffPct: number
  diffColor: string
}

export function calculateStepActuals(
  step: WorkoutStep,
  records: { power?: number }[]
): StepActuals {
  let actualPower: number | null = null
  let powerDiff: number | null = null
  let diffPct = 0
  let diffColor = 'text-text-muted'

  // Approximate step matching using index = seconds
  const startIdx = step.start_s
  const endIdx = step.start_s + step.duration_s
  const stepRecords = records.slice(startIdx, endIdx).filter(r => r.power != null)

  if (stepRecords.length > 0) {
    const sum = stepRecords.reduce((acc, r) => acc + (r.power || 0), 0)
    actualPower = Math.round(sum / stepRecords.length)
    powerDiff = actualPower - step.power_watts
    diffPct = step.power_watts > 0 ? (powerDiff / step.power_watts) * 100 : 0

    if (Math.abs(diffPct) <= 5) diffColor = 'text-green'
    else if (powerDiff > 0) diffColor = 'text-yellow'
    else diffColor = 'text-red'
  }

  return { actualPower, powerDiff, diffPct, diffColor }
}
