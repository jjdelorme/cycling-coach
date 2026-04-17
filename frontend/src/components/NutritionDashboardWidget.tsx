import { useMemo } from 'react'
import { Line } from 'react-chartjs-2'
import { useDailyNutrition, useWeeklyNutrition } from '../hooks/useApi'
import { Apple, ChevronRight } from 'lucide-react'
import { localDateStr } from '../lib/format'

interface Props {
  onNavigateToNutrition?: () => void
}

export default function NutritionDashboardWidget({ onNavigateToNutrition }: Props) {
  const today = localDateStr()
  const { data: daily } = useDailyNutrition(today)
  const { data: weekly } = useWeeklyNutrition(today)

  // 7-day net calorie balance sparkline
  const sparkData = useMemo(() => {
    if (!weekly?.days) return null
    return {
      labels: weekly.days.map(d => {
        const dt = new Date(d.date + 'T12:00:00')
        return dt.toLocaleDateString(undefined, { weekday: 'short' })
      }),
      datasets: [{
        data: weekly.days.map(d => {
          // Net = intake - ride expenditure (BMR excluded for simplicity in sparkline)
          return d.meal_count > 0 ? d.calories - d.calories_out_rides : null
        }),
        borderColor: '#00d4aa',
        backgroundColor: 'rgba(0, 212, 170, 0.1)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      }],
    }
  }, [weekly])

  const sparkOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { enabled: false } },
    scales: {
      x: { display: false },
      y: { display: false },
    },
  } as const

  if (!daily) return null

  const netBalance = daily.net_caloric_balance
  const netColor = netBalance >= 0 ? 'text-green' : 'text-red'
  const netLabel = netBalance >= 0 ? 'surplus' : 'deficit'

  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
      {/* Section header */}
      <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center justify-between">
        <h2 className="text-sm font-bold text-text uppercase tracking-wider flex items-center gap-2">
          <Apple size={16} className="text-green" />
          Energy Balance
        </h2>
        <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Today</span>
      </div>

      <div className="p-5">
        {/* In / Out / Net */}
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="text-center">
            <p className="text-2xl font-bold text-accent">{daily.total_calories_in.toLocaleString()}</p>
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">In (kcal)</p>
            <p className="text-xs text-text-muted">{daily.meal_count} meal{daily.meal_count !== 1 ? 's' : ''}</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-yellow">{daily.calories_out.total.toLocaleString()}</p>
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Out (kcal)</p>
            <p className="text-xs text-text-muted">{daily.calories_out.rides > 0 ? `${daily.calories_out.rides} rides` : 'BMR only'}</p>
          </div>
          <div className="text-center">
            <p className={`text-2xl font-bold ${netColor}`}>{Math.abs(netBalance).toLocaleString()}</p>
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{netLabel}</p>
          </div>
        </div>

        {/* Ratio bar */}
        {daily.calories_out.total > 0 && (
          <div className="mb-4">
            <div className="h-2 bg-surface-low rounded-full overflow-hidden flex">
              <div
                className="bg-accent rounded-l-full"
                style={{ width: `${Math.min((daily.total_calories_in / (daily.total_calories_in + daily.calories_out.total)) * 100, 100)}%` }}
              />
              <div className="bg-yellow flex-1 rounded-r-full" />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[9px] text-text-muted">In: {daily.total_calories_in > 0 ? Math.round((daily.total_calories_in / (daily.total_calories_in + daily.calories_out.total)) * 100) : 0}%</span>
              <span className="text-[9px] text-text-muted">Out: {Math.round((daily.calories_out.total / (daily.total_calories_in + daily.calories_out.total)) * 100)}%</span>
            </div>
          </div>
        )}

        {/* Weekly sparkline */}
        {sparkData && (
          <div className="mb-4">
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest mb-2">This Week</p>
            <div className="h-16">
              <Line data={sparkData} options={sparkOptions} />
            </div>
          </div>
        )}

        {/* CTA */}
        {onNavigateToNutrition && (
          <button
            onClick={onNavigateToNutrition}
            className="flex items-center gap-1 text-accent text-xs font-bold uppercase tracking-widest hover:opacity-80 transition-opacity"
          >
            Log a Meal <ChevronRight size={14} />
          </button>
        )}
      </div>
    </div>
  )
}
