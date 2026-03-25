import { useState, useMemo } from 'react'
import { usePowerCurve, useEfficiency, useZones, useFTPHistory } from '../hooks/useApi'
import { useChartColors } from '../lib/theme'
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
              if (pt.weight_kg != null) lines.push(`Weight: ${pt.weight_kg.toFixed(1)} kg`)
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
