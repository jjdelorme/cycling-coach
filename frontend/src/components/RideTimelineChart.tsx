import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { Line } from 'react-chartjs-2'
import { Activity } from 'lucide-react'
import { zoneColor, fmtTime } from '../lib/format'
import { useChartColors } from '../lib/theme'
import type { WorkoutDetail, WorkoutStep, RideLap } from '../types/api'
import { ChartJS } from '../lib/charts'

function buildStepIndexMap(sampleCount: number, downsampleStep: number, steps: WorkoutStep[]): number[] {
  const map: number[] = []
  for (let i = 0; i < sampleCount; i++) {
    const secs = i * downsampleStep
    let found = -1
    for (let si = 0; si < steps.length; si++) {
      const s = steps[si]
      if (secs >= s.start_s && secs < s.start_s + s.duration_s) { found = si; break }
    }
    map.push(found)
  }
  return map
}

function buildLapIndexMap(sampleCount: number, downsampleStep: number, records: any[], laps: RideLap[]): number[] {
  const firstRecordTs = records[0]?.timestamp_utc
  const firstLapTs = laps[0]?.start_time
  
  if (firstRecordTs && firstLapTs && firstRecordTs.length > 5 && firstLapTs.length > 5) {
    const lapTimes = laps.map(l => {
      const start = new Date(l.start_time || '').getTime()
      return { start, end: start + (l.total_timer_time || 0) * 1000 }
    })
    
    const map: number[] = []
    for (let i = 0; i < sampleCount; i++) {
      const r = records[i * downsampleStep]
      if (!r || !r.timestamp_utc) { map.push(-1); continue }
      const t = new Date(r.timestamp_utc).getTime()
      map.push(lapTimes.findIndex(lt => t >= lt.start && t <= lt.end))
    }
    return map
  }

  let cumulative = 0
  const lapRanges = laps.map(l => {
    const start = cumulative
    const end = start + (l.total_timer_time || 0)
    cumulative = end
    return { start, end }
  })
  
  const map: number[] = []
  for (let i = 0; i < sampleCount; i++) {
    const secs = i * downsampleStep
    const idx = lapRanges.findIndex(range => secs >= range.start && secs < range.end)
    map.push(idx)
  }
  return map
}

const selectionDataMap = new WeakMap<ChartJS, { state: 'idle' | 'dragging' | 'locked'; startIdx: number | null; endIdx: number | null }>()

interface Props {
  records: { timestamp_utc?: string; power?: number; heart_rate?: number; cadence?: number }[]
  laps: RideLap[]
  workout?: WorkoutDetail
  highlightedStep?: number | null
  highlightedLapIndex?: number | null
}

