/**
 * Convert ISO week string (e.g. "2026-W14") to the Monday date string ("2026-03-30").
 */
export function isoWeekToMonday(isoWeek: string): string {
  const match = isoWeek.match(/^(\d{4})-W(\d{2})$/)
  if (!match) return ''
  const year = parseInt(match[1])
  const week = parseInt(match[2])

  // Jan 4 is always in week 1 (ISO 8601)
  const jan4 = new Date(year, 0, 4)
  const dow = jan4.getDay() || 7 // 1=Mon..7=Sun
  const week1Monday = new Date(jan4)
  week1Monday.setDate(jan4.getDate() - dow + 1)

  const target = new Date(week1Monday)
  target.setDate(week1Monday.getDate() + (week - 1) * 7)

  const y = target.getFullYear()
  const m = String(target.getMonth() + 1).padStart(2, '0')
  const d = String(target.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export interface PlannedWeekData {
  planned: { planned_tss?: number; total_duration_s?: number }[]
}

/**
 * Aggregate planned weeks into a Map keyed by Monday date string.
 * Each entry has total planned TSS and hours for that week.
 */
export function buildPlannedByMonday(
  mondays: string[],
  weekPlans: PlannedWeekData[],
): Map<string, { tss: number; hours: number }> {
  const map = new Map<string, { tss: number; hours: number }>()
  for (let i = 0; i < mondays.length && i < weekPlans.length; i++) {
    const wp = weekPlans[i]
    let tss = 0
    let seconds = 0
    for (const w of wp.planned) {
      tss += Number(w.planned_tss ?? 0)
      seconds += Number(w.total_duration_s ?? 0)
    }
    if (tss > 0 || seconds > 0) {
      map.set(mondays[i], { tss, hours: seconds / 3600 })
    }
  }
  return map
}
