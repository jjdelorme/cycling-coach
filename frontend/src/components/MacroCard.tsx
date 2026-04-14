import { useState, useRef, useEffect } from 'react'
import { Trash2, ChevronDown, ChevronUp, Loader2, Sparkles } from 'lucide-react'
import { useUpdateMeal, useDeleteMeal, useAnalyzeMeal } from '../hooks/useApi'
import type { MealSummary } from '../types/api'

const MEAL_TYPES = ['Breakfast', 'Lunch', 'Dinner', 'Snack', 'Other']

interface Props {
  meal: MealSummary
  onAskNutritionist?: (mealContext: string) => void
}

export default function MacroCard({ meal, onAskNutritionist }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [editValues, setEditValues] = useState({
    total_calories: meal.total_calories,
    total_protein_g: meal.total_protein_g,
    total_carbs_g: meal.total_carbs_g,
    total_fat_g: meal.total_fat_g,
    meal_type: meal.meal_type ?? '',
    date: meal.date,
    user_notes: meal.user_notes ?? '',
  })
  const [swipeX, setSwipeX] = useState(0)
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  const SWIPE_THRESHOLD = 80

  const updateMeal = useUpdateMeal()
  const deleteMeal = useDeleteMeal()
  const analyzeMeal = useAnalyzeMeal()

  // Sync when meal prop is updated externally (e.g. by the nutritionist agent)
  useEffect(() => {
    setEditValues({
      total_calories: meal.total_calories,
      total_protein_g: meal.total_protein_g,
      total_carbs_g: meal.total_carbs_g,
      total_fat_g: meal.total_fat_g,
      meal_type: meal.meal_type ?? '',
      date: meal.date,
      user_notes: meal.user_notes ?? '',
    })
  }, [meal.total_calories, meal.total_protein_g, meal.total_carbs_g, meal.total_fat_g, meal.meal_type, meal.date, meal.user_notes])

  const hasChanges =
    editValues.total_calories !== meal.total_calories ||
    editValues.total_protein_g !== meal.total_protein_g ||
    editValues.total_carbs_g !== meal.total_carbs_g ||
    editValues.total_fat_g !== meal.total_fat_g ||
    editValues.meal_type !== (meal.meal_type ?? '') ||
    editValues.date !== meal.date ||
    editValues.user_notes !== (meal.user_notes ?? '')

  const handleSave = () => {
    updateMeal.mutate({ id: meal.id, body: editValues })
  }

  const handleDelete = () => {
    if (window.confirm('Delete this meal? This cannot be undone.')) {
      deleteMeal.mutate(meal.id)
    }
  }

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStartRef.current) return
    const dx = e.touches[0].clientX - touchStartRef.current.x
    const dy = e.touches[0].clientY - touchStartRef.current.y
    if (Math.abs(dy) > Math.abs(dx)) return
    if (dx < 0) setSwipeX(Math.max(dx, -SWIPE_THRESHOLD - 20))
  }

  const handleTouchEnd = () => {
    setSwipeX(swipeX < -SWIPE_THRESHOLD ? -SWIPE_THRESHOLD : 0)
    touchStartRef.current = null
  }

  const time = new Date(meal.logged_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const mealTypeLabel = meal.meal_type
    ? MEAL_TYPES.find(t => t.toLowerCase() === meal.meal_type!.toLowerCase()) ?? meal.meal_type
    : null

  return (
    <div className="relative overflow-hidden rounded-xl">
      {/* Delete action behind the card */}
      <div className="absolute inset-y-0 right-0 w-20 bg-red flex items-center justify-center">
        <button onClick={handleDelete} className="p-2 text-white">
          <Trash2 size={20} />
        </button>
      </div>

      {/* Swipeable card */}
      <div
        className={`relative bg-surface border shadow-sm transition-transform ${
          expanded ? 'border-accent/30' : 'border-border hover:border-accent/30'
        }`}
        style={{ transform: `translateX(${swipeX}px)` }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Compact display — always visible */}
        <button
          onClick={() => setExpanded(e => !e)}
          className="w-full text-left p-4 flex gap-3"
        >
          {/* Photo thumbnail */}
          {meal.photo_url && (
            <div className="w-16 h-16 rounded-lg overflow-hidden shrink-0 bg-surface-low">
              <img src={meal.photo_url} alt="" className="w-full h-full object-cover" />
            </div>
          )}

          <div className="flex-1 min-w-0">
            {/* Time · Meal type · badges */}
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{time}</span>
              {mealTypeLabel && (
                <>
                  <span className="text-[10px] text-text-muted">·</span>
                  <span className="text-[10px] font-bold text-accent uppercase tracking-widest">{mealTypeLabel}</span>
                </>
              )}
              {meal.confidence === 'low' && (
                <span className="text-[10px] font-bold text-yellow uppercase tracking-widest">~</span>
              )}
              {meal.edited_by_user && (
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">edited</span>
              )}
            </div>

            {/* Description */}
            <p className="text-sm text-text truncate">{meal.description}</p>

            {/* Headline kcal — full breakdown in expanded mini cards */}
            <div className="mt-1.5">
              <span className="text-sm font-bold text-accent">
                {meal.total_calories} <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">kcal</span>
              </span>
            </div>
          </div>

          <div className="shrink-0 self-center text-text-muted">
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
        </button>

        {/* Expanded edit mode */}
        {expanded && (
          <div className="border-t border-border px-4 pb-4 pt-3">
            {/* Full photo */}
            {meal.photo_url && (
              <div className="w-full rounded-lg overflow-hidden mb-3 bg-surface-low">
                <img src={meal.photo_url} alt={meal.description} className="w-full h-auto object-contain" />
              </div>
            )}

            {/* Description (read-only) */}
            <p className="text-sm text-text-muted mb-3">{meal.description}</p>

            {/* Agent notes */}
            {meal.agent_notes && (
              <p className="text-[10px] text-text-muted italic border-l-2 border-green/30 pl-2 mb-3">
                {meal.agent_notes}
              </p>
            )}

            {/* User notes */}
            <textarea
              value={editValues.user_notes}
              onChange={e => setEditValues(prev => ({ ...prev, user_notes: e.target.value }))}
              placeholder="Add notes..."
              rows={2}
              className="w-full bg-surface-low border border-border rounded-lg px-3 py-2 text-sm text-text placeholder:text-text-muted/40 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 resize-none mb-3"
            />

            {/* Date + meal type row */}
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div>
                <input
                  type="date"
                  value={editValues.date}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={e => setEditValues(prev => ({ ...prev, date: e.target.value }))}
                  className="w-full bg-surface-low border border-border rounded-lg px-2 py-2 text-center text-sm font-bold text-text focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20"
                />
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest mt-1 block text-center">Date</span>
              </div>
              <div>
                <select
                  value={editValues.meal_type}
                  onChange={e => setEditValues(prev => ({ ...prev, meal_type: e.target.value }))}
                  className="w-full bg-surface-low border border-border rounded-lg px-2 py-2 text-center text-sm font-bold text-text focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20"
                >
                  <option value="">— type —</option>
                  {MEAL_TYPES.map(t => (
                    <option key={t} value={t.toLowerCase()}>{t}</option>
                  ))}
                </select>
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest mt-1 block text-center">Meal Type</span>
              </div>
            </div>

            {/* Macro inputs */}
            <div className="grid grid-cols-4 gap-2 mb-3">
              <MacroInput label="KCAL" value={editValues.total_calories} color="text-accent"
                onChange={v => setEditValues(prev => ({ ...prev, total_calories: v }))} />
              <MacroInput label="PROT g" value={editValues.total_protein_g} color="text-green" step={0.1}
                onChange={v => setEditValues(prev => ({ ...prev, total_protein_g: v }))} />
              <MacroInput label="CARBS g" value={editValues.total_carbs_g} color="text-yellow" step={0.1}
                onChange={v => setEditValues(prev => ({ ...prev, total_carbs_g: v }))} />
              <MacroInput label="FAT g" value={editValues.total_fat_g} color="text-blue" step={0.1}
                onChange={v => setEditValues(prev => ({ ...prev, total_fat_g: v }))} />
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between">
              <button
                onClick={handleDelete}
                className="p-2 text-text-muted hover:text-red hover:bg-red/5 rounded-md transition-all"
                title="Delete meal"
              >
                <Trash2 size={16} />
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => analyzeMeal.mutate(meal.id)}
                  disabled={analyzeMeal.isPending}
                  className="flex items-center gap-1 text-text-muted hover:text-green text-[10px] font-bold uppercase tracking-widest transition-colors disabled:opacity-50"
                >
                  {analyzeMeal.isPending ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                  {meal.agent_notes ? 'Re-analyze' : 'Analyze'}
                </button>
                {onAskNutritionist && (
                  <button
                    onClick={() => {
                      let context = `Tell me about this meal: ${meal.description} (${meal.total_calories} kcal, P${Math.round(meal.total_protein_g)}g / C${Math.round(meal.total_carbs_g)}g / F${Math.round(meal.total_fat_g)}g)`
                      if (meal.agent_notes) context += `\n\nPrior analysis: ${meal.agent_notes}`
                      onAskNutritionist(context)
                    }}
                    className="text-text-muted hover:text-accent text-[10px] font-bold uppercase tracking-widest transition-colors"
                  >
                    Ask Nutritionist
                  </button>
                )}

                {hasChanges && (
                  <button
                    onClick={handleSave}
                    disabled={updateMeal.isPending}
                    className="bg-accent text-white rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest hover:opacity-90 shadow-lg shadow-accent/20 disabled:opacity-50"
                  >
                    {updateMeal.isPending ? 'Saving...' : 'Save Changes'}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function MacroInput({ label, value, color, step = 1, onChange }: {
  label: string; value: number; color: string; step?: number
  onChange: (v: number) => void
}) {
  return (
    <div className="text-center">
      <input
        type="number"
        value={value}
        step={step}
        onChange={e => onChange(Number(e.target.value))}
        className={`w-full bg-surface-low border border-border rounded-lg px-2 py-2 text-center text-sm font-bold ${color} focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20`}
      />
      <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest mt-1 block">{label}</span>
    </div>
  )
}
