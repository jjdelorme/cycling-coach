import { useState, useMemo } from 'react'
import { usePowerCurve, useEfficiency, useZones, useFTPHistory, useMacroPlan, useWeeklyOverview } from '../hooks/useApi'
import { useChartColors } from '../lib/theme'
import { fmtWeight } from '../lib/format'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line, Bar, Doughnut } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler,
)

import type { DateRange } from '../lib/api'

type Tab = 'power-curve' | 'efficiency' | 'zones' | 'ftp-history'

const TABS: { key: Tab; label: string }[] = [
  { key: 'power-curve', label: 'Power Curve' },
  { key: 'efficiency', label: 'Efficiency' },
  { key: 'zones', label: 'Zones' },
  { key: 'ftp-history', label: 'FTP History' },
]

type RangeKey = '1w' | '3m' | '6m' | '1y' | 'all'
const RANGE_OPTIONS: { key: RangeKey; label: string }[] = [
  { key: '1w', label: 'This Week' },
  { key: '3m', label: '3 Months' },
  { key: '6m', label: '6 Months' },
  { key: '1y', label: '1 Year' },
  { key: 'all', label: 'All Time' },
]

function rangeToDates(key: RangeKey): DateRange {
  if (key === 'all') return {}
  const now = new Date()
  const start = new Date(now)
  if (key === '1w') start.setDate(now.getDate() - 7)
  else if (key === '3m') start.setMonth(now.getMonth() - 3)
  else if (key === '6m') start.setMonth(now.getMonth() - 6)
  else if (key === '1y') start.setFullYear(now.getFullYear() - 1)
  const y = start.getFullYear()
  const m = String(start.getMonth() + 1).padStart(2, '0')
  const d = String(start.getDate()).padStart(2, '0')
  return { start_date: `${y}-${m}-${d}` }
}

const ZONE_COLORS: Record<string, string> = {
  z0: '#aaaaaa',
  z1: '#7ec8e3',
  z2: '#00d4aa',
  z3: '#f5c518',
  z4: '#e8913a',
  z5: '#e94560',
  z6: '#9b59b6',
  Z1: '#7ec8e3',
  Z2: '#00d4aa',
  Z3: '#f5c518',
  Z4: '#e8913a',
  Z5: '#e94560',
  Z6: '#9b59b6',
}

const PHASE_COLORS: Record<string, string> = {
  'Base Rebuild': '#0f3460',
  'Build 1': '#e94560',
  'Build 2': '#f5c518',
  'Peak': '#00d4aa',
  'Taper': '#9b59b6',
}

type OverviewMetric = 'hours' | 'tss'

