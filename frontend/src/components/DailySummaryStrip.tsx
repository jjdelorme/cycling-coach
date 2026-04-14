import type { DailyNutritionSummary } from '../types/api'

interface Props {
  data: DailyNutritionSummary
}

export default function DailySummaryStrip({ data }: Props) {
  const pct = data.target_calories > 0
    ? Math.min(Math.round((data.total_calories_in / data.target_calories) * 100), 100)
    : 0

  return (
    <div className="bg-surface rounded-xl border border-border p-5 shadow-sm">
      {/* Headline */}
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <span className="text-3xl font-bold text-accent">{data.total_calories_in.toLocaleString()}</span>
          <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest ml-2">kcal</span>
        </div>
        <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">
          {data.remaining_calories > 0 ? `${data.remaining_calories} remaining` : 'Target reached'}
        </span>
      </div>

      {/* Macro breakdown */}
      <div className="flex gap-6 mb-3">
        <MacroStat label="Protein" value={data.total_protein_g} unit="g" color="text-green" />
        <MacroStat label="Carbs" value={data.total_carbs_g} unit="g" color="text-yellow" />
        <MacroStat label="Fat" value={data.total_fat_g} unit="g" color="text-blue" />
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-surface-low rounded-full overflow-hidden">
        <div
          className="h-full bg-accent rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest mt-1.5 text-right">
        {pct}% of daily goal
      </p>
    </div>
  )
}

function MacroStat({ label, value, unit, color }: { label: string; value: number; unit: string; color: string }) {
  return (
    <div>
      <span className={`text-lg font-bold ${color}`}>{Math.round(value)}</span>
      <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest ml-1">{unit}</span>
      <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{label}</p>
    </div>
  )
}
