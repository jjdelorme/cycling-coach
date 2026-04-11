import { useState, useMemo } from 'react'
import {
  usePowerCurve,
  useEfficiency,
  useZones,
  useFTPHistory,
  useMacroPlan,
  useWeeklyOverview,
  useAthleteSettings,
  useWithingsStatus,
  useWeightHistory,
} from '../hooks/useApi'
import { useChartColors } from '../lib/theme'
import { fmtWeight } from '../lib/format'
import { useUnits } from '../lib/units'
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
import {
  Activity,
  Zap,
  BarChart3,
  History,
  Calendar,
  TrendingUp,
  Target,
  Trophy,
  ArrowUpRight,
  ArrowDownRight,
  Scale,
} from 'lucide-react'

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

type Tab = 'power-curve' | 'efficiency' | 'zones' | 'ftp-history' | 'weight'

const TABS: { key: Tab; label: string; icon: any }[] = [
  { key: 'power-curve', label: 'Power Curve', icon: Activity },
  { key: 'efficiency', label: 'Efficiency', icon: Zap },
  { key: 'zones', label: 'Zones', icon: BarChart3 },
  { key: 'ftp-history', label: 'FTP History', icon: History },
  { key: 'weight', label: 'Weight', icon: Scale },
]

type RangeKey = '1w' | '3m' | '6m' | '1y' | 'all'
const RANGE_OPTIONS: { key: RangeKey; label: string }[] = [
  { key: '1w', label: '1W' },
  { key: '3m', label: '3M' },
  { key: '6m', label: '6M' },
  { key: '1y', label: '1Y' },
  { key: 'all', label: 'ALL' },
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
  z0: '#94a3b8',
  z1: '#7ec8e3',
  z2: '#00d4aa',
  z3: '#f5c518',
  z4: '#e8913a',
  z5: '#e94560',
  z6: '#9b59b6',
}

