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
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { usePMC, useRides, useWeeklySummary, useDailySummary } from '../hooks/useApi'
import type { DailySummary } from '../types/api'
import { fetchWeekPlan } from '../lib/api'
import { fmtDuration, fmtDistance, fmtWeight, fmtSport, fmtDateStr, localDateStr } from '../lib/format'
import { useUnits } from '../lib/units'
import { useChartColors } from '../lib/theme'
import {
  TrendingUp,
  Zap,
  Activity,
  Weight,
  Calendar,
  ChevronRight
} from 'lucide-react'
import SportIcon from '../components/SportIcon'
import NutritionDashboardWidget from '../components/NutritionDashboardWidget'
import { isoWeekToMonday, buildPlannedByMonday } from '../lib/chart-helpers'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Legend, Filler)

const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

type MetricKey = 'tss' | 'hours' | 'calories' | 'distance' | 'ascent' | 'power'

interface MetricDef {
  key: MetricKey
  label: string
  color: string
  yAxisID: string
  fmt: (v: number, imperial: boolean) => string
  getValue: (s: DailySummary, imperial: boolean) => number | null
}

const METRICS: MetricDef[] = [
  {
    key: 'tss', label: 'TSS', color: 'rgb(233,69,96)', yAxisID: 'y_tss',
    fmt: (v) => `${Math.round(v)}`,
    getValue: (s) => s.tss > 0 ? Math.round(s.tss) : null,
  },
  {
    key: 'hours', label: 'Hours', color: 'rgb(74,158,255)', yAxisID: 'y_hrs',
    fmt: (v) => `${v.toFixed(1)}h`,
    getValue: (s) => s.duration_s > 0 ? parseFloat((s.duration_s / 3600).toFixed(2)) : null,
  },
  {
    key: 'calories', label: 'Kcal', color: 'rgb(251,146,60)', yAxisID: 'y_cal',
    fmt: (v) => v.toLocaleString(),
    getValue: (s) => s.total_calories > 0 ? s.total_calories : null,
  },
  {
    key: 'distance', label: 'Miles', color: 'rgb(0,212,170)', yAxisID: 'y_dist',
    fmt: (v, imp) => `${v.toFixed(1)}${imp ? 'mi' : 'km'}`,
    getValue: (s, imp) => s.distance_m > 0 ? parseFloat((s.distance_m / (imp ? 1609.34 : 1000)).toFixed(2)) : null,
  },
  {
    key: 'ascent', label: 'Climbing', color: 'rgb(234,179,8)', yAxisID: 'y_asc',
    fmt: (v, imp) => `${Math.round(v)}${imp ? 'ft' : 'm'}`,
    getValue: (s, imp) => s.ascent_m > 0 ? Math.round(s.ascent_m * (imp ? 3.28084 : 1)) : null,
  },
  {
    key: 'power', label: 'Avg W', color: 'rgb(167,139,250)', yAxisID: 'y_pwr',
    fmt: (v) => `${Math.round(v)}w`,
    getValue: (s) => s.avg_power ?? null,
  },
]

