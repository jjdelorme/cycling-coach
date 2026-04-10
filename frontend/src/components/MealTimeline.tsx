import { useRef } from 'react'
import { ChevronLeft, ChevronRight, UtensilsCrossed } from 'lucide-react'
import MacroCard from './MacroCard'
import type { MealSummary } from '../types/api'

interface Props {
  meals: MealSummary[]
  date: string
  onDateChange: (date: string) => void
  onAskNutritionist?: (context: string) => void
}

export default function MealTimeline({ meals, date, onDateChange, onAskNutritionist }: Props) {
  const d = new Date(date + 'T12:00:00') // noon to avoid timezone shift
  const today = new Date().toISOString().slice(0, 10)
  const isToday = date === today
  const timelineTouchRef = useRef<{ x: number } | null>(null)

  const formatDate = () => {
    if (isToday) return 'Today'
    const yesterday = new Date()
    yesterday.setDate(yesterday.getDate() - 1)
    if (date === yesterday.toISOString().slice(0, 10)) return 'Yesterday'
    return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  }

  const shiftDate = (delta: number) => {
    const next = new Date(d)
    next.setDate(next.getDate() + delta)
    onDateChange(next.toISOString().slice(0, 10))
  }

  const handleTimelineTouchStart = (e: React.TouchEvent) => {
    timelineTouchRef.current = { x: e.touches[0].clientX }
  }

  const handleTimelineTouchEnd = (e: React.TouchEvent) => {
    if (!timelineTouchRef.current) return
    const dx = e.changedTouches[0].clientX - timelineTouchRef.current.x
    if (Math.abs(dx) > 60) {
      // Swipe right = previous day, swipe left = next day
      shiftDate(dx > 0 ? -1 : 1)
    }
    timelineTouchRef.current = null
  }

  return (
    <div
      onTouchStart={handleTimelineTouchStart}
      onTouchEnd={handleTimelineTouchEnd}
    >
      {/* Date nav */}
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => shiftDate(-1)} className="p-2 text-text-muted hover:text-text rounded-md transition-colors">
          <ChevronLeft size={20} />
        </button>
        <div className="text-center">
          <span className="text-sm font-bold text-text uppercase tracking-wider">{formatDate()}</span>
          {!isToday && (
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">
              {d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          )}
        </div>
        <button
          onClick={() => shiftDate(1)}
          disabled={isToday}
          className="p-2 text-text-muted hover:text-text rounded-md transition-colors disabled:opacity-30"
        >
          <ChevronRight size={20} />
        </button>
      </div>

      {/* Meal list */}
      {meals.length > 0 ? (
        <div className="space-y-3">
          {meals.map(meal => (
            <MacroCard key={meal.id} meal={meal} onAskNutritionist={onAskNutritionist} />
          ))}
        </div>
      ) : (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <UtensilsCrossed size={64} className="text-text-muted mx-auto opacity-10 mb-4" />
          <p className="text-text-muted font-bold uppercase tracking-widest text-xs mb-1">
            No meals logged {isToday ? 'today' : 'this day'}
          </p>
          <p className="text-text-muted text-xs">Snap a photo to get started</p>
        </div>
      )}
    </div>
  )
}