const PHASE_COLORS: Record<string, string> = {
  'Base Rebuild': '#334155',
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

  const todayIdx = useMemo(() => {
    if (!overview) return -1
    return overview.findIndex((w) => {
      const wDate = new Date(w.week_start)
      const diff = (today.getTime() - wDate.getTime()) / 86400000
      return diff >= 0 && diff < 7
    })
  }, [overview, today])

  const chartData = useMemo(() => {
    if (!overview || overview.length === 0) return null
    const isHours = metric === 'hours'
    return {
      labels: overview.map((w) => w.week_start.slice(5)),
      datasets: [
        {
          label: isHours ? 'Target High' : 'Target TSS High',
          data: overview.map((w) => isHours ? w.target_hours_high : w.target_tss_high),
          borderColor: 'rgba(148, 163, 184, 0.2)',
          backgroundColor: 'rgba(148, 163, 184, 0.05)',
          borderWidth: 1,
          borderDash: [4, 4],
          fill: '1',
          pointRadius: 0,
          tension: 0,
        },
        {
          label: isHours ? 'Target Low' : 'Target TSS Low',
          data: overview.map((w) => isHours ? w.target_hours_low : w.target_tss_low),
          borderColor: 'rgba(148, 163, 184, 0.2)',
          backgroundColor: 'transparent',
          borderWidth: 1,
          borderDash: [4, 4],
          fill: false,
          pointRadius: 0,
          tension: 0,
        },
        {
          label: isHours ? 'Planned' : 'Planned TSS',
          data: overview.map((w) => isHours ? (w.planned_hours || null) : (w.planned_tss || null)),
          borderColor: '#4a9eff',
          backgroundColor: 'transparent',
          borderWidth: 2,
          borderDash: [6, 3],
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: isHours ? 'Actual' : 'Actual TSS',
          data: overview.map((w) => {
            const val = isHours ? w.actual_hours : w.actual_tss
            return val > 0 ? val : null
          }),
          borderColor: '#00d4aa',
          backgroundColor: 'rgba(0, 212, 170, 0.1)',
          fill: true,
          segment: {
            borderColor: (ctx: any) => ctx.p1DataIndex >= todayIdx && todayIdx !== -1 ? 'rgba(0, 212, 170, 0.4)' : undefined,
            borderDash: (ctx: any) => ctx.p1DataIndex >= todayIdx && todayIdx !== -1 ? [5, 5] : undefined,
          },
          pointStyle: (ctx: any) => ctx.dataIndex === todayIdx ? 'rectRot' : 'circle',
          pointRadius: (ctx: any) => {
            if (ctx.dataIndex === todayIdx) return 6
            return (ctx.raw as number) > 0 ? 3 : 0
          },
          pointHoverRadius: (ctx: any) => ctx.dataIndex === todayIdx ? 8 : 6,
          pointBackgroundColor: overview.map((w, idx) => {
            if (idx === todayIdx) return '#00d4aa'
            const actual = isHours ? w.actual_hours : w.actual_tss
            const low = isHours ? w.target_hours_low : w.target_tss_low
            const high = isHours ? w.target_hours_high : w.target_tss_high
            if (actual === 0) return 'transparent'
            if (low != null && actual < low) return '#e94560'
            if (high != null && actual > high) return '#f5c518'
            return '#00d4aa'
          }),
          tension: 0.3,
          borderWidth: 2,
          spanGaps: false,
        },
      ],
    }
  }, [overview, metric, todayIdx])

  const todayLinePlugin = useMemo(() => ({
    id: 'todayLine',
    afterDraw(chart: ChartJS) {
      if (todayIdx < 0) return
      const meta = chart.getDatasetMeta(0)
      if (!meta.data[todayIdx]) return
      const x = meta.data[todayIdx].x
      const { ctx, chartArea } = chart
      ctx.save()
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.5)'
      ctx.lineWidth = 1.5
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      ctx.moveTo(x, chartArea.top)
      ctx.lineTo(x, chartArea.bottom)
      ctx.stroke()

      // Add "TODAY" label
      ctx.fillStyle = 'rgba(148, 163, 184, 0.8)'
      ctx.font = 'bold 9px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('TODAY', x, chartArea.top - 5)

      ctx.restore()
    },
  }), [todayIdx])

  const stats = useMemo(() => {
    if (!overview) return { onTarget: 0, under: 0, over: 0, avg: 0, total: 0 }
    const past = overview.filter((w) => w.week_start <= todayStr && (w.actual_hours > 0 || w.actual_tss > 0) && w.target_hours_low != null)
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
    return { onTarget, under, over, avg, total: past.length }
  }, [overview, todayStr, metric])

  if (phasesLoading || overviewLoading) return <div className="p-6 text-text-muted animate-pulse">Loading training plan...</div>
  if (!phases || phases.length === 0) return null

  const allStart = new Date(phases[0].start_date).getTime()
  const allEnd = new Date(phases[phases.length - 1].end_date).getTime()
  const totalDays = (allEnd - allStart) / 86400000 + 1
  const todayPct = ((today.getTime() - allStart) / 86400000 / totalDays) * 100
  const currentPhase = phases.find(
    (p) => p.start_date <= todayStr && p.end_date >= todayStr,
  )

  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-border bg-surface-low flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h2 className="text-sm font-bold text-text uppercase tracking-wider flex items-center gap-2">
          <Calendar size={16} className="text-accent" />
          Season Macro-Plan
        </h2>
        
        <div className="flex items-center gap-4">
          {currentPhase && (
            <div className="flex items-center gap-2 px-3 py-1 bg-accent/10 rounded-full border border-accent/20">
              <Target size={12} className="text-accent" />
              <span className="text-[10px] font-bold text-accent uppercase tracking-wider">
                {currentPhase.name} {currentPhase.focus && `— ${currentPhase.focus}`}
              </span>
            </div>
          )}
          <div className="flex bg-surface rounded-lg p-0.5 border border-border shadow-inner">
            {(['hours', 'tss'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                className={`px-3 py-1 text-[10px] font-bold uppercase tracking-widest rounded transition-all ${
                  metric === m ? 'bg-accent text-white shadow-sm' : 'text-text-muted hover:text-text'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="p-6 space-y-8">
        {/* Gantt / Phase Bar */}
        <div className="relative">
          <div className="relative h-12 rounded-lg flex overflow-hidden shadow-inner border border-border/50 bg-bg">
            {phases.map((p) => {
              const dur = (new Date(p.end_date).getTime() - new Date(p.start_date).getTime()) / 86400000 + 1
              const widthPct = (dur / totalDays) * 100
              const color = PHASE_COLORS[p.name] || '#64748b'
              return (
                <div
                  key={p.id}
                  className="group relative h-full flex items-center justify-center text-[10px] font-bold uppercase tracking-tighter px-1 transition-all hover:brightness-110"
                  style={{ width: `${widthPct}%`, backgroundColor: color, color: '#fff' }}
                  title={`${p.name}: ${p.start_date} to ${p.end_date}`}
                >
                  {widthPct > 8 ? p.name.split(' ')[0] : ''}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 bg-surface-high text-text text-xs rounded-lg shadow-xl border border-border whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20">
                    <p className="font-bold">{p.name}</p>
                    <p className="text-[10px] text-text-muted">{p.start_date} to {p.end_date}</p>
                    {p.hours_per_week_low && <p className="text-[10px] text-accent mt-1">{p.hours_per_week_low}-{p.hours_per_week_high}h/wk</p>}
                  </div>
                </div>
              )
            })}
          </div>
          {todayPct >= 0 && todayPct <= 100 && (
            <div className="absolute top-0 h-full w-0.5 bg-white shadow-[0_0_8px_rgba(255,255,255,0.8)] z-10" style={{ left: `${todayPct}%` }} />
          )}
          <div className="relative mt-2 text-[10px] font-bold text-text-muted uppercase tracking-widest h-4">
            <span className="absolute left-0">{phases[0].start_date.slice(5)}</span>
            <span className="absolute right-0">{phases[phases.length - 1].end_date.slice(5)}</span>
          </div>
        </div>

        {/* Plan Chart */}
        <div className="h-64">
          {chartData ? (
            <Line 
              data={chartData} 
              plugins={[todayLinePlugin]}
              options={{
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
                      title: (items) => {
                        const w = overview?.[items[0]?.dataIndex]
                        return w ? `Week of ${w.week_start}${w.phase ? ` (${w.phase})` : ''}` : ''
                      },
                      label: (ctx) => {
                        const w = overview?.[ctx.dataIndex]
                        if (!w || ctx.datasetIndex === 1) return ''
                        const isHours = metric === 'hours'
                        const unit = isHours ? 'h' : ''
                        if (ctx.datasetIndex === 0) return `Target Range: ${isHours ? w.target_hours_low : w.target_tss_low}-${isHours ? w.target_hours_high : w.target_tss_high}${unit}`
                        return `${ctx.dataset.label}: ${ctx.parsed.y ?? 0}${unit}`
                      }
                    },
                    filter: (item) => item.datasetIndex !== 1,
                  }
                },
                scales: {
                  x: { grid: { display: false }, ticks: { color: cc.tickColor, maxTicksLimit: 12, font: { size: 10 } } },
                  y: { grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: cc.tickColor }, title: { display: true, text: metric === 'hours' ? 'HRS/WK' : 'TSS/WK', color: cc.tickColor, font: { size: 9, weight: 'bold' } }, min: 0 }
                }
              }} 
            />
          ) : <p className="text-text-muted text-sm text-center py-12">No overview data available</p>}
        </div>

        {/* Stats Summary */}
        <div className="pt-4 border-t border-border/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[10px] font-bold text-text-muted uppercase tracking-widest flex items-center gap-2">
              <Activity size={12} className="text-accent" />
              Season Performance Summary 
              <span className="ml-1 lowercase font-normal italic opacity-70">(Calculated from {stats.total} completed weeks in this season)</span>
            </h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest mb-1 flex items-center gap-1.5"><TrendingUp size={12} /> Average Load</span>
              <span className="text-lg font-bold text-text">{metric === 'hours' ? `${stats.avg.toFixed(1)}h` : Math.round(stats.avg)}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-green uppercase tracking-widest mb-1 flex items-center gap-1.5"><Trophy size={12} /> On Target</span>
              <span className="text-lg font-bold text-green">{stats.onTarget} <span className="text-xs font-normal text-text-muted">/ {stats.total}</span></span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-red uppercase tracking-widest mb-1 flex items-center gap-1.5"><ArrowDownRight size={12} /> Under Target</span>
              <span className="text-lg font-bold text-red">{stats.under} <span className="text-xs font-normal text-text-muted">/ {stats.total}</span></span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-yellow uppercase tracking-widest mb-1 flex items-center gap-1.5"><ArrowUpRight size={12} /> Over Target</span>
              <span className="text-lg font-bold text-yellow">{stats.over} <span className="text-xs font-normal text-text-muted">/ {stats.total}</span></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function PowerCurveChart({ dateRange }: { dateRange: DateRange }) {
  const { data, isLoading, error } = usePowerCurve(dateRange)
  const cc = useChartColors()

  if (isLoading) return <div className="h-96 flex items-center justify-center text-text-muted animate-pulse italic">Calculating best efforts...</div>
  if (error) return <div className="h-96 flex items-center justify-center text-red">Error loading power data</div>
  if (!data || data.length === 0) return <div className="h-96 flex items-center justify-center text-text-muted">No power data for this range</div>

  const sorted = [...data].sort((a, b) => a.duration_s - b.duration_s)
  const fmtDurationLabel = (s: number): string => s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${(s / 3600).toFixed(1)}h`

  return (
    <div className="h-96">
      <Line 
        data={{
          labels: sorted.map((d) => fmtDurationLabel(d.duration_s)),
          datasets: [{
            label: 'Best Power (W)',
            data: sorted.map((d) => d.power),
            borderColor: '#f5c518',
            backgroundColor: 'rgba(245, 197, 24, 0.1)',
            fill: true,
            tension: 0.3,
            pointBackgroundColor: '#f5c518',
            pointRadius: 2,
            pointHoverRadius: 6,
          }]
        }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { afterLabel: (ctx) => `Date: ${sorted[ctx.dataIndex].date}` } }
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: cc.tickColor, font: { size: 10 } } },
            y: { grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: cc.tickColor }, title: { display: true, text: 'WATTS', color: cc.tickColor, font: { size: 9, weight: 'bold' } } }
          }
        }}
      />
    </div>
  )
}