function SevenDayStrip({ data, today, days: numDays = 7 }: { data: DailySummary[]; today: string; days?: number }) {
  const cc = useChartColors()
  const units = useUnits()
  const imperial = units === 'imperial'
  const [active, setActive] = useState<Set<MetricKey>>(new Set(['tss', 'hours', 'calories']))

  const byDate = new Map(data.map((d) => [d.date, d]))
  const dates: string[] = []
  for (let i = numDays - 1; i >= 0; i--) {
    const d = new Date(today + 'T00:00:00')
    d.setDate(d.getDate() - i)
    const y = d.getFullYear(), mo = String(d.getMonth() + 1).padStart(2, '0'), dy = String(d.getDate()).padStart(2, '0')
    dates.push(`${y}-${mo}-${dy}`)
  }

  const entries = dates.map((date) => ({ date, summary: byDate.get(date) ?? null }))
  const todayIdx = entries.findIndex((e) => e.date === today)
  const labels = entries.map((e) => {
    const d = new Date(e.date + 'T00:00:00')
    return `${DAY_LABELS[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()}`
  })

  const pointRadii = entries.map((_, i) => (i === todayIdx ? 5 : 3))

  // Build one Y-axis per metric (all hidden except left/right for first two active)
  const activeList = METRICS.filter((m) => active.has(m.key))
  const scales: Record<string, object> = {
    x: {
      ticks: { color: cc.tickColor, font: { size: 10 }, maxTicksLimit: 7 },
      grid: { display: false },
    },
  }
  METRICS.forEach((m) => {
    const isFirst = activeList[0]?.key === m.key
    const isSecond = activeList[1]?.key === m.key
    scales[m.yAxisID] = {
      position: isSecond ? 'right' : 'left',
      display: isFirst || isSecond,
      beginAtZero: true,
      ticks: {
        color: isFirst ? activeList[0].color : isSecond ? activeList[1].color : cc.tickColor,
        font: { size: 9 },
        maxTicksLimit: 5,
      },
      grid: isFirst
        ? { color: 'rgba(148, 163, 184, 0.08)' }
        : { drawOnChartArea: false },
    }
  })

  const datasets = METRICS.filter((m) => active.has(m.key)).map((m) => ({
    label: m.label,
    yAxisID: m.yAxisID,
    data: entries.map((e) => (e.summary ? m.getValue(e.summary, imperial) : null)),
    borderColor: m.color,
    backgroundColor: m.color.replace('rgb(', 'rgba(').replace(')', ', 0.06)'),
    fill: false,
    spanGaps: false,
    tension: 0.3,
    borderWidth: 2,
    pointRadius: pointRadii,
    pointBackgroundColor: entries.map((_, i) => (i === todayIdx ? '#4a9eff' : m.color)),
    pointHoverRadius: 6,
  }))

  const chartData = { labels, datasets }
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: cc.tooltipBg,
        titleColor: cc.tooltipTitle,
        bodyColor: cc.tooltipBody,
        borderColor: cc.tooltipBorder,
        borderWidth: 1,
        callbacks: {
          label: (ctx: any) => {
            const m = METRICS.find((m) => m.label === ctx.dataset.label)
            const v = ctx.parsed.y
            return v !== null ? `${ctx.dataset.label}: ${m ? m.fmt(v, imperial) : v}` : ''
          },
        },
      },
    },
    scales,
  }

  const toggle = (key: MetricKey) => {
    setActive((prev) => {
      const next = new Set(prev)
      if (next.has(key)) { if (next.size > 1) next.delete(key) }
      else next.add(key)
      return next
    })
  }

  return (
    <div className="bg-surface rounded-xl border border-border p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold text-text uppercase tracking-wider">Last 7 Days</h2>
        <div className="flex flex-wrap gap-2">
          {METRICS.map((m) => {
            const on = active.has(m.key)
            return (
              <button
                key={m.key}
                onClick={() => toggle(m.key)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-widest border transition-all"
                style={on
                  ? { borderColor: m.color, color: m.color, background: m.color.replace('rgb(', 'rgba(').replace(')', ', 0.12)') }
                  : { borderColor: 'rgba(148,163,184,0.2)', color: 'rgba(148,163,184,0.5)', background: 'transparent' }
                }
              >
                <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: on ? m.color : 'rgba(148,163,184,0.3)' }} />
                {m.label}
              </button>
            )
          })}
        </div>
      </div>
      <div style={{ height: '220px' }}>
        <Line data={chartData} options={chartOptions as any} />
      </div>
    </div>
  )
}

interface Props {
  onRideSelect?: (id: number) => void
  onWorkoutSelect?: (id: number, date: string) => void
  onNavigateToNutrition?: () => void
}

