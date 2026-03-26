import { useState, useMemo } from 'react'
import { useRides } from '../hooks/useApi'
import { fetchWeekPlan } from '../lib/api'
import { fmtDuration } from '../lib/format'
import { useQuery } from '@tanstack/react-query'
import type { PlannedWorkout, RideSummary } from '../types/api'

interface Props {
  onRideSelect: (id: number) => void
  onWorkoutSelect: (id: number, date: string) => void
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const DAY_HEADERS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** Return YYYY-MM-DD string for a Date in local time. */
function toDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Get the Monday-start week date (YYYY-MM-DD) for a given date. */
function weekMonday(d: Date): Date {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const dow = copy.getDay() // 0=Sun
  const diff = dow === 0 ? -6 : 1 - dow
  copy.setDate(copy.getDate() + diff)
  return copy
}

/** Build the grid of dates displayed for a given month (Mon-start weeks). */
function buildCalendarDays(year: number, month: number): Date[] {
  const firstOfMonth = new Date(year, month, 1)
  const lastOfMonth = new Date(year, month + 1, 0)
  const startDate = weekMonday(firstOfMonth)
  // End on the Sunday that covers the last day of the month
  const endSunday = new Date(lastOfMonth)
  const dow = endSunday.getDay()
  if (dow !== 0) {
    endSunday.setDate(endSunday.getDate() + (7 - dow))
  }

  const days: Date[] = []
  const cursor = new Date(startDate)
  while (cursor <= endSunday) {
    days.push(new Date(cursor))
    cursor.setDate(cursor.getDate() + 1)
  }
  return days
}

/** Collect the distinct Monday dates that overlap the displayed calendar grid. */
function getWeekMondays(calendarDays: Date[]): string[] {
  const set = new Set<string>()
  for (const d of calendarDays) {
    set.add(toDateStr(weekMonday(d)))
  }
  return Array.from(set).sort()
}

export default function Calendar({ onRideSelect, onWorkoutSelect }: Props) {
  const [currentDate, setCurrentDate] = useState(() => {
    const now = new Date()
    return { year: now.getFullYear(), month: now.getMonth() }
  })
  const [selectedDay, setSelectedDay] = useState<string | null>(null)

  const calendarDays = useMemo(
    () => buildCalendarDays(currentDate.year, currentDate.month),
    [currentDate.year, currentDate.month],
  )

  const weekMondays = useMemo(() => getWeekMondays(calendarDays), [calendarDays])

  // Date range for rides query: first and last day shown on the grid
  const gridStart = toDateStr(calendarDays[0])
  const gridEnd = toDateStr(calendarDays[calendarDays.length - 1])

  const { data: rides } = useRides({ start_date: gridStart, end_date: gridEnd, limit: 500 })

  // Fetch week plans for every Monday visible on the grid, then merge
  const { data: weekPlans, refetch } = useQuery({
    queryKey: ['calendar-week-plans', weekMondays],
    queryFn: async () => {
      const results = await Promise.all(weekMondays.map((m) => fetchWeekPlan(m)))
      return results
    },
    enabled: weekMondays.length > 0,
  })

  // Deduplicate planned workouts by id
  const allWorkouts = useMemo(() => {
    if (!weekPlans) return []
    const seen = new Set<number>()
    const result: PlannedWorkout[] = []
    for (const wp of weekPlans) {
      for (const w of wp.planned) {
        if (w.id && !seen.has(w.id)) {
          seen.add(w.id)
          result.push(w)
        }
      }
    }
    return result
  }, [weekPlans])

  // Index rides and workouts by date string
  const ridesByDate = useMemo(() => {
    const map = new Map<string, RideSummary[]>()
    if (!rides) return map
    for (const r of rides) {
      const d = r.date?.slice(0, 10)
      if (!d) continue
      if (!map.has(d)) map.set(d, [])
      map.get(d)!.push(r)
    }
    return map
  }, [rides])

  const workoutsByDate = useMemo(() => {
    const map = new Map<string, PlannedWorkout[]>()
    for (const w of allWorkouts) {
      const d = w.date?.slice(0, 10)
      if (!d) continue
      if (!map.has(d)) map.set(d, [])
      map.get(d)!.push(w)
    }
    return map
  }, [allWorkouts])

  // Navigation
  function prevMonth() {
    setCurrentDate((prev) => {
      const m = prev.month - 1
      return m < 0
        ? { year: prev.year - 1, month: 11 }
        : { year: prev.year, month: m }
    })
    setSelectedDay(null)
  }

  function nextMonth() {
    setCurrentDate((prev) => {
      const m = prev.month + 1
      return m > 11
        ? { year: prev.year + 1, month: 0 }
        : { year: prev.year, month: m }
    })
    setSelectedDay(null)
  }

  // Detail panel data
  const selectedRides = selectedDay ? ridesByDate.get(selectedDay) ?? [] : []
  const selectedWorkouts = selectedDay ? workoutsByDate.get(selectedDay) ?? [] : []

  return (
    <div className="space-y-4">
      {/* Month navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={prevMonth}
          className="px-3 py-1 rounded bg-surface hover:bg-surface2 text-text border border-border"
        >
          &larr;
        </button>
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-text">
            {MONTH_NAMES[currentDate.month]} {currentDate.year}
          </h2>
          <button
            onClick={() => refetch()}
            className="px-2 py-1 rounded bg-surface hover:bg-surface2 text-text-muted border border-border text-sm"
            title="Refresh"
          >
            &#x21bb;
          </button>
        </div>
        <button
          onClick={nextMonth}
          className="px-3 py-1 rounded bg-surface hover:bg-surface2 text-text border border-border"
        >
          &rarr;
        </button>
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-px bg-border rounded overflow-hidden">
        {/* Day headers */}
        {DAY_HEADERS.map((d) => (
          <div key={d} className="bg-surface2 text-text-muted text-center text-xs font-medium py-1">
            {d}
          </div>
        ))}

        {/* Day cells */}
        {calendarDays.map((date) => {
          const dateStr = toDateStr(date)
          const isCurrentMonth = date.getMonth() === currentDate.month
          const isToday = dateStr === toDateStr(new Date())
          const isSelected = dateStr === selectedDay
          const dayRides = ridesByDate.get(dateStr) ?? []
          const dayWorkouts = workoutsByDate.get(dateStr) ?? []
          const totalTSS = dayRides.reduce((sum, r) => sum + (r.tss ?? 0), 0)

          return (
            <div
              key={dateStr}
              onClick={() => {
                // Navigate directly: ride takes priority, then workout, otherwise toggle detail panel
                if (dayRides.length > 0) {
                  onRideSelect(dayRides[0].id)
                } else if (dayWorkouts.length > 0 && dayWorkouts[0].id) {
                  onWorkoutSelect(dayWorkouts[0].id, dateStr)
                } else {
                  setSelectedDay(isSelected ? null : dateStr)
                }
              }}
              className={`
                min-h-[80px] md:min-h-[100px] p-1 cursor-pointer transition-colors
                ${isCurrentMonth ? 'bg-surface' : 'bg-bg'}
                ${isToday ? 'ring-2 ring-accent ring-inset' : ''}
                ${isSelected && !isToday ? 'ring-2 ring-text-muted ring-inset' : ''}
                hover:bg-surface2
              `}
            >
              <div className={`text-xs font-medium ${isToday ? 'text-accent font-bold' : isCurrentMonth ? 'text-text' : 'text-text-muted'}`}>
                {date.getDate()}
              </div>

              <div className="mt-0.5 space-y-0.5 overflow-hidden">
                {/* Rides */}
                {dayRides.map((r) => (
                  <div
                    key={r.id}
                    onClick={(e) => { e.stopPropagation(); onRideSelect(r.id) }}
                    className="text-[10px] md:text-xs text-green truncate cursor-pointer hover:underline"
                  >
                    {r.sport ?? 'Ride'}{r.tss ? ` ${Math.round(r.tss)}` : ''}
                  </div>
                ))}

                {/* Planned workouts */}
                {dayWorkouts.map((w, i) => (
                  <div
                    key={w.id ?? i}
                    onClick={(e) => { e.stopPropagation(); onWorkoutSelect(w.id, dateStr) }}
                    className="text-[10px] md:text-xs text-yellow truncate cursor-pointer hover:underline"
                  >
                    {w.name ?? 'Workout'}
                  </div>
                ))}

                {/* Total TSS */}
                {dayRides.length > 0 && totalTSS > 0 && (
                  <div className="text-[10px] text-text-muted">
                    TSS {Math.round(totalTSS)}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Day detail panel */}
      {selectedDay && (
        <div className="bg-surface border border-border rounded-lg p-4">
          <h3 className="text-text font-semibold mb-2">
            {new Date(selectedDay + 'T00:00:00').toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
              year: 'numeric',
            })}
          </h3>

          {selectedRides.length === 0 && selectedWorkouts.length === 0 && (
            <p className="text-text-muted text-sm">Rest day</p>
          )}

          {selectedRides.length > 0 && (
            <div className="mb-3">
              <h4 className="text-text-muted text-xs uppercase tracking-wide mb-1">Rides</h4>
              <ul className="space-y-1">
                {selectedRides.map((r) => (
                  <li key={r.id}>
                    <button
                      onClick={() => onRideSelect(r.id)}
                      className="text-sm text-green hover:text-accent underline text-left"
                    >
                      {r.sport ?? 'Ride'}
                      {r.tss ? ` - TSS ${Math.round(r.tss)}` : ''}
                      {r.duration_s ? ` - ${fmtDuration(r.duration_s)}` : ''}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {selectedWorkouts.length > 0 && (
            <div>
              <h4 className="text-text-muted text-xs uppercase tracking-wide mb-1">Planned Workouts</h4>
              <ul className="space-y-1">
                {selectedWorkouts.map((w, i) => (
                  <li key={w.id ?? i}>
                    {w.id ? (
                      <button
                        onClick={() => onWorkoutSelect(w.id, selectedDay!)}
                        className="text-sm text-yellow hover:text-accent underline text-left"
                      >
                        {w.name ?? 'Workout'}
                        {w.total_duration_s ? ` - ${fmtDuration(w.total_duration_s)}` : ''}
                      </button>
                    ) : (
                      <span className="text-sm text-yellow">
                        {w.name ?? 'Workout'}
                        {w.total_duration_s ? ` - ${fmtDuration(w.total_duration_s)}` : ''}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