function EfficiencyChart({ dateRange }: { dateRange: DateRange }) {
  const { data, isLoading, error } = useEfficiency(dateRange)
  const cc = useChartColors()

  if (isLoading) return <div className="h-96 flex items-center justify-center text-text-muted animate-pulse italic">Calculating aerobic decoupling...</div>
  if (error) return <div className="h-96 flex items-center justify-center text-red">Error loading efficiency data</div>
  if (!data || data.length === 0) return <div className="h-96 flex items-center justify-center text-text-muted">No efficiency data for this range</div>

  return (
    <div className="h-96">
      <Line 
        data={{
          labels: data.map((d) => d.date),
          datasets: [{
            label: 'Efficiency (W/bpm)',
            data: data.map((d) => d.ef),
            borderColor: '#00d4aa',
            backgroundColor: 'rgba(0, 212, 170, 0.1)',
            fill: true,
            tension: 0.3,
            pointBackgroundColor: '#00d4aa',
            pointRadius: 2,
            pointHoverRadius: 5,
          }]
        }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                afterLabel: (ctx) => {
                  const pt = data[ctx.dataIndex]
                  return `NP: ${pt.np}W\nAvg HR: ${pt.avg_hr}bpm`
                }
              }
            }
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: cc.tickColor, maxTicksLimit: 12, font: { size: 10 } } },
            y: { grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: cc.tickColor }, title: { display: true, text: 'POWER / HR', color: cc.tickColor, font: { size: 9, weight: 'bold' } } }
          }
        }}
      />
    </div>
  )
}

