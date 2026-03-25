import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { usePMC, useRides, useWeeklySummary } from '../hooks/useApi'
import { fmtDuration, fmtDistance } from '../lib/format'
import { useChartColors } from '../lib/theme'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler)

interface Props {
  onRideSelect?: (id: number) => void
}

export default function Dashboard({ onRideSelect }: Props) {
  const { data: pmcData, isLoading: pmcLoading } = usePMC()
  const { data: rides, isLoading: ridesLoading } = useRides({ limit: 7 })
  const { data: _weekly, isLoading: _weeklyLoading } = useWeeklySummary()
  const cc = useChartColors()

  if (pmcLoading || ridesLoading) {
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
    { label: 'Weight', value: lastPMC?.weight ? `${lastPMC.weight.toFixed(1)} kg` : '--', color: 'text-yellow' },
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
                    <td className="py-2 pr-4 text-right">{fmtDistance(ride.distance_m)}</td>
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
