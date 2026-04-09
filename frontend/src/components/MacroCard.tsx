import { useState, useRef, useEffect } from 'react'
import { Trash2, ChevronDown, ChevronUp } from 'lucide-react'
import { useUpdateMeal, useDeleteMeal } from '../hooks/useApi'
import type { MealSummary } from '../types/api'

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
  })
  const [swipeX, setSwipeX] = useState(0)
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  const SWIPE_THRESHOLD = 80

  const updateMeal = useUpdateMeal()
  const deleteMeal = useDeleteMeal()

  // Sync editValues when the meal prop is updated externally (e.g. by the nutritionist agent)
  useEffect(() => {
    setEditValues({
      total_calories: meal.total_calories,
      total_protein_g: meal.total_protein_g,
      total_carbs_g: meal.total_carbs_g,
      total_fat_g: meal.total_fat_g,
    })
  }, [meal.total_calories, meal.total_protein_g, meal.total_carbs_g, meal.total_fat_g])

  const hasChanges =
    editValues.total_calories !== meal.total_calories ||
    editValues.total_protein_g !== meal.total_protein_g ||
    editValues.total_carbs_g !== meal.total_carbs_g ||
    editValues.total_fat_g !== meal.total_fat_g

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
    // Only track horizontal swipes (ignore vertical scroll)
    if (Math.abs(dy) > Math.abs(dx)) return
    if (dx < 0) {
      setSwipeX(Math.max(dx, -SWIPE_THRESHOLD - 20))
    }
  }

  const handleTouchEnd = () => {
    if (swipeX < -SWIPE_THRESHOLD) {
      // Snap to reveal delete
      setSwipeX(-SWIPE_THRESHOLD)
    } else {
      setSwipeX(0)
    }
    touchStartRef.current = null
  }

  const time = new Date(meal.logged_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

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
          {/* Timestamp + confidence */}
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{time}</span>
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
            <span className="text-sm font-bold text-accent">{meal.total_calories} <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">kcal</span></span>
          </div>
        </div>

        <div className="shrink-0 self-center text-text-muted">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </button>

      {/* Expanded edit mode */}
      {expanded && (
        <div className="border-t border-border px-4 pb-4 pt-3">
          {/* Larger photo */}
          {meal.photo_url && (
            <div className="w-full rounded-lg overflow-hidden mb-3 bg-surface-low">
              <img src={meal.photo_url} alt={meal.description} className="w-full h-auto object-contain" />
            </div>
          )}

          {/* Description (read-only) */}
          <p className="text-sm text-text-muted mb-3">{meal.description}</p>

          {/* Editable macro inputs */}
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
              {onAskNutritionist && (
                <button
                  onClick={() => onAskNutritionist(
                    `Tell me about this meal: ${meal.description} (${meal.total_calories} kcal, P${Math.round(meal.total_protein_g)}g / C${Math.round(meal.total_carbs_g)}g / F${Math.round(meal.total_fat_g)}g)`
                  )}
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