const ZONE_INFO: Record<string, { label: string; pctLow: number; pctHigh: number }> = {
  z0: { label: 'COASTING', pctLow: 0, pctHigh: 0 },
  z1: { label: 'ACTIVE RECOVERY', pctLow: 0, pctHigh: 0.55 },
  z2: { label: 'ENDURANCE', pctLow: 0.55, pctHigh: 0.75 },
  z3: { label: 'TEMPO', pctLow: 0.75, pctHigh: 0.90 },
  z4: { label: 'THRESHOLD', pctLow: 0.90, pctHigh: 1.05 },
  z5: { label: 'VO2MAX', pctLow: 1.05, pctHigh: 1.20 },
  z6: { label: 'ANAEROBIC', pctLow: 1.20, pctHigh: Infinity },
}

function zoneWattRange(zone: string, ftp: number): string {
  const info = ZONE_INFO[zone.toLowerCase()]
  if (!info || !ftp) return ''
  if (zone.toLowerCase() === 'z0') return '0W'
  if (info.pctHigh === Infinity) return `>${Math.round(ftp * info.pctLow)}W`
  return `${Math.round(ftp * info.pctLow)}-${Math.round(ftp * info.pctHigh)}W`
}

function ZonesChart({ dateRange }: { dateRange: DateRange }) {
  const { data, isLoading, error } = useZones(dateRange)
  const { data: athleteSettings } = useAthleteSettings()

  if (isLoading) return <div className="h-80 flex items-center justify-center text-text-muted animate-pulse italic">Aggregating time in zones...</div>
  if (error || !data || data.length === 0) return <div className="h-80 flex items-center justify-center text-text-muted">No zone data available</div>

  const ftp = parseInt(athleteSettings?.ftp || '0', 10)
  const totalHours = data.reduce((sum, z) => sum + z.hours, 0)

  return (
    <div className="flex flex-col lg:flex-row gap-12 items-center">
      <div className="w-full lg:w-1/2 h-80 relative">
        <Doughnut 
          data={{
            labels: data.map((d) => d.zone.toUpperCase()),
            datasets: [{
              data: data.map((d) => d.percentage),
              backgroundColor: data.map((d) => ZONE_COLORS[d.zone] || '#64748b'),
              borderColor: 'transparent',
              hoverOffset: 12,
            }]
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${ctx.parsed.toFixed(1)}% (${data[ctx.dataIndex].hours.toFixed(1)}h)` } }
            },
            cutout: '75%'
          }}
        />
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Total Time</span>
          <span className="text-3xl font-bold text-text">{totalHours.toFixed(1)}h</span>
        </div>
      </div>

      <div className="w-full lg:w-1/2">
        <div className="space-y-3">
          {data.map((z) => (
            <div key={z.zone} className="group">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: ZONE_COLORS[z.zone] || '#64748b' }} />
                  <span className="text-[10px] font-bold text-text uppercase tracking-wider">{z.zone.toUpperCase()}</span>
                  <span className="text-[10px] font-bold text-text-muted uppercase tracking-tighter opacity-0 group-hover:opacity-100 transition-opacity">
                    {ZONE_INFO[z.zone.toLowerCase()]?.label}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-[10px] font-mono text-text-muted">{ftp ? zoneWattRange(z.zone, ftp) : ''}</span>
                  <span className="text-xs font-bold text-text w-12 text-right">{z.percentage.toFixed(1)}%</span>
                </div>
              </div>
              <div className="w-full bg-surface-high rounded-full h-1.5 overflow-hidden">
                <div className="h-full rounded-full transition-all duration-1000 ease-out shadow-[0_0_8px] shadow-current opacity-80" style={{ width: `${z.percentage}%`, backgroundColor: ZONE_COLORS[z.zone] || '#64748b', color: ZONE_COLORS[z.zone] }} />
              </div>
            </div>
          ))}
        </div>
        {ftp > 0 && <p className="text-[10px] text-text-muted font-bold uppercase tracking-tighter mt-6 text-right italic">Calculated based on {ftp}W FTP</p>}
      </div>
    </div>
  )
}

function FTPHistoryChart({ dateRange }: { dateRange: DateRange }) {
  const { data, isLoading, error } = useFTPHistory(dateRange)
  const cc = useChartColors()

  if (isLoading) return <div className="h-96 flex items-center justify-center text-text-muted animate-pulse italic">Loading history...</div>
  if (error || !data || data.length === 0) return <div className="h-96 flex items-center justify-center text-text-muted">No FTP history available</div>

  const hasWkg = data.some((d) => d.w_per_kg != null)

  return (
    <div className="h-96">
      {/* @ts-ignore mixed chart types */}
      <Bar 
        data={{
          labels: data.map((d) => d.month),
          datasets: [
            {
              type: 'bar' as const,
              label: 'FTP (W)',
              data: data.map((d) => d.ftp),
              backgroundColor: 'rgba(245, 197, 24, 0.7)',
              borderColor: '#f5c518',
              borderWidth: 1,
              borderRadius: 4,
              yAxisID: 'y',
            },
            ...(hasWkg ? [{
              type: 'line' as const,
              label: 'W/kg',
              data: data.map((d) => d.w_per_kg ?? null),
              borderColor: '#00d4aa',
              backgroundColor: 'transparent',
              pointRadius: 4,
              pointHoverRadius: 6,
              tension: 0.3,
              yAxisID: 'y1',
            }] : []),
          ] as any[],
        }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: cc.tickColor, boxWidth: 12, font: { size: 11, weight: 'bold' } }, position: 'top', align: 'end' },
            tooltip: {
              callbacks: {
                afterLabel: (ctx) => {
                  if (ctx.datasetIndex === 0) {
                    const pt = data[ctx.dataIndex]
                    const lines: string[] = []
                    if (pt.weight_kg != null) lines.push(`Weight: ${fmtWeight(pt.weight_kg)}`)
                    if (pt.w_per_kg != null) lines.push(`W/kg: ${pt.w_per_kg.toFixed(2)}`)
                    return lines.join('\n')
                  }
                  return ''
                }
              }
            }
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: cc.tickColor, font: { size: 10 } } },
            y: { position: 'left', grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: cc.tickColor }, title: { display: true, text: 'WATTS', color: cc.tickColor, font: { size: 9, weight: 'bold' } } },
            y1: hasWkg ? { position: 'right', grid: { display: false }, ticks: { color: '#00d4aa', font: { size: 10 } }, title: { display: true, text: 'W/KG', color: '#00d4aa', font: { size: 9, weight: 'bold' } } } : {}
          }
        }}
      />
    </div>
  )
}

function WeightChart({ dateRange }: { dateRange: DateRange }) {
  const { data: measurements, isLoading, error } = useWeightHistory(dateRange)
  const { data: withingsStatus } = useWithingsStatus()
  const cc = useChartColors()
  const units = useUnits()
  const imperial = units === 'imperial'
  const unitLabel = imperial ? 'lbs' : 'kg'
  const toDisplay = (kg: number) => imperial ? kg * 2.20462 : kg

  if (isLoading) return <div className="h-96 flex items-center justify-center text-text-muted animate-pulse italic">Loading weight data...</div>
  if (error) return <div className="h-96 flex items-center justify-center text-red">Error loading weight data</div>
  if (!measurements || measurements.length === 0) return (
    <div className="h-96 flex flex-col items-center justify-center gap-2 text-text-muted">
      <Scale size={32} className="opacity-30" />
      <p className="text-sm italic">No weight data for this range</p>
      {!withingsStatus?.connected && (
        <p className="text-xs opacity-70">Connect Withings in Settings to sync body measurements.</p>
      )}
    </div>
  )

  const displayWeights = measurements.map((d) => toDisplay(d.weight_kg))
  const minWeight = Math.min(...displayWeights)
  const maxWeight = Math.max(...displayWeights)
  const padding = (maxWeight - minWeight) * 0.1 || (imperial ? 2 : 1)

  return (
    <div>
      {withingsStatus?.connected && withingsStatus?.last_measurement_date && (
        <p className="text-xs text-text-muted mb-4">
          Withings — last synced {withingsStatus.last_measurement_date}
        </p>
      )}
      <div className="h-80">
        <Line
          data={{
            labels: measurements.map((d) => d.date),
            datasets: [{
              label: `Weight (${unitLabel})`,
              data: displayWeights,
              borderColor: '#00d4aa',
              backgroundColor: 'rgba(0, 212, 170, 0.08)',
              fill: true,
              tension: 0.3,
              spanGaps: true,
              pointBackgroundColor: '#00d4aa',
              pointRadius: 3,
              pointHoverRadius: 6,
            }],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: cc.tooltipBg,
                titleColor: cc.tooltipTitle,
                bodyColor: cc.tooltipBody,
                callbacks: {
                  label: (ctx) => `${(ctx.parsed.y as number).toFixed(1)} ${unitLabel}`,
                },
              },
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: { color: cc.tickColor, maxTicksLimit: 12, font: { size: 10 } },
              },
              y: {
                grid: { color: 'rgba(148, 163, 184, 0.1)' },
                ticks: { color: cc.tickColor, callback: (v) => `${v} ${unitLabel}` },
                title: { display: true, text: `WEIGHT (${unitLabel.toUpperCase()})`, color: cc.tickColor, font: { size: 9, weight: 'bold' } },
                min: Math.floor(minWeight - padding),
                max: Math.ceil(maxWeight + padding),
              },
            },
          }}
        />
      </div>
    </div>
  )
}

export default function Analysis() {
  const [activeTab, setActiveTab] = useState<Tab>('power-curve')
  const [range, setRange] = useState<RangeKey>('3m')
  const dateRange = useMemo(() => rangeToDates(range), [range])

  return (
    <div className="space-y-8 pb-12">
      <h1 className="text-2xl font-bold text-text">Analysis</h1>

      <TrainingPlanOverview />

      <div className="space-y-6">
        {/* Sub-Tabs Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border">
          <div className="flex overflow-x-auto no-scrollbar">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 px-5 py-3 text-[10px] font-bold uppercase tracking-widest rounded-t-xl transition-all whitespace-nowrap ${
                  activeTab === tab.key
                    ? 'bg-surface text-accent border-b-2 border-accent'
                    : 'text-text-muted hover:text-text hover:bg-surface/50'
                }`}
              >
                <tab.icon size={14} />
                {tab.label}
              </button>
            ))}
          </div>
          
          <div className="flex bg-surface-low rounded-lg p-1 border border-border mb-2 sm:mb-0">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                onClick={() => setRange(opt.key)}
                className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-tighter rounded-md transition-all ${
                  range === opt.key ? 'bg-accent text-white shadow-sm' : 'text-text-muted hover:text-text'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content card */}
        <div className="bg-surface rounded-xl border border-border p-6 shadow-sm min-h-[450px] animate-in fade-in slide-in-from-bottom-2 duration-300">
          {activeTab === 'power-curve' && <PowerCurveChart dateRange={dateRange} />}
          {activeTab === 'efficiency' && <EfficiencyChart dateRange={dateRange} />}
          {activeTab === 'zones' && <ZonesChart dateRange={dateRange} />}
          {activeTab === 'ftp-history' && <FTPHistoryChart dateRange={dateRange} />}
          {activeTab === 'weight' && <WeightChart dateRange={dateRange} />}
        </div>
      </div>
    </div>
  )
}