function TrainingPlanOverview() {
  const { data: phases, isLoading: phasesLoading } = useMacroPlan()
  const { data: overview, isLoading: overviewLoading } = useWeeklyOverview()
  const cc = useChartColors()
  const [metric, setMetric] = useState<OverviewMetric>('hours')

  const today = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])
  const todayStr = useMemo(() => today.toISOString().slice(0, 10), [today])

  // Chart data built from weekly-overview endpoint
  const chartData = useMemo(() => {
    if (!overview || overview.length === 0) return null
    const isHours = metric === 'hours'
    return {
      labels: overview.map((w) => w.week_start.slice(5)),
      datasets: [
        {
          label: isHours ? 'Target High' : 'Target TSS High',
          data: overview.map((w) => isHours ? w.target_hours_high : w.target_tss_high),
          borderColor: 'rgba(255, 255, 255, 0.15)',
          backgroundColor: 'rgba(255, 255, 255, 0.06)',
          borderWidth: 1,
          borderDash: [4, 4],
          fill: '1',
          pointRadius: 0,
          tension: 0,
        },
        {
          label: isHours ? 'Target Low' : 'Target TSS Low',
          data: overview.map((w) => isHours ? w.target_hours_low : w.target_tss_low),
          borderColor: 'rgba(255, 255, 255, 0.15)',
          backgroundColor: 'transparent',
          borderWidth: 1,
          borderDash: [4, 4],
          fill: false,
          pointRadius: 0,
          tension: 0,
        },
        {
          label: isHours ? 'Planned Hours' : 'Planned TSS',
          data: overview.map((w) => isHours ? (w.planned_hours || null) : (w.planned_tss || null)),
          borderColor: '#3b82f6',
          backgroundColor: 'transparent',
          borderWidth: 2,
          borderDash: [6, 3],
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.3,
          fill: false,
        },
        {
          label: isHours ? 'Actual Hours' : 'Actual TSS',
          data: overview.map((w) => {
            const val = isHours ? w.actual_hours : w.actual_tss
            return val > 0 ? val : null
          }),
          borderColor: '#22c55e',
          backgroundColor: 'rgba(34, 197, 94, 0.2)',
          fill: true,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: overview.map((w) => {
            const actual = isHours ? w.actual_hours : w.actual_tss
            const low = isHours ? w.target_hours_low : w.target_tss_low
            const high = isHours ? w.target_hours_high : w.target_tss_high
            if (actual === 0) return 'transparent'
            if (low != null && actual < low) return '#ef4444'
            if (high != null && actual > high) return '#f5c518'
            return '#22c55e'
          }),
          tension: 0.3,
          borderWidth: 2,
          spanGaps: false,
        },
      ],
    }
  }, [overview, metric])

  const todayIdx = useMemo(() => {
    if (!overview) return -1
    return overview.findIndex((w) => {
      const wDate = new Date(w.week_start)
      const diff = (today.getTime() - wDate.getTime()) / 86400000
      return diff >= 0 && diff < 7
    })
  }, [overview, today])

  const todayLinePlugin = useMemo(() => ({
    id: 'todayLine',
    afterDraw(chart: ChartJS) {
      if (todayIdx < 0) return
      const meta = chart.getDatasetMeta(0)
      if (!meta.data[todayIdx]) return
      const x = meta.data[todayIdx].x
      const { ctx, chartArea } = chart
      ctx.save()
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)'
      ctx.lineWidth = 1.5
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      ctx.moveTo(x, chartArea.top)
      ctx.lineTo(x, chartArea.bottom)
      ctx.stroke()
      ctx.restore()
    },
  }), [todayIdx])

  // Summary stats
  const stats = useMemo(() => {
    if (!overview) return { onTarget: 0, under: 0, over: 0, avg: 0 }
    const past = overview.filter((w) => w.week_start < todayStr && w.actual_hours > 0 && w.target_hours_low != null)
    const isHours = metric === 'hours'
    const onTarget = past.filter((w) => {
      const a = isHours ? w.actual_hours : w.actual_tss
      const lo = (isHours ? w.target_hours_low : w.target_tss_low) ?? 0
      const hi = (isHours ? w.target_hours_high : w.target_tss_high) ?? Infinity
      return a >= lo && a <= hi
    }).length
    const under = past.filter((w) => {
      const a = isHours ? w.actual_hours : w.actual_tss
      const lo = (isHours ? w.target_hours_low : w.target_tss_low) ?? 0
      return a < lo
    }).length
    const over = past.filter((w) => {
      const a = isHours ? w.actual_hours : w.actual_tss
      const hi = (isHours ? w.target_hours_high : w.target_tss_high) ?? Infinity
      return a > hi
    }).length
    const avg = past.length > 0
      ? past.reduce((s, w) => s + (isHours ? w.actual_hours : w.actual_tss), 0) / past.length
      : 0
    return { onTarget, under, over, avg }
  }, [overview, todayStr, metric])

  // Early returns AFTER all hooks
  if (phasesLoading || overviewLoading) return <p className="text-text-muted">Loading training plan...</p>
  if (!phases || phases.length === 0) return null

  const allStart = new Date(phases[0].start_date).getTime()
  const allEnd = new Date(phases[phases.length - 1].end_date).getTime()
  const totalDays = (allEnd - allStart) / 86400000
  const todayPct = ((today.getTime() - allStart) / 86400000 / totalDays) * 100
  const currentPhase = phases.find(
    (p) => p.start_date <= todayStr && p.end_date >= todayStr,
  )

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: cc.tooltipBg,
        titleColor: cc.tooltipTitle,
        bodyColor: cc.tooltipBody,
        borderColor: cc.tooltipBorder,
        borderWidth: 1,
        callbacks: {
          title: (items: { dataIndex: number }[]) => {
            const w = overview?.[items[0]?.dataIndex]
            if (!w) return ''
            return `Week of ${w.week_start}${w.phase ? ` (${w.phase})` : ''}`
          },
          label: (ctx: { datasetIndex: number; dataIndex: number; parsed: { y: number | null } }) => {
            const w = overview?.[ctx.dataIndex]
            if (!w) return ''
            const isHours = metric === 'hours'
            const unit = isHours ? 'h' : ''
            if (ctx.datasetIndex === 0 && w.target_hours_low != null) {
              const lo = isHours ? w.target_hours_low : w.target_tss_low
              const hi = isHours ? w.target_hours_high : w.target_tss_high
              return `Target: ${lo}-${hi}${unit}`
            }
            if (ctx.datasetIndex === 2) return `Planned: ${ctx.parsed.y ?? 0}${unit}`
            if (ctx.datasetIndex === 3) return `Actual: ${ctx.parsed.y ?? 0}${unit}`
            return ''
          },
        },
        filter: (item: { datasetIndex: number }) => item.datasetIndex !== 1,
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: cc.tickColor, maxTicksLimit: 14, font: { size: 10 } },
      },
      y: {
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: cc.tickColor },
        title: {
          display: true,
          text: metric === 'hours' ? 'Hours/wk' : 'TSS/wk',
          color: cc.tickColor,
          font: { size: 11 },
        },
        min: 0,
      },
    },
  }

  return (
    <div className="bg-surface rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-text">Training Plan</h2>
        <div className="flex items-center gap-3">
          {currentPhase && (
            <span className="text-sm text-text-muted">
              Current:{' '}
              <span className="text-text font-medium">{currentPhase.name}</span>
              {currentPhase.focus && <span className="ml-2 text-xs">— {currentPhase.focus}</span>}
            </span>
          )}
          {/* Hours / TSS toggle */}
          <div className="flex gap-1 ml-2">
            {(['hours', 'tss'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                className={`px-2 py-0.5 text-xs font-medium rounded transition-colors ${
                  metric === m
                    ? 'bg-accent text-white'
                    : 'bg-surface2 text-text-muted hover:text-text border border-border'
                }`}
              >
                {m === 'hours' ? 'Hours' : 'TSS'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Gantt bar */}
      <div className="relative">
        <div className="relative h-10 rounded overflow-hidden flex">
          {phases.map((p) => {
            const dur = (new Date(p.end_date).getTime() - new Date(p.start_date).getTime()) / 86400000
            const widthPct = (dur / totalDays) * 100
            const color = PHASE_COLORS[p.name] || '#666'
            return (
              <div
                key={p.id}
                className="h-full flex items-center justify-center text-xs font-medium px-1 overflow-hidden whitespace-nowrap"
                style={{
                  width: `${widthPct}%`,
                  backgroundColor: color,
                  color: p.name === 'Build 2' ? '#1a1a2e' : '#fff',
                }}
                title={`${p.name}: ${p.start_date} to ${p.end_date}${p.hours_per_week_low ? ` (${p.hours_per_week_low}-${p.hours_per_week_high}h/wk)` : ''}`}
              >
                {widthPct > 10 ? p.name : ''}
              </div>
            )
          })}
        </div>
        {todayPct >= 0 && todayPct <= 100 && (
          <div
            className="absolute top-0 h-10 w-0.5 bg-white"
            style={{ left: `${todayPct}%` }}
            title="Today"
          />
        )}
        {/* Date labels */}
        <div className="flex justify-between mt-1 text-xs text-text-muted">
          {phases.map((p) => (
            <span key={p.id}>{p.start_date.slice(5)}</span>
          ))}
          <span>{phases[phases.length - 1].end_date.slice(5)}</span>
        </div>
      </div>

      {/* Volume / TSS chart */}
      <div className="h-52 mt-2">
        {chartData ? (
          <Line data={chartData} options={chartOptions} plugins={[todayLinePlugin]} />
        ) : (
          <p className="text-text-muted text-sm">No data yet</p>
        )}
      </div>

      {/* Legend + stats row */}
      <div className="flex items-center justify-between mt-2 text-xs text-text-muted flex-wrap gap-2">
        <div className="flex gap-3">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-white/20 border-t border-dashed border-white/30" /> Target
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5" style={{ borderTop: '2px dashed #3b82f6' }} /> Planned
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-green-500" /> Actual
          </span>
        </div>
        <div className="flex gap-3">
          <span>Avg: <span className="text-text font-medium">{metric === 'hours' ? `${stats.avg.toFixed(1)}h` : Math.round(stats.avg)}</span></span>
          <span className="text-green-400">{stats.onTarget} on target</span>
          <span className="text-red-400">{stats.under} under</span>
          <span className="text-yellow-400">{stats.over} over</span>
        </div>
      </div>
    </div>
  )
}

function PowerCurveChart({ dateRange }: { dateRange: DateRange }) {
  const { data, isLoading, error } = usePowerCurve(dateRange)
  const cc = useChartColors()

  if (isLoading) return <p className="text-text-muted">Loading power curve...</p>
  if (error) return <p className="text-red-400">Error loading power curve.</p>
  if (!data || data.length === 0)
    return <p className="text-text-muted">No power curve data available.</p>

  const sorted = [...data].sort((a, b) => a.duration_s - b.duration_s)

  const fmtDurationLabel = (s: number): string => {
    if (s < 60) return `${s}s`
    if (s < 3600) return `${Math.round(s / 60)}min`
    return `${(s / 3600).toFixed(1)}h`
  }

  const labels = sorted.map((d) => fmtDurationLabel(d.duration_s))
  const powers = sorted.map((d) => d.power)
  const dates = sorted.map((d) => d.date)

  const chartData = {
    labels,
    datasets: [
      {
        label: 'Best Power (W)',
        data: powers,
        borderColor: '#f5c518',
        backgroundColor: 'rgba(245, 197, 24, 0.1)',
        fill: true,
        tension: 0.3,
        pointBackgroundColor: '#f5c518',
        pointRadius: 4,
        pointHoverRadius: 6,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          afterLabel: (ctx: { dataIndex: number }) => `Date: ${dates[ctx.dataIndex]}`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: cc.gridColor },
        ticks: { color: cc.tickColor },
      },
      y: {
        grid: { color: cc.gridColor },
        ticks: { color: cc.tickColor },
        title: { display: true, text: 'Power (W)', color: cc.tickColor },
      },
    },
  }

  return (
    <div className="h-96">
      <Line data={chartData} options={options} />
    </div>
  )
}

function EfficiencyChart({ dateRange }: { dateRange: DateRange }) {
  const { data, isLoading, error } = useEfficiency(dateRange)
  const cc = useChartColors()

  if (isLoading) return <p className="text-text-muted">Loading efficiency...</p>
  if (error) return <p className="text-red-400">Error loading efficiency.</p>
  if (!data || data.length === 0)
    return <p className="text-text-muted">No efficiency data available.</p>

  const chartData = {
    labels: data.map((d) => d.date),
    datasets: [
      {
        label: 'Efficiency (W/bpm)',
        data: data.map((d) => d.ef),
        borderColor: '#00d4aa',
        backgroundColor: 'rgba(0, 212, 170, 0.1)',
        fill: true,
        tension: 0.3,
        pointBackgroundColor: '#00d4aa',
        pointRadius: 2,
        pointHoverRadius: 5,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          afterLabel: (ctx: { dataIndex: number }) => {
            const pt = data[ctx.dataIndex]
            const lines: string[] = []
            if (pt.np != null) lines.push(`NP: ${pt.np}W`)
            if (pt.avg_hr != null) lines.push(`Avg HR: ${pt.avg_hr} bpm`)
            return lines.join('\n')
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: cc.gridColor },
        ticks: { color: cc.tickColor, maxTicksLimit: 12 },
      },
      y: {
        grid: { color: cc.gridColor },
        ticks: { color: cc.tickColor },
        title: { display: true, text: 'Power / HR', color: cc.tickColor },
      },
    },
  }

  return (
    <div className="h-96">
      <Line data={chartData} options={options} />
    </div>
  )
}

function ZonesChart({ dateRange }: { dateRange: DateRange }) {
  const { data, isLoading, error } = useZones(dateRange)
  const cc = useChartColors()

  if (isLoading) return <p className="text-text-muted">Loading zones...</p>
  if (error) return <p className="text-red-400">Error loading zones.</p>
  if (!data || data.length === 0)
    return <p className="text-text-muted">No zone data available.</p>

  const colors = data.map((d) => ZONE_COLORS[d.zone] || '#888')

  const chartData = {
    labels: data.map((d) => d.zone),
    datasets: [
      {
        data: data.map((d) => d.percentage),
        backgroundColor: colors,
        borderColor: 'transparent',
        hoverOffset: 8,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'right' as const,
        labels: { color: cc.tickColor, padding: 16 },
      },
      tooltip: {
        callbacks: {
          label: (ctx: { dataIndex: number }) => {
            const z = data[ctx.dataIndex]
            return `${z.zone}: ${z.percentage.toFixed(1)}% (${z.hours.toFixed(1)}h)`
          },
        },
      },
    },
  }

  const totalHours = data.reduce((sum, z) => sum + z.hours, 0)

  return (
    <div>
      <div className="h-80 flex items-center justify-center">
        <Doughnut data={chartData} options={options} />
      </div>
      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text-muted">
              <th className="text-left py-2 px-3">Zone</th>
              <th className="text-right py-2 px-3">Hours</th>
              <th className="text-right py-2 px-3">Percentage</th>
            </tr>
          </thead>
          <tbody>
            {data.map((z) => (
              <tr key={z.zone} className="border-b border-border/50">
                <td className="py-2 px-3 flex items-center gap-2">
                  <span
                    className="inline-block w-3 h-3 rounded-full"
                    style={{ backgroundColor: ZONE_COLORS[z.zone] || '#888' }}
                  />
                  {z.zone}
                </td>
                <td className="text-right py-2 px-3">{z.hours.toFixed(1)}h</td>
                <td className="text-right py-2 px-3">{z.percentage.toFixed(1)}%</td>
              </tr>
            ))}
            <tr className="font-semibold text-text">
              <td className="py-2 px-3">Total</td>
              <td className="text-right py-2 px-3">{totalHours.toFixed(1)}h</td>
              <td className="text-right py-2 px-3">100%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FTPHistoryChart({ dateRange }: { dateRange: DateRange }) {
  const { data, isLoading, error } = useFTPHistory(dateRange)
  const cc = useChartColors()

  if (isLoading) return <p className="text-text-muted">Loading FTP history...</p>
  if (error) return <p className="text-red-400">Error loading FTP history.</p>
  if (!data || data.length === 0)
    return <p className="text-text-muted">No FTP history data available.</p>

  const hasWkg = data.some((d) => d.w_per_kg != null)

  const chartData = {
    labels: data.map((d) => d.month),
    datasets: [
      {
        type: 'bar' as const,
        label: 'FTP (W)',
        data: data.map((d) => d.ftp),
        backgroundColor: 'rgba(245, 197, 24, 0.7)',
        borderColor: '#f5c518',
        borderWidth: 1,
        yAxisID: 'y',
      },
      ...(hasWkg
        ? [
            {
              type: 'line' as const,
              label: 'W/kg',
              data: data.map((d) => d.w_per_kg ?? null),
              borderColor: '#00d4aa',
              backgroundColor: 'transparent',
              pointBackgroundColor: '#00d4aa',
              pointRadius: 4,
              pointHoverRadius: 6,
              tension: 0.3,
              yAxisID: 'y1',
            },
          ]
        : []),
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: cc.tickColor },
      },
      tooltip: {
        callbacks: {
          afterLabel: (ctx: { datasetIndex: number; dataIndex: number }) => {
            if (ctx.datasetIndex === 0) {
              const pt = data[ctx.dataIndex]
              const lines: string[] = []
              if (pt.weight_kg != null) lines.push(`Weight: ${fmtWeight(pt.weight_kg)}`)
              if (pt.w_per_kg != null) lines.push(`W/kg: ${pt.w_per_kg.toFixed(2)}`)
              return lines.join('\n')
            }
            return ''
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: cc.gridColor },
        ticks: { color: cc.tickColor },
      },
      y: {
        position: 'left' as const,
        grid: { color: cc.gridColor },
        ticks: { color: cc.tickColor },
        title: { display: true, text: 'FTP (W)', color: cc.tickColor },
      },
      ...(hasWkg
        ? {
            y1: {
              position: 'right' as const,
              grid: { drawOnChartArea: false },
              ticks: { color: '#00d4aa' },
              title: { display: true, text: 'W/kg', color: '#00d4aa' },
            },
          }
        : {}),
    },
  }

  return (
    <div className="h-96">
      {/* @ts-expect-error mixed chart types */}
      <Bar data={chartData} options={options} />
    </div>
  )
}

export default function Analysis() {
  const [activeTab, setActiveTab] = useState<Tab>('power-curve')
  const [range, setRange] = useState<RangeKey>('3m')
  const dateRange = useMemo(() => rangeToDates(range), [range])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-text">Analysis</h1>

        {/* Time range selector */}
        <div className="flex gap-1">
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setRange(opt.key)}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                range === opt.key
                  ? 'bg-accent text-white'
                  : 'bg-surface2 text-text-muted hover:text-text border border-border'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <TrainingPlanOverview />

      {/* Tab buttons */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
              activeTab === tab.key
                ? 'bg-surface2 text-text border-b-2 border-accent'
                : 'text-text-muted hover:text-text'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-surface rounded-lg p-6">
        {activeTab === 'power-curve' && <PowerCurveChart dateRange={dateRange} />}
        {activeTab === 'efficiency' && <EfficiencyChart dateRange={dateRange} />}
        {activeTab === 'zones' && <ZonesChart dateRange={dateRange} />}
        {activeTab === 'ftp-history' && <FTPHistoryChart dateRange={dateRange} />}
      </div>
    </div>
  )
}
