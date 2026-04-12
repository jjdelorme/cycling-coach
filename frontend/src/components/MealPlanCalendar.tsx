import { useState, useRef } from 'react'
import { ChevronLeft, ChevronRight, CalendarDays } from 'lucide-react'
import { useMealPlan } from '../hooks/useApi'
import MealPlanDayDetail from './MealPlanDayDetail'
import type { MealPlanDay } from '../types/api'

const MEAL_SLOTS = [
  { key: 'breakfast', label: 'Breakfast' },
  { key: 'snack_am', label: 'AM Snack' },
  { key: 'lunch', label: 'Lunch' },
  { key: 'snack_pm', label: 'PM Snack' },
  { key: 'pre_workout', label: 'Pre-Ride' },
  { key: 'post_workout', label: 'Post-Ride' },
  { key: 'dinner', label: 'Dinner' },
]

function getMonday(dateStr: string): string {
  const d = new Date(dateStr + 'T12:00:00')
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  d.setDate(d.getDate() + diff)
  return d.toISOString().slice(0, 10)
}

interface Props {
  onOpenNutritionist?: (context?: string) => void
}

export default function MealPlanCalendar({ onOpenNutritionist }: Props) {
  const [weekStart, setWeekStart] = useState(() => getMonday(new Date().toISOString().slice(0, 10)))
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const touchRef = useRef<{ x: number } | null>(null)

  const { data, isLoading } = useMealPlan({ date: weekStart, days: 7 })

  // Derive selected day from live query data so it updates automatically
  const selectedDay = selectedDate && data
    ? data.days.find(d => d.date === selectedDate) ?? null
    : null

  const shiftWeek = (delta: number) => {
    const d = new Date(weekStart + 'T12:00:00')
    d.setDate(d.getDate() + delta * 7)
    setWeekStart(d.toISOString().slice(0, 10))
    setSelectedDate(null)
  }

  const goToThisWeek = () => {
    setWeekStart(getMonday(new Date().toISOString().slice(0, 10)))
    setSelectedDate(null)
  }

  const today = new Date().toISOString().slice(0, 10)
  const thisWeekMonday = getMonday(today)
  const isCurrentWeek = weekStart === thisWeekMonday

  const handleTouchStart = (e: React.TouchEvent) => {
    touchRef.current = { x: e.touches[0].clientX }
  }
  const handleTouchEnd = (e: React.TouchEvent) => {
    if (!touchRef.current) return
    const dx = e.changedTouches[0].clientX - touchRef.current.x
    if (Math.abs(dx) > 80) shiftWeek(dx > 0 ? -1 : 1)
    touchRef.current = null
  }

  // If a day is selected, show the detail view
  if (selectedDay && data) {
    const dayIndex = data.days.findIndex(d => d.date === selectedDay.date)
    const prevDay = dayIndex > 0 ? data.days[dayIndex - 1] : undefined
    const nextDay = dayIndex < data.days.length - 1 ? data.days[dayIndex + 1] : undefined

    return (
      <MealPlanDayDetail
        day={selectedDay}
        onBack={() => setSelectedDate(null)}
        onPrev={prevDay ? () => setSelectedDate(prevDay.date) : undefined}
        onNext={nextDay ? () => setSelectedDate(nextDay.date) : undefined}
        onOpenNutritionist={onOpenNutritionist}
      />
    )
  }

  const weekLabel = data
    ? (() => {
        const s = new Date(data.start_date + 'T12:00:00')
        const e = new Date(data.end_date + 'T12:00:00')
        const sameMonth = s.getMonth() === e.getMonth()
        if (sameMonth) {
          return `${s.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} - ${e.getDate()}`
        }
        return `${s.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} - ${e.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
      })()
    : ''

  return (
    <div onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
      {/* Week nav */}
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => shiftWeek(-1)} className="p-2 text-text-muted hover:text-text rounded-md transition-colors">
          <ChevronLeft size={20} />
        </button>
        <div className="text-center">
          <button
            onClick={goToThisWeek}
            className="text-sm font-bold text-text uppercase tracking-wider hover:text-accent transition-colors"
          >
            {isCurrentWeek ? 'This Week' : weekLabel}
          </button>
          {!isCurrentWeek && (
            <p className="text-[10px] font-bold text-accent cursor-pointer hover:underline mt-0.5" onClick={goToThisWeek}>
              Jump to this week
            </p>
          )}
        </div>
        <button onClick={() => shiftWeek(1)} className="p-2 text-text-muted hover:text-text rounded-md transition-colors">
          <ChevronRight size={20} />
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !data || data.days.length === 0 ? (
        <EmptyState onOpenNutritionist={onOpenNutritionist} />
      ) : (
        <>
          {/* Desktop: grid layout */}
          <div className="hidden md:block overflow-x-auto">
            <div className="grid grid-cols-7 gap-1 min-w-[700px]">
              {/* Column headers */}
              {data.days.map((day) => {
                const d = new Date(day.date + 'T12:00:00')
                const isToday = day.date === today
                return (
                  <button
                    key={day.date}
                    onClick={() => setSelectedDate(day.date)}
                    className={`text-center py-2 rounded-t-lg transition-colors ${
                      isToday ? 'bg-accent/10 text-accent' : 'text-text-muted hover:text-text hover:bg-surface'
                    }`}
                  >
                    <div className="text-[10px] font-bold uppercase tracking-widest">
                      {d.toLocaleDateString(undefined, { weekday: 'short' })}
                    </div>
                    <div className={`text-sm font-bold ${isToday ? 'text-accent' : 'text-text'}`}>
                      {d.getDate()}
                    </div>
                  </button>
                )
              })}

              {/* Meal slot rows */}
              {MEAL_SLOTS.map((slot) => (
                data.days.map((day) => {
                  const planned = day.planned[slot.key]
                  const isToday = day.date === today

                  return (
                    <button
                      key={`${day.date}-${slot.key}`}
                      onClick={() => setSelectedDate(day.date)}
                      className={`min-h-[48px] p-1.5 rounded transition-colors text-left ${
                        isToday ? 'bg-accent/5' : 'bg-surface/50'
                      } hover:bg-surface border border-transparent hover:border-border`}
                    >
                      {planned ? (
                        <div>
                          <p className="text-[10px] font-bold text-yellow truncate leading-tight">
                            {planned.name}
                          </p>
                          <p className="text-[9px] text-text-muted mt-0.5">
                            {planned.total_calories} kcal
                          </p>
                        </div>
                      ) : (
                        <div className="h-full" />
                      )}
                    </button>
                  )
                })
              ))}
            </div>

            {/* Slot labels on hover - left gutter */}
            <div className="mt-2 flex gap-2 flex-wrap">
              {MEAL_SLOTS.map((slot) => (
                <span key={slot.key} className="text-[9px] font-bold text-text-muted uppercase tracking-widest">
                  {slot.label}
                </span>
              ))}
            </div>
          </div>

          {/* Mobile: card list */}
          <div className="md:hidden space-y-2">
            {data.days.map((day) => {
              const d = new Date(day.date + 'T12:00:00')
              const isToday = day.date === today
              const plannedCount = Object.values(day.planned).filter(Boolean).length
              const actualCount = day.actual.length

              return (
                <button
                  key={day.date}
                  onClick={() => setSelectedDate(day.date)}
                  className={`w-full text-left bg-surface rounded-xl border p-4 transition-colors ${
                    isToday ? 'border-accent/30' : 'border-border'
                  } hover:border-accent/50`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-bold ${isToday ? 'text-accent' : 'text-text'}`}>
                        {isToday ? 'Today' : d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                      </span>
                      {isToday && (
                        <span className="text-[9px] font-bold bg-accent/10 text-accent px-2 py-0.5 rounded-full uppercase tracking-widest">Today</span>
                      )}
                    </div>
                    <div className="flex gap-3 text-[10px] font-bold uppercase tracking-widest">
                      {plannedCount > 0 && (
                        <span className="text-yellow">{plannedCount} planned</span>
                      )}
                      {actualCount > 0 && (
                        <span className="text-green">{actualCount} logged</span>
                      )}
                    </div>
                  </div>

                  {plannedCount > 0 && (
                    <div className="flex gap-4 text-xs">
                      <span className="text-text font-bold">{day.day_totals.planned_calories} kcal</span>
                      <span className="text-green">P {Math.round(day.day_totals.planned_protein_g)}g</span>
                      <span className="text-yellow">C {Math.round(day.day_totals.planned_carbs_g)}g</span>
                      <span className="text-blue">F {Math.round(day.day_totals.planned_fat_g)}g</span>
                    </div>
                  )}

                  {plannedCount === 0 && actualCount === 0 && (
                    <p className="text-xs text-text-muted">No meals planned or logged</p>
                  )}
                </button>
              )
            })}
          </div>

          {/* Week totals bar */}
          {data.days.some(d => Object.values(d.planned).some(Boolean) || d.actual.length > 0) && (
            <div className="mt-4 bg-surface rounded-xl border border-border p-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Week Totals (Planned)</span>
                <div className="flex gap-4 text-xs font-bold">
                  <span className="text-text">
                    {Math.round(data.days.reduce((sum, d) => sum + d.day_totals.planned_calories, 0) / Math.max(1, data.days.filter(d => d.day_totals.planned_calories > 0).length))} avg kcal/day
                  </span>
                  <span className="text-green">
                    P {Math.round(data.days.reduce((sum, d) => sum + d.day_totals.planned_protein_g, 0) / Math.max(1, data.days.filter(d => d.day_totals.planned_protein_g > 0).length))}g
                  </span>
                  <span className="text-yellow">
                    C {Math.round(data.days.reduce((sum, d) => sum + d.day_totals.planned_carbs_g, 0) / Math.max(1, data.days.filter(d => d.day_totals.planned_carbs_g > 0).length))}g
                  </span>
                  <span className="text-blue">
                    F {Math.round(data.days.reduce((sum, d) => sum + d.day_totals.planned_fat_g, 0) / Math.max(1, data.days.filter(d => d.day_totals.planned_fat_g > 0).length))}g
                  </span>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function EmptyState({ onOpenNutritionist }: { onOpenNutritionist?: (context?: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <CalendarDays size={64} className="text-text-muted mx-auto opacity-10 mb-4" />
      <p className="text-text-muted font-bold uppercase tracking-widest text-xs mb-1">
        No meal plan this week
      </p>
      <p className="text-text-muted text-xs mb-4">
        Ask the nutritionist to create a meal plan based on your training schedule
      </p>
      {onOpenNutritionist && (
        <button
          onClick={() => onOpenNutritionist('Create a meal plan for this week based on my training schedule and dietary preferences.')}
          className="px-5 py-2.5 bg-accent text-white rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 transition-all shadow-lg shadow-accent/20"
        >
          Plan My Meals
        </button>
      )}
    </div>
  )
}
