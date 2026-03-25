import { useState, useMemo } from 'react'
import { useWorkoutDetail, useUpdateWorkoutNotes } from '../hooks/useApi'
import { fmtTime, zoneColor, zoneLabel } from '../lib/format'
import { useChartColors } from '../lib/theme'
import { Line } from 'react-chartjs-2'
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
import type { WorkoutDetail, WorkoutStep } from '../types/api'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler)

interface Props {
  workoutId: number | null
  onClose: () => void
}

function computeSummary(detail: WorkoutDetail) {
  const { steps, ftp, total_duration_s } = detail
  const totalDuration = total_duration_s
  let weightedSum = 0
  let maxTarget = 0

  for (const step of steps) {
    const watts = step.power_watts
    weightedSum += watts * step.duration_s
    if (watts > maxTarget) maxTarget = watts
  }

  const avgPower = totalDuration > 0 ? Math.round(weightedSum / totalDuration) : 0
  const intensityFactor = ftp > 0 ? avgPower / ftp : 0
  const tss = totalDuration > 0 ? Math.round((totalDuration * avgPower * intensityFactor) / (ftp * 3600) * 100) : 0

  return {
    duration: totalDuration,
    ftp,
    avgPower,
    maxTarget: Math.round(maxTarget),
    intensityFactor: intensityFactor.toFixed(2),
    tss,
  }
}

function buildChartData(steps: WorkoutStep[], _ftp: number) {
  const labels: string[] = []
  const powers: number[] = []
  const bgColors: string[] = []
  const SAMPLE_INTERVAL = 5

  for (const step of steps) {
    const endS = step.start_s + step.duration_s
    for (let t = step.start_s; t < endS; t += SAMPLE_INTERVAL) {
      labels.push(fmtTime(t))
      powers.push(step.power_watts)
      bgColors.push(zoneColor(step.power_pct, 0.35))
    }
  }

  return {
    labels,
    datasets: [
      {
        label: 'Target Power',
        data: powers,
        borderColor: 'rgba(245, 197, 24, 1)',
        backgroundColor: bgColors,
        fill: true,
        stepped: 'before' as const,
        pointRadius: 0,
        borderWidth: 2,
        tension: 0,
      },
    ],
  }
}

