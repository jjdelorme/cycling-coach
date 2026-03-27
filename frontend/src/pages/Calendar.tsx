import { useState, useMemo } from 'react'
import { useRides, useDeleteWorkout } from '../hooks/useApi'
import { fetchWeekPlan } from '../lib/api'
import { fmtDuration, fmtDistance } from '../lib/format'
import { useUnits } from '../lib/units'
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
  const units = useUnits()
  const deleteWorkout = useDeleteWorkout()
  const [currentDate, setCurrentDate] = useState(() => {
    const now = new Date()
    return { year: now.getFullYear(), month: now.getMonth() }
  })
  const [selectedDay, setSelectedDay] = useState<string | null>(() => toDateStr(new Date()))

  const calendarDays = useMemo(
    () => buildCalendarDays(currentDate.year, currentDate.month),
    [currentDate.year, currentDate.month],
  )

  const weekMondays = useMemo(() => getWeekMondays(calendarDays), [calendarDays])

  // Date range for rides query: first and last day shown on the grid
  const gridStart = toDateStr(calendarDays[0])
  const gridEnd = toDateStr(calendarDays[calendarDays.length - 1])

  const { data: rides, isLoading: ridesLoading } = useRides({ start_date: gridStart, end_date: gridEnd, limit: 500 })

  // Fetch week plans for every Monday visible on the grid, then merge
  const { data: weekPlans, isLoading: plansLoading, refetch } = useQuery({
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

      {/* Loading spinner */}
      {(ridesLoading || plansLoading) && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-border border-t-accent" />
        </div>
      )}

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
              onClick={() => setSelectedDay(isSelected ? null : dateStr)}
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
                    className="text-[10px] md:text-xs text-green truncate"
                  >
                    {r.sport ?? 'Ride'}{r.tss ? ` ${Math.round(r.tss)}` : ''}
                  </div>
                ))}

                {/* Planned workouts */}
                {dayWorkouts.map((w, i) => (
                  <div
                    key={w.id ?? i}
                    className="text-[10px] md:text-xs text-yellow truncate"
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
          <h3 className="text-text font-semibold mb-3">
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

          {/* Ride previews */}
          {selectedRides.map((r) => (
            <div key={r.id} className="mb-3">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-text-muted text-xs uppercase tracking-wide">
                  {r.title || r.sport || 'Ride'}
                </h4>
                <button
                  onClick={() => onRideSelect(r.id)}
                  className="text-xs text-accent hover:underline"
                >
                  View Details &rarr;
                </button>
              </div>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                {r.duration_s != null && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">Duration</div>
                    <div className="text-sm font-medium text-text">{fmtDuration(r.duration_s)}</div>
                  </div>
                )}
                {r.distance_m != null && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">Distance</div>
                    <div className="text-sm font-medium text-text">{fmtDistance(r.distance_m, units)}</div>
                  </div>
                )}
                {r.tss != null && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">TSS</div>
                    <div className="text-sm font-medium text-text">{Math.round(r.tss)}</div>
                  </div>
                )}
                {r.avg_power != null && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">Avg Power</div>
                    <div className="text-sm font-medium text-text">{r.avg_power}w</div>
                  </div>
                )}
                {r.normalized_power != null && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">NP</div>
                    <div className="text-sm font-medium text-text">{r.normalized_power}w</div>
                  </div>
                )}
                {r.avg_hr != null && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">Avg HR</div>
                    <div className="text-sm font-medium text-text">{r.avg_hr} bpm</div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Workout previews */}
          {selectedWorkouts.map((w, i) => (
            <div key={w.id ?? i} className={selectedRides.length > 0 ? 'mt-3 pt-3 border-t border-border' : ''}>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-text-muted text-xs uppercase tracking-wide">
                  Planned: {w.name ?? 'Workout'}
                </h4>
                <div className="flex items-center gap-2">
                  {w.id && (
                    <button
                      onClick={() => onWorkoutSelect(w.id, selectedDay!)}
                      className="text-xs text-accent hover:underline"
                    >
                      View Details &rarr;
                    </button>
                  )}
                  {w.id && (
                    <button
                      onClick={() => { if (confirm(`Delete "${w.name ?? 'Workout'}"?`)) deleteWorkout.mutate(w.id) }}
                      className="text-xs text-red hover:underline"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {w.total_duration_s != null && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">Duration</div>
                    <div className="text-sm font-medium text-text">{fmtDuration(w.total_duration_s)}</div>
                  </div>
                )}
                {w.planned_tss != null && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">TSS (est)</div>
                    <div className="text-sm font-medium text-text">{Math.round(Number(w.planned_tss))}</div>
                  </div>
                )}
                {w.sport && (
                  <div className="text-center">
                    <div className="text-[10px] text-text-muted">Sport</div>
                    <div className="text-sm font-medium text-text capitalize">{w.sport}</div>
                  </div>
                )}
              </div>
              {w.coach_notes && (
                <div className="mt-2 text-xs text-text-muted bg-surface2 rounded p-2 whitespace-pre-wrap">
                  {w.coach_notes}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
