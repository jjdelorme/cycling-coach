import { Sparkles, X } from 'lucide-react'

interface Props {
  photoUrl: string | null
  isPending: boolean
  error?: string
  onCancel: () => void
}

export default function MacroAnalysisCard({ photoUrl, isPending, error, onCancel }: Props) {
  return (
    <div className="bg-surface rounded-xl border border-border p-5 shadow-sm mb-4">
      <div className="flex gap-4">
        {/* Photo thumbnail */}
        {photoUrl && (
          <div className="w-20 h-20 rounded-lg overflow-hidden shrink-0 bg-surface-low">
            <img src={photoUrl} alt="Meal" className="w-full h-full object-cover" />
          </div>
        )}

        <div className="flex-1 min-w-0">
          {isPending ? (
            <>
              <div className="flex items-center gap-2 mb-3">
                <Sparkles size={16} className="text-accent animate-pulse" />
                <span className="text-sm font-bold text-text uppercase tracking-wider">Analyzing...</span>
              </div>
              {/* Skeleton lines */}
              <div className="space-y-2">
                <div className="animate-pulse bg-surface-low rounded h-4 w-3/4" />
                <div className="animate-pulse bg-surface-low rounded h-4 w-1/2" />
                <div className="animate-pulse bg-surface-low rounded h-4 w-2/3" />
              </div>
            </>
          ) : error ? (
            <div className="text-sm text-red">{error}</div>
          ) : null}
        </div>
      </div>

      {/* Cancel button */}
      <div className="mt-3 flex justify-end">
        <button
          onClick={onCancel}
          className="text-text-muted hover:text-text text-xs font-bold uppercase tracking-widest transition-colors flex items-center gap-1"
        >
          <X size={12} />
          Cancel
        </button>
      </div>
    </div>
  )
}