export default function WorkoutViewer({ workoutId, onClose }: Props) {
  const { data: detail, isLoading, error } = useWorkoutDetail(workoutId)
  const updateNotes = useUpdateWorkoutNotes()
  const cc = useChartColors()
  const [athleteNotes, setAthleteNotes] = useState<string | null>(null)
  const [saveStatus, setSaveStatus] = useState('')

  // Initialize athlete notes from detail when loaded
  const notesValue = athleteNotes ?? detail?.athlete_notes ?? ''

  const summary = useMemo(() => detail ? computeSummary(detail) : null, [detail])
  const chartData = useMemo(() => detail ? buildChartData(detail.steps, detail.ftp) : null, [detail])

  if (workoutId === null) return null

  const handleSaveNotes = async () => {
    if (!detail) return
    setSaveStatus('')
    try {
      await updateNotes.mutateAsync({ id: detail.id, body: { athlete_notes: notesValue || null } })
      setSaveStatus('Saved!')
      setTimeout(() => setSaveStatus(''), 2000)
    } catch {
      setSaveStatus('Error saving')
    }
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx: any) => `${ctx.parsed.y}w`,
        },
      },
    },
    scales: {
      x: {
        ticks: { color: cc.tickColor, maxTicksLimit: 10, font: { size: 10 } },
        grid: { color: cc.gridColor },
      },
      y: {
        title: { display: true, text: 'Watts', color: cc.tickColor },
        ticks: { color: cc.tickColor, font: { size: 10 } },
        grid: { color: cc.gridColor },
        min: 0,
      },
    },
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface border border-border rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-lg font-semibold text-text">
            {detail?.name ?? 'Workout'}
          </h2>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text text-xl leading-none"
          >
            &times;
          </button>
        </div>

        {isLoading && (
          <div className="px-6 py-12 text-center text-text-muted animate-pulse">Loading workout...</div>
        )}

        {error && (
          <div className="px-6 py-12 text-center text-red-400">Failed to load workout.</div>
        )}

        {detail && summary && chartData && (
          <div className="px-6 py-4 space-y-6">
            {/* Summary bar */}
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
              {[
                { label: 'Duration', value: fmtTime(summary.duration) },
                { label: 'FTP', value: `${summary.ftp}w` },
                { label: 'Avg Power', value: `${summary.avgPower}w` },
                { label: 'Max Target', value: `${summary.maxTarget}w` },
                { label: 'IF (est)', value: summary.intensityFactor },
                { label: 'TSS (est)', value: summary.tss },
              ].map(item => (
                <div key={item.label} className="bg-bg rounded-lg px-3 py-2 text-center">
                  <div className="text-xs text-text-muted">{item.label}</div>
                  <div className="text-sm font-semibold text-text">{item.value}</div>
                </div>
              ))}
            </div>

            {/* Power profile chart */}
            <div className="bg-bg rounded-lg p-4" style={{ height: 220 }}>
              <Line data={chartData} options={chartOptions} />
            </div>

            {/* Steps table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-muted text-xs border-b border-border">
                    <th className="text-left py-2 px-2">Type</th>
                    <th className="text-left py-2 px-2">Time Range</th>
                    <th className="text-left py-2 px-2">Duration</th>
                    <th className="text-left py-2 px-2">Power</th>
                    <th className="text-left py-2 px-2">Zone</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.steps.map((step, i) => (
                    <tr key={i} className="border-b border-border/50 hover:bg-surface2/50">
                      <td className="py-1.5 px-2 text-text capitalize">{step.type}</td>
                      <td className="py-1.5 px-2 text-text-muted">
                        {fmtTime(step.start_s)} - {fmtTime(step.start_s + step.duration_s)}
                      </td>
                      <td className="py-1.5 px-2 text-text">{fmtTime(step.duration_s)}</td>
                      <td className="py-1.5 px-2 text-text">
                        {step.power_watts}w
                        <span className="text-text-muted ml-1">({Math.round(step.power_pct * 100)}%)</span>
                      </td>
                      <td className="py-1.5 px-2">
                        <span
                          className="inline-block px-2 py-0.5 rounded text-xs font-medium"
                          style={{ backgroundColor: zoneColor(step.power_pct, 0.25), color: zoneColor(step.power_pct) }}
                        >
                          {zoneLabel(step.power_pct)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Notes section */}
            {detail.id && (
              <div className="space-y-4">
                {detail.coach_notes && (
                  <div>
                    <h4 className="text-xs font-semibold text-text-muted uppercase mb-1">Coach's Notes</h4>
                    <div className="bg-bg rounded-lg px-4 py-3 text-sm text-text whitespace-pre-wrap">
                      {detail.coach_notes}
                    </div>
                  </div>
                )}
                <div>
                  <h4 className="text-xs font-semibold text-text-muted uppercase mb-1">Your Pre-Ride Notes</h4>
                  <textarea
                    value={notesValue}
                    onChange={e => setAthleteNotes(e.target.value)}
                    placeholder="How are you feeling? Any goals for this session?"
                    rows={3}
                    className="w-full bg-bg border border-border rounded-lg px-4 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-accent resize-none"
                  />
                  <div className="flex items-center gap-3 mt-2">
                    <button
                      onClick={handleSaveNotes}
                      disabled={updateNotes.isPending}
                      className="bg-accent text-white px-4 py-1.5 rounded-md text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
                    >
                      {updateNotes.isPending ? 'Saving...' : 'Save'}
                    </button>
                    {saveStatus && (
                      <span className="text-xs text-green">{saveStatus}</span>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Actions: Download links */}
            <div className="flex gap-3 border-t border-border pt-4">
              <a
                href={`/api/plan/workouts/${detail.id}/download?fmt=tcx`}
                download
                className="text-sm text-accent hover:underline"
              >
                Download TCX
              </a>
              <a
                href={`/api/plan/workouts/${detail.id}/download?fmt=zwo`}
                download
                className="text-sm text-accent hover:underline"
              >
                Download ZWO
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
