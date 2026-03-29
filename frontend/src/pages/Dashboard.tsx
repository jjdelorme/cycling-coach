import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line, Bar } from 'react-chartjs-2'
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { usePMC, useRides, useWeeklySummary } from '../hooks/useApi'
import { fetchWeekPlan } from '../lib/api'
import { fmtDuration, fmtDistance, fmtWeight } from '../lib/format'
import { useUnits } from '../lib/units'
import { useChartColors } from '../lib/theme'
import { 
  TrendingUp, 
  Zap, 
  Activity, 
  Weight, 
  Calendar, 
  Bike,
  ChevronRight
} from 'lucide-react'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Legend, Filler)

interface Props {
  onRideSelect?: (id: number) => void
  onWorkoutSelect?: (id: number, date: string) => void
}

export default function Dashboard({ onRideSelect, onWorkoutSelect }: Props) {
  const units = useUnits()
  const { data: pmcData, isLoading: pmcLoading } = usePMC()
  const { data: rides, isLoading: ridesLoading } = useRides({ limit: 7 })
  const { data: weekly, isLoading: weeklyLoading } = useWeeklySummary()
  const cc = useChartColors()

  // Compute Monday dates for this week + next 3
  const { planMondays } = useMemo(() => {
    const now = new Date()
    const dow = now.getDay()
    const thisMon = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (dow === 0 ? 6 : dow - 1))
    const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const mondays: string[] = []
    for (let i = 0; i < 4; i++) {
      const m = new Date(thisMon)
      m.setDate(m.getDate() + i * 7)
      mondays.push(fmt(m))
    }
    return { planMondays: mondays }
  }, [])

  // Fetch planned workouts for this week + next 3 weeks
  const { data: plannedWeeks, isLoading: plannedLoading } = useQuery({
    queryKey: ['planned-weeks', planMondays],
    queryFn: () => Promise.all(planMondays.map((m) => fetchWeekPlan(m))),
  })

  // Find next upcoming workout (today if no ride yet, otherwise tomorrow+)
  const today = new Date().toISOString().slice(0, 10)
  const rodeTodayAlready = rides?.some((r) => r.date === today) ?? false

  const nextWorkout = useMemo(() => {
    if (!plannedWeeks) return null
    const upcoming: { id?: number; date: string; name: string; duration_s: number; tss: number; notes?: string }[] = []
    for (const wp of plannedWeeks) {
      for (const w of wp.planned) {
        if (w.date && (rodeTodayAlready ? w.date > today : w.date >= today)) {
          upcoming.push({
            id: w.id,
            date: w.date,
            name: w.name || 'Workout',
            duration_s: w.total_duration_s || 0,
            tss: Number(w.planned_tss || 0),
            notes: w.coach_notes || undefined,
          })
        }
      }
    }
    upcoming.sort((a, b) => a.date.localeCompare(b.date))
    return upcoming[0] || null
  }, [plannedWeeks, today, rodeTodayAlready])

  const latestRide = useMemo(() => {
    if (!rides || rides.length === 0) return null
    const todayRide = rides.find((r) => r.date === today)
    if (todayRide) return { ...todayRide, isToday: true }
    return { ...rides[0], isToday: false }
  }, [rides, today])

  if (pmcLoading || ridesLoading || weeklyLoading || plannedLoading) {
    return <div className="p-6 text-text-muted animate-pulse">Loading dashboard...</div>
  }

  const lastPMC = pmcData && pmcData.length > 0 ? pmcData[pmcData.length - 1] : null
  const pmc90 = pmcData ? pmcData.slice(-90) : []
  const tsbValue = lastPMC?.tsb ?? 0
  const tsbColor = tsbValue >= 0 ? 'text-green' : 'text-red'

  const metricCards = [
    { label: 'Fitness (CTL)', value: lastPMC?.ctl?.toFixed(0) ?? '--', color: 'text-green', icon: TrendingUp },
    { label: 'Fatigue (ATL)', value: lastPMC?.atl?.toFixed(0) ?? '--', color: 'text-red', icon: Zap },
    { label: 'Form (TSB)', value: lastPMC?.tsb?.toFixed(0) ?? '--', color: tsbColor, icon: Activity },
    { label: 'Weight', value: fmtWeight(lastPMC?.weight), color: 'text-yellow', icon: Weight },
  ]

  const chartData = {
    labels: pmc90.map((d) => d.date),
    datasets: [
      { label: 'CTL', data: pmc90.map((d) => d.ctl ?? null), borderColor: '#00d4aa', borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false },
      { label: 'ATL', data: pmc90.map((d) => d.atl ?? null), borderColor: '#e94560', borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false },
      { label: 'TSB', data: pmc90.map((d) => d.tsb ?? null), borderColor: '#4a9eff', backgroundColor: 'rgba(74, 158, 255, 0.1)', borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true },
    ],
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: { labels: { color: cc.legendColor, boxWidth: 12, font: { size: 12 } }, position: 'top' as const, align: 'end' as const },
      tooltip: { backgroundColor: cc.tooltipBg, titleColor: cc.tooltipTitle, bodyColor: cc.tooltipBody, borderColor: cc.tooltipBorder, borderWidth: 1 },
    },
    scales: {
      x: { ticks: { color: cc.tickColor, maxTicksLimit: 10 }, grid: { display: false } },
      y: { ticks: { color: cc.tickColor }, grid: { color: 'rgba(148, 163, 184, 0.1)' } },
    },
  }

  return (
    <div className="space-y-6">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {metricCards.map((card) => (
          <div key={card.label} className="bg-surface rounded-xl border border-border p-5 shadow-sm hover:border-accent/30 transition-all group">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">{card.label}</span>
              <card.icon size={16} className="text-text-muted group-hover:text-accent transition-colors" />
            </div>
            <p className={`text-3xl font-bold ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Next Workout */}
        <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
          <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center justify-between">
            <h2 className="text-sm font-bold text-text uppercase tracking-wider flex items-center gap-2">
              <Calendar size={16} className="text-accent" />
              Next Workout
            </h2>
          </div>
          <div className="p-5">
            {nextWorkout ? (
              <div
                className={nextWorkout.id ? "cursor-pointer group" : ""}
                onClick={() => nextWorkout.id && onWorkoutSelect?.(nextWorkout.id, nextWorkout.date)}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xl font-bold text-text group-hover:text-accent transition-colors">{nextWorkout.name}</h3>
                  <span className="text-xs font-medium px-2.5 py-1 bg-accent/10 text-accent rounded-full capitalize">
                    {nextWorkout.date === today ? 'Today' : new Date(nextWorkout.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                  </span>
                </div>
                <div className="flex gap-4 mb-4">
                  <div className="flex items-center gap-1.5 text-sm text-text-muted">
                    <Zap size={14} className="text-yellow" />
                    <span>{Math.round(nextWorkout.tss)} TSS</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-sm text-text-muted">
                    <Activity size={14} className="text-blue" />
                    <span>{fmtDuration(nextWorkout.duration_s)}</span>
                  </div>
                </div>
                {nextWorkout.notes && (
                  <div className="bg-surface-low rounded-lg p-3 text-sm text-text-muted line-clamp-3 italic">
                    {nextWorkout.notes}
                  </div>
                )}
                {nextWorkout.id && (
                  <div className="mt-4 flex items-center gap-1 text-accent text-xs font-bold uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                    View Details <ChevronRight size={14} />
                  </div>
                )}
              </div>
            ) : (
              <p className="text-text-muted text-sm py-4 italic">No upcoming workouts planned</p>
            )}
          </div>
        </div>

        {/* Latest Ride */}
        <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
          <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center justify-between">
            <h2 className="text-sm font-bold text-text uppercase tracking-wider flex items-center gap-2">
              <Bike size={16} className="text-green" />
              {latestRide?.isToday ? "Today's Ride" : 'Last Ride'}
            </h2>
          </div>
          <div className="p-5">
            {latestRide ? (
              <div className="cursor-pointer group" onClick={() => onRideSelect?.(latestRide.id)}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold text-text group-hover:text-accent transition-colors">
                    {latestRide.title || latestRide.sub_sport || latestRide.sport || 'Ride'}
                  </h3>
                  <span className="text-xs font-medium text-text-muted">
                    {latestRide.isToday ? 'Today' : latestRide.date}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  <div>
                    <span className="text-[10px] font-bold text-text-muted uppercase tracking-tighter block mb-1">TSS</span>
                    <span className="text-lg font-bold text-accent">{latestRide.tss?.toFixed(0) ?? '--'}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-text-muted uppercase tracking-tighter block mb-1">Power</span>
                    <span className="text-lg font-bold text-blue">{latestRide.avg_power ? `${latestRide.avg_power}w` : '--'}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-text-muted uppercase tracking-tighter block mb-1">Distance</span>
                    <span className="text-lg font-bold text-text">{fmtDistance(latestRide.distance_m, units)}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-text-muted uppercase tracking-tighter block mb-1">Duration</span>
                    <span className="text-lg font-bold text-text">{fmtDuration(latestRide.duration_s)}</span>
                  </div>
                </div>
                <div className="mt-4 flex items-center gap-1 text-accent text-xs font-bold uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                  View Analysis <ChevronRight size={14} />
                </div>
              </div>
            ) : (
              <p className="text-text-muted text-sm py-4 italic">No recent rides found</p>
            )}
          </div>
        </div>
      </div>

      {/* Main Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface rounded-xl border border-border p-5 shadow-sm">
          <h2 className="text-sm font-bold text-text uppercase tracking-wider mb-6">Fitness Trends (PMC)</h2>
          <div className="h-80">
            {pmc90.length > 0 ? <Line data={chartData} options={chartOptions} /> : <p className="text-text-muted text-sm py-8 italic">No PMC data available.</p>}
          </div>
        </div>

        <div className="bg-surface rounded-xl border border-border p-5 shadow-sm">
          <h2 className="text-sm font-bold text-text uppercase tracking-wider mb-6">Weekly Training Load</h2>
          <div className="h-80">
            {weekly && weekly.length > 0 ? (
              <Bar 
                data={{
                  labels: weekly.slice(-12).map(w => w.week.slice(5)),
                  datasets: [
                    { 
                      label: 'TSS', 
                      data: weekly.slice(-12).map(w => w.tss), 
                      backgroundColor: 'rgba(233, 69, 96, 0.7)', 
                      borderRadius: 4,
                      yAxisID: 'y'
                    },
                    { 
                      label: 'Hours', 
                      data: weekly.slice(-12).map(w => w.duration_h), 
                      backgroundColor: 'rgba(0, 212, 170, 0.7)', 
                      borderRadius: 4,
                      yAxisID: 'y1'
                    }
                  ]
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  scales: {
                    x: { grid: { display: false }, ticks: { color: cc.tickColor } },
                    y: { 
                      position: 'left',
                      title: { display: true, text: 'TSS', color: cc.tickColor, font: { size: 10, weight: 'bold' } },
                      ticks: { color: cc.tickColor }, 
                      grid: { color: 'rgba(148, 163, 184, 0.1)' } 
                    },
                    y1: { 
                      position: 'right',
                      title: { display: true, text: 'Hours', color: cc.tickColor, font: { size: 10, weight: 'bold' } },
                      ticks: { color: cc.tickColor }, 
                      grid: { drawOnChartArea: false } 
                    }
                  },
                  plugins: { 
                    legend: { 
                      position: 'top',
                      align: 'end',
                      labels: { color: cc.legendColor, boxWidth: 12, font: { size: 11 } } 
                    } 
                  }
                }}
              />
            ) : <p className="text-text-muted text-sm py-8 italic">No weekly data available.</p>}
          </div>
        </div>
      </div>

      {/* Rides Table */}
      <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b border-border bg-surface-low">
          <h2 className="text-sm font-bold text-text uppercase tracking-wider">Recent Rides</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] font-bold text-text-muted uppercase tracking-widest bg-surface-low/50">
                <th className="text-left py-3 px-5">Date</th>
                <th className="text-left py-3 px-5">Sport</th>
                <th className="text-right py-3 px-5">Duration</th>
                <th className="text-right py-3 px-5">Distance</th>
                <th className="text-right py-3 px-5">TSS</th>
                <th className="text-right py-3 px-5">Avg Power</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {rides?.map((ride) => (
                <tr
                  key={ride.id}
                  onClick={() => onRideSelect?.(ride.id)}
                  className="text-text hover:bg-surface2/50 transition-colors cursor-pointer group"
                >
                  <td className="py-3 px-5 font-medium">{ride.date}</td>
                  <td className="py-3 px-5 text-text-muted">{ride.sub_sport || ride.sport || '--'}</td>
                  <td className="py-3 px-5 text-right font-mono">{fmtDuration(ride.duration_s)}</td>
                  <td className="py-3 px-5 text-right font-mono">{fmtDistance(ride.distance_m, units)}</td>
                  <td className="py-3 px-5 text-right font-bold text-accent">{ride.tss?.toFixed(0) ?? '--'}</td>
                  <td className="py-3 px-5 text-right font-bold text-blue">{ride.avg_power ? `${ride.avg_power}w` : '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
