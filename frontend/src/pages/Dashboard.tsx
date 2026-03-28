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

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Legend, Filler)

interface Props {
  onRideSelect?: (id: number) => void
}

export default function Dashboard({ onRideSelect }: Props) {
  const units = useUnits()
  const { data: pmcData, isLoading: pmcLoading } = usePMC()
  const { data: rides, isLoading: ridesLoading } = useRides({ limit: 7 })
  const { data: weekly, isLoading: weeklyLoading } = useWeeklySummary()
  const cc = useChartColors()

  // Convert ISO week string (YYYY-Www) to Monday date string (YYYY-MM-DD)
  const isoWeekToMonday = (isoWeek: string): string => {
    const match = isoWeek.match(/^(\d{4})-W(\d{2})$/)
    if (!match) return ''
    const year = parseInt(match[1])
    const week = parseInt(match[2])
    const jan4 = new Date(year, 0, 4)
    const mon = new Date(jan4)
    mon.setDate(jan4.getDate() - (jan4.getDay() || 7) + 1 + (week - 1) * 7)
    return `${mon.getFullYear()}-${String(mon.getMonth() + 1).padStart(2, '0')}-${String(mon.getDate()).padStart(2, '0')}`
  }

  // Compute Monday dates for this week + next 3
  const { thisMonday, planMondays } = useMemo(() => {
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
    return { thisMonday: fmt(thisMon), planMondays: mondays }
  }, [])

  // Fetch planned workouts for this week + next 3 weeks
  const { data: plannedWeeks, isLoading: plannedLoading } = useQuery({
    queryKey: ['planned-weeks', planMondays],
    queryFn: () => Promise.all(planMondays.map((m) => fetchWeekPlan(m))),
  })

  // Aggregate planned workouts by Monday date key
  const plannedByMonday = useMemo(() => {
    if (!plannedWeeks) return new Map<string, { tss: number; hours: number }>()
    const map = new Map<string, { tss: number; hours: number }>()
    for (const wp of plannedWeeks) {
      let totalSec = 0
      let totalTss = 0
      for (const w of wp.planned) {
        totalSec += w.total_duration_s ?? 0
        totalTss += Number(w.planned_tss ?? 0)
      }
      const hours = totalSec / 3600
      map.set(wp.week_start, {
        tss: Math.round(totalTss),
        hours: Math.round(hours * 10) / 10,
      })
    }
    return map
  }, [plannedWeeks])

  // Find next upcoming workout (today if no ride yet, otherwise tomorrow+)
  const today = new Date().toISOString().slice(0, 10)
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
  const rodeTodayAlready = rides?.some((r) => r.date === today) ?? false

  const nextWorkout = useMemo(() => {
    if (!plannedWeeks) return null
    const upcoming: { date: string; name: string; duration_s: number; tss: number; notes?: string }[] = []
    for (const wp of plannedWeeks) {
      for (const w of wp.planned) {
        if (w.date && (rodeTodayAlready ? w.date > today : w.date >= today)) {
          upcoming.push({
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

  // Find latest ride: today's ride, or yesterday's if none today
  const latestRide = useMemo(() => {
    if (!rides || rides.length === 0) return null
    const todayRide = rides.find((r) => r.date === today)
    if (todayRide) return { ...todayRide, isToday: true }
    const yesterdayRide = rides.find((r) => r.date === yesterday)
    if (yesterdayRide) return { ...yesterdayRide, isToday: false }
    return { ...rides[0], isToday: false }
  }, [rides, today, yesterday])

  if (pmcLoading || ridesLoading || weeklyLoading || plannedLoading) {
    return <div className="p-6 text-text-muted">Loading...</div>
  }

  const lastPMC = pmcData && pmcData.length > 0 ? pmcData[pmcData.length - 1] : null

  // Last 90 days of PMC data for chart
  const pmc90 = pmcData ? pmcData.slice(-90) : []

  const tsbValue = lastPMC?.tsb ?? 0
  const tsbColor = tsbValue >= 0 ? 'text-green' : 'text-red'

  const metricCards = [
    { label: 'CTL (Fitness)', value: lastPMC?.ctl?.toFixed(0) ?? '--', color: 'text-green' },
    { label: 'ATL (Fatigue)', value: lastPMC?.atl?.toFixed(0) ?? '--', color: 'text-red' },
    { label: 'TSB (Form)', value: lastPMC?.tsb?.toFixed(0) ?? '--', color: tsbColor },
    { label: 'Weight', value: fmtWeight(lastPMC?.weight), color: 'text-yellow' },
  ]

  const chartData = {
    labels: pmc90.map((d) => d.date),
    datasets: [
      {
        label: 'CTL',
        data: pmc90.map((d) => d.ctl ?? null),
        borderColor: '#22c55e',
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
      },
      {
        label: 'ATL',
        data: pmc90.map((d) => d.atl ?? null),
        borderColor: '#ef4444',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
      },
      {
        label: 'TSB',
        data: pmc90.map((d) => d.tsb ?? null),
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      legend: {
        labels: {
          color: cc.legendColor,
        },
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
        ticks: {
          color: cc.tickColor,
          maxTicksLimit: 10,
        },
        grid: {
          color: cc.gridColor,
        },
      },
      y: {
        ticks: {
          color: cc.tickColor,
        },
        grid: {
          color: cc.gridColor,
        },
      },
    },
  }

  return (
    <div className="space-y-6">
      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {metricCards.map((card) => (
          <div key={card.label} className="bg-surface rounded-lg border border-border p-4">
            <p className="text-sm text-text-muted">{card.label}</p>
            <p className={`text-2xl font-bold ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      {/* Next Workout + Latest Ride tiles */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Next Workout */}
        <div className="bg-surface rounded-lg border border-border p-4">
          <h2 className="text-sm font-medium text-text-muted mb-2">Next Workout</h2>
          {nextWorkout ? (
            <div>
              <div className="flex items-baseline justify-between">
                <p className="text-lg font-semibold text-text">{nextWorkout.name}</p>
                <span className="text-sm text-text-muted">
                  {nextWorkout.date === today ? 'Today' : new Date(nextWorkout.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                </span>
              </div>
              <div className="flex gap-4 mt-1 text-sm">
                {nextWorkout.duration_s > 0 && (
                  <span className="text-blue">{fmtDuration(nextWorkout.duration_s)}</span>
                )}
                {nextWorkout.tss > 0 && (
                  <span className="text-accent">{Math.round(nextWorkout.tss)} TSS</span>
                )}
              </div>
              {nextWorkout.notes && (
                <p className="mt-2 text-xs text-text-muted line-clamp-2">{nextWorkout.notes}</p>
              )}
            </div>
          ) : (
            <p className="text-text-muted text-sm">No upcoming workouts planned</p>
          )}
        </div>

        {/* Latest Ride */}
        <div className="bg-surface rounded-lg border border-border p-4">
          <h2 className="text-sm font-medium text-text-muted mb-2">
            {latestRide?.isToday ? "Today's Ride" : 'Last Ride'}
          </h2>
          {latestRide ? (
            <div
              className="cursor-pointer hover:bg-surface2 -m-4 p-4 rounded-lg transition-colors"
              onClick={() => onRideSelect?.(latestRide.id)}
            >
              <div className="flex items-baseline justify-between">
                <p className="text-lg font-semibold text-text">
                  {latestRide.title || latestRide.sub_sport || latestRide.sport || 'Ride'}
                </p>
                <span className="text-sm text-text-muted">
                  {latestRide.isToday ? 'Today' : latestRide.date === yesterday ? 'Yesterday' : latestRide.date}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-3 mt-2 text-sm">
                <div>
                  <span className="text-text-muted text-xs block">Duration</span>
                  <span className="text-text">{fmtDuration(latestRide.duration_s)}</span>
                </div>
                <div>
                  <span className="text-text-muted text-xs block">TSS</span>
                  <span className="text-accent">{latestRide.tss?.toFixed(0) ?? '--'}</span>
                </div>
                <div>
                  <span className="text-text-muted text-xs block">Avg Power</span>
                  <span className="text-blue">{latestRide.avg_power ? `${latestRide.avg_power}w` : '--'}</span>
                </div>
                <div>
                  <span className="text-text-muted text-xs block">Distance</span>
                  <span className="text-text">{fmtDistance(latestRide.distance_m, units)}</span>
                </div>
              </div>
              {(latestRide.normalized_power || latestRide.avg_hr) && (
                <div className="grid grid-cols-4 gap-3 mt-1 text-sm">
                  <div>
                    <span className="text-text-muted text-xs block">NP</span>
                    <span className="text-text">{latestRide.normalized_power ? `${latestRide.normalized_power}w` : '--'}</span>
                  </div>
                  <div>
                    <span className="text-text-muted text-xs block">Avg HR</span>
                    <span className="text-red">{latestRide.avg_hr ? `${latestRide.avg_hr}bpm` : '--'}</span>
                  </div>
                  <div>
                    <span className="text-text-muted text-xs block">Elevation</span>
                    <span className="text-text">{latestRide.total_ascent ? `${latestRide.total_ascent}m` : '--'}</span>
                  </div>
                  <div>
                    <span className="text-text-muted text-xs block">IF</span>
                    <span className="text-text">{latestRide.intensity_factor?.toFixed(2) ?? '--'}</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-text-muted text-sm">No recent rides</p>
          )}
        </div>
      </div>

      {/* PMC + Volume Charts — side by side on desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

      {/* PMC Chart */}
      <div className="bg-surface rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold text-text mb-4">Performance Management Chart</h2>
        <div className="h-72">
          {pmc90.length > 0 ? (
            <Line data={chartData} options={chartOptions} />
          ) : (
            <p className="text-text-muted">No PMC data available.</p>
          )}
        </div>
      </div>

      {/* Weekly Volume Chart */}
      {(() => {
        // Build unified week list: last 12 actual + future planned (up to 3)
        const actual = weekly?.slice(-12) ?? []
        // Convert actual ISO week labels to Monday dates for matching
        const actualMondays = new Set(actual.map((w) => isoWeekToMonday(w.week)))

        // Future weeks not already in actual
        const futureWeeks: { label: string; monday: string; tss: number; hours: number }[] = []
        for (const mon of planMondays) {
          if (!actualMondays.has(mon)) {
            const plan = plannedByMonday.get(mon)
            if (plan && (plan.tss > 0 || plan.hours > 0)) {
              futureWeeks.push({ label: mon, monday: mon, ...plan })
            }
          }
        }

        // Use ISO week labels for display, Monday dates for matching
        const allLabels = [...actual.map((w) => w.week), ...futureWeeks.map((w) => w.label)]
        const allMondays = [...actual.map((w) => isoWeekToMonday(w.week)), ...futureWeeks.map((w) => w.monday)]
        const thisWeekIdx = allMondays.indexOf(thisMonday)

        // For each week: pick actual values or planned values, and set color accordingly
        const tssData: number[] = []
        const tssColors: string[] = []
        const tssBorders: string[] = []
        const hoursData: number[] = []
        const hoursColors: string[] = []
        const hoursBorders: string[] = []

        // Tooltip labels
        const tssLabels: string[] = []
        const hoursLabels: string[] = []

        for (const w of actual) {
          const monday = isoWeekToMonday(w.week)
          const plan = plannedByMonday.get(monday)
          const isThisWeek = monday === thisMonday

          tssData.push(w.tss ?? 0)
          tssColors.push('rgba(59, 130, 246, 0.7)')
          tssBorders.push('rgba(59, 130, 246, 1)')
          tssLabels.push(plan && isThisWeek ? `TSS: ${Math.round(w.tss ?? 0)} / ${plan.tss} planned` : `TSS: ${Math.round(w.tss ?? 0)}`)

          hoursData.push(w.duration_h ?? 0)
          hoursColors.push('rgba(34, 197, 94, 0.7)')
          hoursBorders.push('rgba(34, 197, 94, 1)')
          hoursLabels.push(plan && isThisWeek ? `Hours: ${(w.duration_h ?? 0).toFixed(1)}h / ${plan.hours}h planned` : `Hours: ${(w.duration_h ?? 0).toFixed(1)}h`)
        }

        for (const w of futureWeeks) {
          tssData.push(w.tss)
          tssColors.push('rgba(59, 130, 246, 0.25)')
          tssBorders.push('rgba(59, 130, 246, 0.5)')
          tssLabels.push(`Planned TSS: ${w.tss}`)

          hoursData.push(w.hours)
          hoursColors.push('rgba(34, 197, 94, 0.25)')
          hoursBorders.push('rgba(34, 197, 94, 0.5)')
          hoursLabels.push(`Planned Hours: ${w.hours}h`)
        }

        // This week's planned values for overlay behind actual
        const thisWeekPlan = thisMonday ? plannedByMonday.get(thisMonday) : undefined

        // Plugin to draw planned bars behind this week's actual bars
        const plannedOverlayPlugin = {
          id: 'plannedOverlay',
          beforeDatasetsDraw(chart: ChartJS) {
            if (thisWeekIdx < 0 || !thisWeekPlan) return
            const { ctx } = chart
            const tsMeta = chart.getDatasetMeta(0) // TSS dataset
            const hrMeta = chart.getDatasetMeta(1) // Hours dataset

            // Draw planned TSS bar
            if (thisWeekPlan.tss > 0 && tsMeta.data[thisWeekIdx]) {
              const bar = tsMeta.data[thisWeekIdx]
              const yScale = chart.scales.y
              const plannedY = yScale.getPixelForValue(thisWeekPlan.tss)
              const baseY = yScale.getPixelForValue(0)
              ctx.save()
              ctx.fillStyle = 'rgba(59, 130, 246, 0.15)'
              ctx.strokeStyle = 'rgba(59, 130, 246, 0.4)'
              ctx.lineWidth = 1
              ctx.setLineDash([4, 4])
              const x = (bar as any).x - (bar as any).width / 2
              const w = (bar as any).width
              ctx.fillRect(x, plannedY, w, baseY - plannedY)
              ctx.strokeRect(x, plannedY, w, baseY - plannedY)
              ctx.restore()
            }

            // Draw planned Hours bar
            if (thisWeekPlan.hours > 0 && hrMeta.data[thisWeekIdx]) {
              const bar = hrMeta.data[thisWeekIdx]
              const yScale = chart.scales.y1
              const plannedY = yScale.getPixelForValue(thisWeekPlan.hours)
              const baseY = yScale.getPixelForValue(0)
              ctx.save()
              ctx.fillStyle = 'rgba(34, 197, 94, 0.15)'
              ctx.strokeStyle = 'rgba(34, 197, 94, 0.4)'
              ctx.lineWidth = 1
              ctx.setLineDash([4, 4])
              const x = (bar as any).x - (bar as any).width / 2
              const w = (bar as any).width
              ctx.fillRect(x, plannedY, w, baseY - plannedY)
              ctx.strokeRect(x, plannedY, w, baseY - plannedY)
              ctx.restore()
            }
          },
        }

        return (
          <div className="bg-surface rounded-lg border border-border p-4">
            <h2 className="text-lg font-semibold text-text mb-4">Weekly Volume</h2>
            <div className="h-72">
              {allLabels.length > 0 ? (
                <Bar
                  plugins={[plannedOverlayPlugin]}
                  data={{
                    labels: allLabels,
                    datasets: [
                      {
                        label: 'TSS',
                        data: tssData,
                        backgroundColor: tssColors,
                        borderColor: tssBorders,
                        borderWidth: 1,
                        yAxisID: 'y',
                      },
                      {
                        label: 'Hours',
                        data: hoursData,
                        backgroundColor: hoursColors,
                        borderColor: hoursBorders,
                        borderWidth: 1,
                        yAxisID: 'y1',
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                      legend: { labels: { color: cc.legendColor } },
                      tooltip: {
                        backgroundColor: cc.tooltipBg,
                        titleColor: cc.tooltipTitle,
                        bodyColor: cc.tooltipBody,
                        borderColor: cc.tooltipBorder,
                        borderWidth: 1,
                        callbacks: {
                          title: (items) => {
                            const idx = items[0]?.dataIndex ?? -1
                            const label = items[0]?.label ?? ''
                            const monday = idx >= 0 && idx < allMondays.length ? allMondays[idx] : ''
                            if (!monday) return label
                            const mon = new Date(monday + 'T00:00:00')
                            const sun = new Date(mon)
                            sun.setDate(mon.getDate() + 6)
                            const fmt = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                            const suffix = idx === thisWeekIdx ? '  (this week)' : ''
                            return `${label}  (${fmt(mon)} – ${fmt(sun)})${suffix}`
                          },
                          label: (ctx) => {
                            const idx = ctx.dataIndex
                            return ctx.dataset.label === 'TSS' ? tssLabels[idx] : hoursLabels[idx]
                          },
                        },
                      },
                    },
                    scales: {
                      x: {
                        ticks: {
                          color: (ctx) => ctx.index === thisWeekIdx ? '#60a5fa' : cc.tickColor,
                          font: (ctx) => ctx.index === thisWeekIdx ? { weight: 'bold' as const } : {},
                        },
                        grid: { color: cc.gridColor },
                      },
                      y: {
                        type: 'linear',
                        position: 'left',
                        title: { display: true, text: 'TSS', color: cc.tickColor },
                        ticks: { color: cc.tickColor },
                        grid: { color: cc.gridColor },
                      },
                      y1: {
                        type: 'linear',
                        position: 'right',
                        title: { display: true, text: 'Hours', color: cc.tickColor },
                        ticks: { color: cc.tickColor },
                        grid: { drawOnChartArea: false },
                      },
                    },
                  }}
                />
              ) : (
                <p className="text-text-muted">No weekly data available.</p>
              )}
            </div>
          </div>
        )
      })()}

      </div>{/* end PMC + Volume grid */}

      {/* Recent Rides */}
      <div className="bg-surface rounded-lg border border-border p-4">
        <h2 className="text-lg font-semibold text-text mb-4">Recent Rides</h2>
        {rides && rides.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-muted border-b border-border">
                  <th className="text-left py-2 pr-4">Date</th>
                  <th className="text-left py-2 pr-4">Sport</th>
                  <th className="text-right py-2 pr-4">Duration</th>
                  <th className="text-right py-2 pr-4">Distance</th>
                  <th className="text-right py-2 pr-4">TSS</th>
                  <th className="text-right py-2">Avg Power</th>
                </tr>
              </thead>
              <tbody>
                {rides.map((ride) => (
                  <tr
                    key={ride.id}
                    onClick={() => onRideSelect?.(ride.id)}
                    className="border-b border-border/50 text-text hover:bg-surface2 transition-colors cursor-pointer"
                  >
                    <td className="py-2 pr-4">{ride.date}</td>
                    <td className="py-2 pr-4 text-text-muted">{ride.sub_sport || ride.sport || '--'}</td>
                    <td className="py-2 pr-4 text-right">{fmtDuration(ride.duration_s)}</td>
                    <td className="py-2 pr-4 text-right">{fmtDistance(ride.distance_m, units)}</td>
                    <td className="py-2 pr-4 text-right text-accent">{ride.tss?.toFixed(0) ?? '--'}</td>
                    <td className="py-2 text-right text-blue">{ride.avg_power ? `${ride.avg_power}w` : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-text-muted">No rides found.</p>
        )}
      </div>
    </div>
  )
}