export default function RideTimelineChart({ records, laps, workout, highlightedStep, highlightedLapIndex }: Props) {
  const cc = useChartColors()
  const chartRef = useRef<ChartJS<'line'>>(null)
  const [selectionStats, setSelectionStats] = useState<{ duration: number; avgPower: number | null; avgHR: number | null; avgCadence: number | null } | null>(null)

  const { chartData, stepIndexMap, lapIndexMap, downsampleStep } = useMemo(() => {
    const maxPoints = 600
    const plannedOnly = records.length === 0 && workout?.steps && workout.steps.length > 0

    // For planned-only workouts, synthesize one data point per second from steps
    let sampled: typeof records
    let step: number
    let labels: string[]

    if (plannedOnly) {
      const totalSeconds = workout!.steps.reduce((sum, s) => sum + s.duration_s, 0)
      step = Math.max(1, Math.floor(totalSeconds / maxPoints))
      const pointCount = Math.ceil(totalSeconds / step)
      sampled = Array.from({ length: pointCount }, () => ({}))
      labels = sampled.map((_, i) => { const s = i * step, m = Math.floor(s / 60), h = Math.floor(m / 60); return h > 0 ? `${h}:${String(m % 60).padStart(2, '0')}` : `${m}m` })
    } else {
      step = Math.max(1, Math.floor(records.length / maxPoints))
      sampled = records.filter((_, i) => i % step === 0)
      labels = sampled.map((_, i) => { const s = i * step, m = Math.floor(s / 60), h = Math.floor(m / 60); return h > 0 ? `${h}:${String(m % 60).padStart(2, '0')}` : `${m}m` })
    }

    const datasets: any[] = []

    const sMap = workout?.steps ? buildStepIndexMap(sampled.length, step, workout.steps) : []
    const lMap = plannedOnly ? [] : buildLapIndexMap(sampled.length, step, records, laps)

    if (workout?.steps) {
      datasets.push({
        label: 'Target Power', data: sampled.map((_, i) => sMap[i] >= 0 ? workout.steps[sMap[i]].power_watts : null),
        borderColor: 'rgba(148, 163, 184, 0.3)', backgroundColor: sampled.map((_, i) => sMap[i] < 0 ? 'transparent' : zoneColor(workout.steps[sMap[i]].power_pct, 0.15)),
        fill: true, stepped: 'before' as const, borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, tension: 0, yAxisID: 'y', order: 2,
      })
    }

    if (sampled.some(r => r.power != null)) datasets.push({ label: 'Power', data: sampled.map(r => r.power ?? null), borderColor: 'rgba(245, 197, 24, 0.8)', backgroundColor: 'rgba(245, 197, 24, 0.05)', fill: !workout, borderWidth: 1.5, pointRadius: 0, tension: 0.2, yAxisID: 'y', order: 1 })
    if (sampled.some(r => r.heart_rate != null)) datasets.push({ label: 'Heart Rate', data: sampled.map(r => r.heart_rate ?? null), borderColor: 'rgba(233, 69, 96, 0.8)', backgroundColor: 'transparent', fill: false, borderWidth: 1.2, pointRadius: 0, tension: 0.2, yAxisID: 'y1', order: 1 })
    if (sampled.some(r => r.cadence != null)) datasets.push({ label: 'Cadence', data: sampled.map(r => r.cadence ?? null), borderColor: 'rgba(126, 200, 227, 0.6)', backgroundColor: 'transparent', fill: false, borderWidth: 1, pointRadius: 0, tension: 0.2, yAxisID: 'y2', order: 1 })

    return { chartData: { labels, datasets }, stepIndexMap: sMap, lapIndexMap: lMap, downsampleStep: step }
  }, [records, workout, laps])

  const highlightColor = useMemo(() => {
    if (highlightedStep != null && workout?.steps?.[highlightedStep]) {
      return zoneColor(workout.steps[highlightedStep].power_pct, 0.8)
    }
    if (highlightedLapIndex != null) return '#00d4aa'
    return 'rgba(255, 255, 255, 0.5)'
  }, [highlightedStep, highlightedLapIndex, workout])

  const targetIndex = highlightedStep ?? highlightedLapIndex ?? -1
  const activeMap = highlightedStep != null ? stepIndexMap : lapIndexMap

  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.update('none')
    }
  }, [targetIndex, highlightColor])

  const computeSelectionStats = useCallback((lo: number, hi: number) => {
    const slice = records.slice(lo * downsampleStep, Math.min(hi * downsampleStep, records.length - 1) + 1)
    const avg = (arr: number[]) => arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null
    setSelectionStats({ duration: slice.length, avgPower: avg(slice.map(r => r.power).filter((v): v is number => v != null && v > 0)), avgHR: avg(slice.map(r => r.heart_rate).filter((v): v is number => v != null && v > 0)), avgCadence: avg(slice.map(r => r.cadence).filter((v): v is number => v != null && v > 0)) })
  }, [records, downsampleStep])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !chart.canvas) return
    const canvas = chart.canvas
    selectionDataMap.set(chart, { state: 'idle', startIdx: null, endIdx: null })
    canvas.style.cursor = 'crosshair'
    function getIdx(e: MouseEvent) { const r = canvas.getBoundingClientRect(), x = e.clientX - r.left; return Math.round(Math.max(0, Math.min(chart!.scales.x.getValueForPixel(x) ?? 0, (chartData.labels?.length ?? 1) - 1))) }
    function onDown(e: MouseEvent) { const sel = selectionDataMap.get(chart!), r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, a = chart!.chartArea; if (!a || x < a.left || x > a.right || y < a.top || y > a.bottom) return; if (sel?.state === 'locked') { selectionDataMap.set(chart!, { state: 'idle', startIdx: null, endIdx: null }); setSelectionStats(null); chart!.draw(); return }; const i = getIdx(e); selectionDataMap.set(chart!, { state: 'dragging', startIdx: i, endIdx: i }); chart!.draw() }
    function onMove(e: MouseEvent) { const sel = selectionDataMap.get(chart!); if (sel?.state === 'dragging') { sel.endIdx = getIdx(e); chart!.draw() } }
    function onUp() { const sel = selectionDataMap.get(chart!); if (sel?.state === 'dragging') { if (sel.startIdx != null && sel.endIdx != null && Math.abs(sel.endIdx - sel.startIdx) > 2) { sel.state = 'locked'; computeSelectionStats(Math.min(sel.startIdx, sel.endIdx), Math.max(sel.startIdx, sel.endIdx)) } else { selectionDataMap.set(chart!, { state: 'idle', startIdx: null, endIdx: null }); setSelectionStats(null) }; chart!.draw() } }
    canvas.addEventListener('mousedown', onDown); canvas.addEventListener('mousemove', onMove); canvas.addEventListener('mouseup', onUp); canvas.addEventListener('mouseleave', onUp)
    return () => { canvas.removeEventListener('mousedown', onDown); canvas.removeEventListener('mousemove', onMove); canvas.removeEventListener('mouseup', onUp); canvas.removeEventListener('mouseleave', onUp); selectionDataMap.delete(chart!) }
  }, [records, workout, chartData.labels?.length, computeSelectionStats])

  const selectionPlugin = useMemo(() => ({
    id: 'selectionPlugin',
    afterDraw(chart: any) {
      const sel = selectionDataMap.get(chart)
      if (!sel || sel.startIdx == null || sel.endIdx == null || sel.state === 'idle') return
      const { ctx, chartArea, scales } = chart
      if (!chartArea || !scales?.x) return
      const x1 = scales.x.getPixelForValue(Math.min(sel.startIdx, sel.endIdx)), x2 = scales.x.getPixelForValue(Math.max(sel.startIdx, sel.endIdx))
      ctx.save()
      ctx.fillStyle = 'rgba(0, 212, 170, 0.1)'
      ctx.fillRect(x1, chartArea.top, x2 - x1, chartArea.bottom - chartArea.top)
      ctx.strokeStyle = '#00d4aa'
      ctx.lineWidth = 1
      ctx.strokeRect(x1, chartArea.top, x2 - x1, chartArea.bottom - chartArea.top)
      ctx.restore()
    }
  }), [])

  return (
    <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center justify-between">
        <h2 className="text-sm font-bold text-text uppercase tracking-wider flex items-center gap-2">
          <Activity size={16} className="text-accent" /> Ride Timeline
        </h2>
        <div className="flex items-center gap-4 text-[10px] font-bold text-text-muted uppercase tracking-widest">
          <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-yellow" /> Power</span>
          <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-red" /> HR</span>
          {workout && <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full border border-dashed border-text-muted" /> Target</span>}
        </div>
      </div>
      <div className="p-5">
        <div className="h-64 sm:h-80">
          <Line ref={chartRef} data={chartData} plugins={[selectionPlugin]} options={{
            responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
            plugins: { 
              legend: { display: false }, 
              tooltip: { backgroundColor: cc.tooltipBg, titleColor: cc.tooltipTitle, bodyColor: cc.tooltipBody },
              highlightPlugin: {
                enabled: true,
                target: targetIndex,
                map: activeMap,
                highlightColor
              }
            },
            scales: {
              x: { ticks: { color: cc.tickColor, maxTicksLimit: 12, font: { size: 10 } }, grid: { display: false } },
              y: { type: 'linear', position: 'left', title: { display: true, text: 'POWER (W)', color: 'rgba(245, 197, 24, 0.8)', font: { size: 9, weight: 'bold' } }, ticks: { color: 'rgba(245, 197, 24, 0.7)', font: { size: 10 } }, grid: { color: 'rgba(148, 163, 184, 0.1)' }, min: 0 },
              y1: { type: 'linear', position: 'right', title: { display: true, text: 'HR (BPM)', color: 'rgba(233, 69, 96, 0.8)', font: { size: 9, weight: 'bold' } }, ticks: { color: 'rgba(233, 69, 96, 0.7)', font: { size: 10 } }, grid: { display: false } },
              y2: { type: 'linear', display: false, min: 0, max: 200 }
            }
          } as any} />
        </div>
        {selectionStats && (
          <div className="flex flex-wrap items-center gap-x-8 gap-y-2 mt-4 pt-4 border-t border-border animate-in fade-in zoom-in duration-300">
            <div className="flex flex-col"><span className="text-[10px] font-bold text-text-muted uppercase tracking-tighter">Selection</span><span className="text-sm font-bold text-text font-mono">{fmtTime(selectionStats.duration)}</span></div>
            {selectionStats.avgPower != null && <div className="flex flex-col"><span className="text-[10px] font-bold text-blue uppercase tracking-tighter">Avg Power</span><span className="text-sm font-bold text-blue font-mono">{selectionStats.avgPower}w</span></div>}
            {selectionStats.avgHR != null && <div className="flex flex-col"><span className="text-[10px] font-bold text-red uppercase tracking-tighter">Avg HR</span><span className="text-sm font-bold text-red font-mono">{selectionStats.avgHR} bpm</span></div>}
            {selectionStats.avgCadence != null && <div className="flex flex-col"><span className="text-[10px] font-bold text-text-muted uppercase tracking-tighter">Avg Cadence</span><span className="text-sm font-bold text-text font-mono">{selectionStats.avgCadence} rpm</span></div>}
          </div>
        )}
      </div>
    </section>
  )
}
