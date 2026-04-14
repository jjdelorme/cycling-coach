import { useState } from 'react'
import { Bar } from 'react-chartjs-2'
import { useMeals, useDailyNutrition, useWeeklyNutrition } from '../hooks/useApi'
import { useChartColors } from '../lib/theme'
import DailySummaryStrip from '../components/DailySummaryStrip'
import MealTimeline from '../components/MealTimeline'
import MealCapture from '../components/MealCapture'
import MealPlanCalendar from '../components/MealPlanCalendar'
import { Loader2 } from 'lucide-react'

interface Props {
  onOpenNutritionist?: (context?: string, sessionId?: string) => void
}

export default function Nutrition({ onOpenNutritionist }: Props) {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [viewMode, setViewMode] = useState<'day' | 'week' | 'plan'>('day')

  const { data: dailyData, isLoading: dailyLoading } = useDailyNutrition(date)
  const { data: mealsData, isLoading: mealsLoading } = useMeals({
    start_date: date,
    end_date: date,
    limit: 50,
  })
  const { data: weeklyData } = useWeeklyNutrition(date)
  const cc = useChartColors()

  const isLoading = dailyLoading || mealsLoading

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-sm font-bold text-text uppercase tracking-wider">Nutrition</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode('day')}
            className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest ${
              viewMode === 'day' ? 'bg-accent text-white' : 'text-text-muted hover:text-text'
            }`}
          >Day</button>
          <button
            onClick={() => setViewMode('week')}
            className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest ${
              viewMode === 'week' ? 'bg-accent text-white' : 'text-text-muted hover:text-text'
            }`}
          >Week</button>
          <button
            onClick={() => setViewMode('plan')}
            className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest ${
              viewMode === 'plan' ? 'bg-accent text-white' : 'text-text-muted hover:text-text'
            }`}
          >Plan</button>
        </div>
      </div>

      {viewMode === 'day' && (
        <>
          {/* Daily summary strip */}
          {dailyData && <DailySummaryStrip data={dailyData} />}

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={24} className="animate-spin text-accent opacity-50" />
            </div>
          )}

          {/* Meal timeline */}
          {!isLoading && (
            <MealTimeline
              meals={mealsData?.meals ?? []}
              date={date}
              onDateChange={setDate}
              onAskNutritionist={onOpenNutritionist}
            />
          )}
        </>
      )}

      {viewMode === 'week' && weeklyData && (
        <div className="bg-surface rounded-xl border border-border p-5 shadow-sm">
          {/* Weekly averages */}
          <div className="flex gap-6 mb-4 flex-wrap">
            <div>
              <span className="text-lg font-bold text-accent">{weeklyData.avg_daily_calories}</span>
              <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest ml-1">avg kcal/day</span>
            </div>
            <div>
              <span className="text-sm font-bold text-green">{Math.round(weeklyData.avg_daily_protein_g)}g P</span>
            </div>
            <div>
              <span className="text-sm font-bold text-yellow">{Math.round(weeklyData.avg_daily_carbs_g)}g C</span>
            </div>
            <div>
              <span className="text-sm font-bold text-blue">{Math.round(weeklyData.avg_daily_fat_g)}g F</span>
            </div>
          </div>

          {/* Stacked bar chart */}
          <div className="h-48">
            <Bar
              data={{
                labels: weeklyData.days.map(d => {
                  const dt = new Date(d.date + 'T12:00:00')
                  return dt.toLocaleDateString(undefined, { weekday: 'short' })
                }),
                datasets: [
                  {
                    label: 'Protein',
                    data: weeklyData.days.map(d => Math.round(d.protein_g * 4)),
                    backgroundColor: '#00d4aa',
                  },
                  {
                    label: 'Carbs',
                    data: weeklyData.days.map(d => Math.round(d.carbs_g * 4)),
                    backgroundColor: '#eab308',
                  },
                  {
                    label: 'Fat',
                    data: weeklyData.days.map(d => Math.round(d.fat_g * 9)),
                    backgroundColor: '#4a9eff',
                  },
                ],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                  legend: {
                    labels: { color: cc.legendColor, boxWidth: 10, font: { size: 11 } },
                    position: 'top',
                    align: 'end',
                  },
                  tooltip: {
                    backgroundColor: cc.tooltipBg,
                    titleColor: cc.tooltipTitle,
                    bodyColor: cc.tooltipBody,
                    borderColor: cc.tooltipBorder,
                    borderWidth: 1,
                  },
                },
                scales: {
                  x: {
                    stacked: true,
                    ticks: { color: cc.tickColor },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' },
                  },
                  y: {
                    stacked: true,
                    ticks: { color: cc.tickColor },
                    grid: { display: false },
                  },
                },
              }}
            />
          </div>
        </div>
      )}

      {viewMode === 'plan' && (
        <MealPlanCalendar onOpenNutritionist={onOpenNutritionist} />
      )}

      {/* FAB for meal capture */}
      <MealCapture
        onMealSaved={() => {
          // Navigate to today's day view so the new meal is visible
          const today = new Date().toISOString().slice(0, 10)
          if (date !== today) setDate(today)
          if (viewMode !== 'day') setViewMode('day')
        }}
        onOpenNutritionist={onOpenNutritionist}
      />
    </div>
  )
}
