import { ChevronLeft, ChevronRight, UtensilsCrossed, MessageSquare } from 'lucide-react'
import MacroCard from './MacroCard'
import type { MealPlanDay, PlannedMeal } from '../types/api'

const MEAL_SLOTS = [
  { key: 'breakfast', label: 'Breakfast' },
  { key: 'snack_am', label: 'AM Snack' },
  { key: 'lunch', label: 'Lunch' },
  { key: 'snack_pm', label: 'PM Snack' },
  { key: 'pre_workout', label: 'Pre-Ride' },
  { key: 'post_workout', label: 'Post-Ride' },
  { key: 'dinner', label: 'Dinner' },
]

interface Props {
  day: MealPlanDay
  onBack: () => void
  onPrev?: () => void
  onNext?: () => void
  onOpenNutritionist?: (context?: string) => void
}

export default function MealPlanDayDetail({ day, onBack, onPrev, onNext, onOpenNutritionist }: Props) {
  const d = new Date(day.date + 'T12:00:00')
  const today = new Date().toISOString().slice(0, 10)
  const isToday = day.date === today

  const plannedSlots = MEAL_SLOTS.filter(s => day.planned[s.key])
  const hasPlanned = plannedSlots.length > 0
  const hasActual = day.actual.length > 0
  const { day_totals: totals } = day

  return (
    <div className="space-y-4">
      {/* Header with nav */}
      <div className="flex items-center justify-between">
        <button
          onClick={onPrev}
          disabled={!onPrev}
          className="p-2 text-text-muted hover:text-text rounded-md transition-colors disabled:opacity-20"
        >
          <ChevronLeft size={20} />
        </button>

        <div className="text-center flex-1">
          <h2 className="text-sm font-bold text-text uppercase tracking-wider">
            {isToday ? 'Today' : d.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
          </h2>
          {isToday && (
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">
              {d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          )}
          <button
            onClick={onBack}
            className="text-[10px] font-bold text-accent uppercase tracking-widest mt-1 hover:opacity-70 transition-opacity"
          >
            Back to Calendar
          </button>
        </div>

        <button
          onClick={onNext}
          disabled={!onNext}
          className="p-2 text-text-muted hover:text-text rounded-md transition-colors disabled:opacity-20"
        >
          <ChevronRight size={20} />
        </button>
      </div>

      {/* Planned vs Actual summary bar */}
      {(hasPlanned || hasActual) && (
        <div className="bg-surface rounded-xl border border-border p-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-[10px] font-bold text-yellow uppercase tracking-widest">Planned</span>
              <div className="mt-1 text-xs space-y-0.5">
                <p className="text-text font-bold">{totals.planned_calories} kcal</p>
                <p className="text-text-muted">
                  P {Math.round(totals.planned_protein_g)}g / C {Math.round(totals.planned_carbs_g)}g / F {Math.round(totals.planned_fat_g)}g
                </p>
              </div>
            </div>
            <div>
              <span className="text-[10px] font-bold text-green uppercase tracking-widest">Logged</span>
              <div className="mt-1 text-xs space-y-0.5">
                <p className="text-text font-bold">{totals.actual_calories} kcal</p>
                <p className="text-text-muted">
                  P {Math.round(totals.actual_protein_g)}g / C {Math.round(totals.actual_carbs_g)}g / F {Math.round(totals.actual_fat_g)}g
                </p>
              </div>
            </div>
          </div>

          {/* Adherence bar */}
          {hasPlanned && totals.planned_calories > 0 && (
            <div className="mt-3 pt-3 border-t border-border/50">
              <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest mb-1">
                <span className="text-text-muted">Calorie Adherence</span>
                <span className={
                  totals.actual_calories === 0 ? 'text-text-muted' :
                  Math.abs(totals.actual_calories - totals.planned_calories) / totals.planned_calories < 0.1 ? 'text-green' :
                  totals.actual_calories < totals.planned_calories ? 'text-yellow' : 'text-red'
                }>
                  {totals.actual_calories === 0 ? 'No meals logged yet' :
                   `${Math.round(totals.actual_calories / totals.planned_calories * 100)}%`}
                </span>
              </div>
              {totals.actual_calories > 0 && (
                <div className="w-full bg-surface-low rounded-full h-1.5">
                  <div
                    className={`h-full rounded-full transition-all ${
                      Math.abs(totals.actual_calories - totals.planned_calories) / totals.planned_calories < 0.1 ? 'bg-green' :
                      totals.actual_calories < totals.planned_calories ? 'bg-yellow' : 'bg-red'
                    }`}
                    style={{ width: `${Math.min(100, (totals.actual_calories / totals.planned_calories) * 100)}%` }}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Planned meals by slot */}
      {hasPlanned && (
        <div className="space-y-2">
          <h3 className="text-[10px] font-bold text-yellow uppercase tracking-widest px-1">Planned Meals</h3>
          {MEAL_SLOTS.map((slot) => {
            const meal = day.planned[slot.key] as PlannedMeal | null | undefined
            if (!meal) return null

            return (
              <div
                key={slot.key}
                className="bg-surface rounded-xl border border-yellow/20 p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[9px] font-bold text-yellow bg-yellow/10 px-2 py-0.5 rounded-full uppercase tracking-widest">
                        {slot.label}
                      </span>
                    </div>
                    <p className="text-sm font-bold text-text truncate">{meal.name}</p>
                    {meal.description && (
                      <p className="text-xs text-text-muted mt-1 line-clamp-2">{meal.description}</p>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-bold text-text">{meal.total_calories}</p>
                    <p className="text-[10px] text-text-muted">kcal</p>
                  </div>
                </div>

                {/* Macro bar */}
                <div className="flex gap-3 mt-2 text-[10px] font-bold">
                  <span className="text-green">P {Math.round(meal.total_protein_g)}g</span>
                  <span className="text-yellow">C {Math.round(meal.total_carbs_g)}g</span>
                  <span className="text-blue">F {Math.round(meal.total_fat_g)}g</span>
                </div>

                {/* Items */}
                {meal.items && meal.items.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-border/30 space-y-1">
                    {meal.items.map((item, i) => (
                      <div key={i} className="flex items-center justify-between text-[10px]">
                        <span className="text-text-muted">
                          {item.name}{item.serving_size ? ` (${item.serving_size})` : ''}
                        </span>
                        <span className="text-text-muted">{item.calories} kcal</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Agent notes */}
                {meal.agent_notes && (
                  <p className="mt-2 text-[10px] text-text-muted italic border-l-2 border-yellow/30 pl-2">
                    {meal.agent_notes}
                  </p>
                )}

                {/* Ask a Question */}
                {onOpenNutritionist && (
                  <button
                    onClick={() => {
                      const items = meal.items?.map(i => `${i.name}${i.serving_size ? ` (${i.serving_size})` : ''}`).join(', ')
                      let context = `I have a question about this planned meal: ${meal.name} (${slot.label}).\n`
                      if (meal.description) context += `${meal.description}\n`
                      context += `Macros: ${meal.total_calories} kcal, P${Math.round(meal.total_protein_g)}g / C${Math.round(meal.total_carbs_g)}g / F${Math.round(meal.total_fat_g)}g`
                      if (items) context += `\nItems: ${items}`
                      if (meal.agent_notes) context += `\nNutritionist notes: ${meal.agent_notes}`
                      onOpenNutritionist(context)
                    }}
                    className="mt-2 flex items-center gap-1 text-text-muted hover:text-accent text-[10px] font-bold uppercase tracking-widest transition-colors"
                  >
                    <MessageSquare size={10} />
                    Ask a Question
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Actual logged meals — reuses MacroCard from Day view */}
      {hasActual && (
        <div className="space-y-2">
          <h3 className="text-[10px] font-bold text-green uppercase tracking-widest px-1">Logged Meals</h3>
          <div className="space-y-3">
            {day.actual.map((meal) => (
              <MacroCard key={meal.id} meal={meal} onAskNutritionist={onOpenNutritionist} />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!hasPlanned && !hasActual && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <UtensilsCrossed size={48} className="text-text-muted mx-auto opacity-10 mb-3" />
          <p className="text-text-muted font-bold uppercase tracking-widest text-xs mb-1">
            No meals planned or logged
          </p>
          {onOpenNutritionist && (
            <button
              onClick={() => onOpenNutritionist(`Create a meal plan for ${day.date} based on my training schedule.`)}
              className="mt-3 px-4 py-2 bg-accent text-white rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 transition-all"
            >
              Plan This Day
            </button>
          )}
        </div>
      )}
    </div>
  )
}