export default function Dashboard({ onRideSelect, onWorkoutSelect, onNavigateToNutrition }: Props) {
  const units = useUnits()
  const { data: pmcData, isLoading: pmcLoading } = usePMC()
  const { data: rides, isLoading: ridesLoading } = useRides({ limit: 7 })
  const { data: weekly, isLoading: weeklyLoading } = useWeeklySummary()
  const { data: dailyData } = useDailySummary(7)
  const cc = useChartColors()

  // Compute Monday dates for this week + next 3
  const { planMondays, thisMonday } = useMemo(() => {
    const now = new Date()
    const dow = now.getDay()
    const thisMon = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (dow === 0 ? 6 : dow - 1))
    const fmt = localDateStr
    const mondays: string[] = []
    for (let i = 0; i < 4; i++) {
      const m = new Date(thisMon)
      m.setDate(m.getDate() + i * 7)
      mondays.push(fmt(m))
    }
    return { planMondays: mondays, thisMonday: fmt(thisMon) }
  }, [])

  // Fetch planned workouts for this week + next 3 weeks
  const { data: plannedWeeks, isLoading: plannedLoading } = useQuery({
    queryKey: ['planned-weeks', planMondays],
    queryFn: () => Promise.all(planMondays.map((m) => fetchWeekPlan(m))),
  })

  // Aggregate planned TSS/hours by week monday
  const plannedByMonday = useMemo(
    () => buildPlannedByMonday(planMondays, plannedWeeks ?? []),
    [planMondays, plannedWeeks],
  )

  // Find next upcoming workout (today if no ride yet, otherwise tomorrow+)
  const today = localDateStr()
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
                    {nextWorkout.date === today ? 'Today' : fmtDateStr(nextWorkout.date)}
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
              <SportIcon sport={latestRide?.sport} size={16} className="text-green" />
              {latestRide?.isToday ? "Today's Ride" : 'Last Ride'}
            </h2>
          </div>
          <div className="p-5">
            {latestRide ? (
              <div className="cursor-pointer group" onClick={() => onRideSelect?.(latestRide.id)}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold text-text group-hover:text-accent transition-colors">
                    {latestRide.title || fmtSport(latestRide.sub_sport) || fmtSport(latestRide.sport)}
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

        {/* Energy Balance Widget */}
        <NutritionDashboardWidget onNavigateToNutrition={onNavigateToNutrition} />

        {/* Last 7 Days — sits beside Energy Balance */}
        <SevenDayStrip data={dailyData ?? []} today={today} days={7} />
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
            {weekly && weekly.length > 0 ? (() => {
              // Build unified week list: last 12 actuals + up to 3 future planned weeks
              const actualWeeks = weekly.slice(-12)
              const actualWeekSet = new Set(actualWeeks.map(w => isoWeekToMonday(w.week)))
              const futureWeeks: { week: string; monday: string }[] = []
              for (let i = 1; i <= 3; i++) {
                const monday = planMondays[i]
                if (monday && !actualWeekSet.has(monday) && plannedByMonday.has(monday)) {
                  const d = new Date(monday + 'T00:00:00')
                  const jan1 = new Date(d.getFullYear(), 0, 1)
                  const dayOfYear = Math.floor((d.getTime() - jan1.getTime()) / 86400000)
                  const weekNum = Math.ceil((dayOfYear + jan1.getDay() + 1) / 7)
                  futureWeeks.push({ week: `W${String(weekNum).padStart(2, '0')}`, monday })
                }
              }

              const weekLabels = [
                ...actualWeeks.map(w => w.week.slice(5)),
                ...futureWeeks.map(w => w.week),
              ]
              const weekMondays = [
                ...actualWeeks.map(w => isoWeekToMonday(w.week)),
                ...futureWeeks.map(w => w.monday),
              ]
              const thisWeekIdx = weekMondays.indexOf(thisMonday)
              const thisWeekPlan = plannedByMonday.get(thisMonday)

              // Per-bar colors: solid for actuals, faded for future planned-only
              const tssColors = weekMondays.map(m =>
                m > thisMonday ? 'rgba(233, 69, 96, 0.25)' : 'rgba(233, 69, 96, 0.7)'
              )
              const hoursColors = weekMondays.map(m =>
                m > thisMonday ? 'rgba(0, 212, 170, 0.25)' : 'rgba(0, 212, 170, 0.7)'
              )

              // Data: actuals + future planned values
              const tssData = [
                ...actualWeeks.map(w => w.tss),
                ...futureWeeks.map(fw => plannedByMonday.get(fw.monday)?.tss ?? 0),
              ]
              const hoursData = [
                ...actualWeeks.map(w => w.duration_h),
                ...futureWeeks.map(fw => plannedByMonday.get(fw.monday)?.hours ?? 0),
              ]

              // Custom plugin: draw ghost bars behind actuals for current week
              const plannedOverlayPlugin = {
                id: 'plannedOverlay',
                beforeDatasetsDraw(chart: ChartJS) {
                  if (thisWeekIdx < 0 || !thisWeekPlan) return
                  const { ctx } = chart
                  const tssMeta = chart.getDatasetMeta(0) // TSS dataset
                  const hrMeta = chart.getDatasetMeta(1)  // Hours dataset

                  // Draw planned TSS ghost bar
                  if (thisWeekPlan.tss > 0 && tssMeta.data[thisWeekIdx]) {
                    const bar = tssMeta.data[thisWeekIdx] as any
                    const yScale = chart.scales.y
                    const plannedY = yScale.getPixelForValue(thisWeekPlan.tss)
                    const baseY = yScale.getPixelForValue(0)
                    ctx.save()
                    ctx.fillStyle = 'rgba(233, 69, 96, 0.12)'
                    ctx.strokeStyle = 'rgba(233, 69, 96, 0.4)'
                    ctx.lineWidth = 1.5
                    ctx.setLineDash([4, 4])
                    const x = bar.x - bar.width / 2
                    ctx.fillRect(x, plannedY, bar.width, baseY - plannedY)
                    ctx.strokeRect(x, plannedY, bar.width, baseY - plannedY)
                    ctx.restore()
                  }

                  // Draw planned Hours ghost bar
                  if (thisWeekPlan.hours > 0 && hrMeta.data[thisWeekIdx]) {
                    const bar = hrMeta.data[thisWeekIdx] as any
                    const yScale = chart.scales.y1
                    const plannedY = yScale.getPixelForValue(thisWeekPlan.hours)
                    const baseY = yScale.getPixelForValue(0)
                    ctx.save()
                    ctx.fillStyle = 'rgba(0, 212, 170, 0.12)'
                    ctx.strokeStyle = 'rgba(0, 212, 170, 0.4)'
                    ctx.lineWidth = 1.5
                    ctx.setLineDash([4, 4])
                    const x = bar.x - bar.width / 2
                    ctx.fillRect(x, plannedY, bar.width, baseY - plannedY)
                    ctx.strokeRect(x, plannedY, bar.width, baseY - plannedY)
                    ctx.restore()
                  }
                },
              }

              return (
                <Bar
                  plugins={[plannedOverlayPlugin]}
                  data={{
                    labels: weekLabels,
                    datasets: [
                      {
                        label: 'TSS',
                        data: tssData,
                        backgroundColor: tssColors,
                        borderRadius: 4,
                        yAxisID: 'y',
                      },
                      {
                        label: 'Hours',
                        data: hoursData,
                        backgroundColor: hoursColors,
                        borderRadius: 4,
                        yAxisID: 'y1',
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                      x: {
                        grid: { display: false },
                        ticks: {
                          color: (ctx) => ctx.index === thisWeekIdx ? '#4a9eff' : cc.tickColor,
                          font: (ctx) => ({ weight: ctx.index === thisWeekIdx ? 'bold' as const : 'normal' as const }),
                        },
                      },
                      y: {
                        position: 'left',
                        title: { display: true, text: 'TSS', color: cc.tickColor, font: { size: 10, weight: 'bold' } },
                        ticks: { color: cc.tickColor },
                        grid: { color: 'rgba(148, 163, 184, 0.1)' },
                      },
                      y1: {
                        position: 'right',
                        title: { display: true, text: 'Hours', color: cc.tickColor, font: { size: 10, weight: 'bold' } },
                        ticks: { color: cc.tickColor },
                        grid: { drawOnChartArea: false },
                      },
                    },
                    plugins: {
                      legend: {
                        position: 'top',
                        align: 'end',
                        labels: { color: cc.legendColor, boxWidth: 12, font: { size: 11 } },
                      },
                      tooltip: {
                        callbacks: {
                          label: (ctx) => {
                            const monday = weekMondays[ctx.dataIndex]
                            const label = ctx.dataset.label ?? ''
                            const val = ctx.parsed.y ?? 0
                            if (monday === thisMonday && thisWeekPlan) {
                              if (label === 'TSS') return `TSS: ${Math.round(val)} / ${Math.round(thisWeekPlan.tss)} planned`
                              if (label === 'Hours') return `Hours: ${val.toFixed(1)} / ${thisWeekPlan.hours.toFixed(1)} planned`
                            }
                            if (label === 'TSS') return `TSS: ${Math.round(val)}`
                            if (label === 'Hours') return `Hours: ${val.toFixed(1)}`
                            return `${label}: ${val}`
                          },
                        },
                      },
                    },
                  }}
                />
              )
            })() : <p className="text-text-muted text-sm py-8 italic">No weekly data available.</p>}
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
                  <td className="py-3 px-5 text-text-muted flex items-center gap-2">
                    <SportIcon sport={ride.sport} size={14} />
                    {fmtSport(ride.sub_sport || ride.sport)}
                  </td>
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
