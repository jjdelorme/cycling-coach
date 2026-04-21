import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { useMeal } from '../hooks/useApi'
import MacroCard from '../components/MacroCard'

interface Props {
  onOpenNutritionist?: (context?: string, sessionId?: string) => void
}

/**
 * Deep-linkable single-meal page at `/nutrition/meals/:id`.
 *
 * Renders the existing MacroCard so all edit/delete/analyze actions
 * remain available. The MacroCard starts collapsed; users tap to
 * expand for the full editor.
 */
export default function MealDetail({ onOpenNutritionist }: Props) {
  const { id } = useParams<{ id: string }>()
  const mealId = id ? Number(id) : null
  const { data: meal, isLoading, error } = useMeal(mealId)

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Link
          to="/nutrition"
          className="flex items-center gap-1 text-[10px] font-bold text-accent uppercase tracking-widest hover:opacity-70 transition-opacity"
        >
          <ArrowLeft size={12} />
          Back to Nutrition
        </Link>
        <h1 className="text-sm font-bold text-text uppercase tracking-wider">Meal</h1>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-accent opacity-50" />
        </div>
      )}

      {error && (
        <div className="bg-surface rounded-xl border border-red/30 p-6 text-center">
          <p className="text-sm text-red font-bold mb-1">Could not load meal</p>
          <p className="text-xs text-text-muted">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      )}

      {!isLoading && !error && !meal && (
        <div className="bg-surface rounded-xl border border-border p-6 text-center">
          <p className="text-sm text-text-muted">Meal not found.</p>
        </div>
      )}

      {meal && <MacroCard meal={meal} onAskNutritionist={onOpenNutritionist} />}
    </div>
  )
}
