import { useState, useEffect, useMemo, useRef } from 'react'
import { useRides, useRide, useUpdateRideComments, useUpdateRideTitle, useWorkoutByDate, useUpdateWorkoutNotes, useSendChat, useActivityDates } from '../hooks/useApi'
import { fmtDuration, fmtDistance, fmtElevation, fmtTime, zoneColor, zoneLabel } from '../lib/format'
import { useUnits } from '../lib/units'
import { useChartColors } from '../lib/theme'
import { useQueryClient } from '@tanstack/react-query'
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
  initialRideId?: number
  initialDate?: string
}

export default function Rides({ initialRideId, initialDate }: Props) {
  const units = useUnits()
  const [selectedRideId, setSelectedRideId] = useState<number | null>(initialRideId ?? null)
  const [selectedDate, setSelectedDate] = useState<string | null>(initialDate ?? null)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [filterParams, setFilterParams] = useState<{ start_date?: string; end_date?: string }>({})
  const [postRideNotes, setPostRideNotes] = useState('')
  const [notesDirty, setNotesDirty] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)

  const queryClient = useQueryClient()
  const { data: rides, isLoading: ridesLoading } = useRides(filterParams)
  const { data: ride, isLoading: rideLoading } = useRide(selectedRideId)
  const updateComments = useUpdateRideComments()
  const sendChat = useSendChat()

  // Extract date from ride for workout lookup, or use selectedDate
  const rideDate = ride?.date?.slice(0, 10) ?? selectedDate
  const { data: plannedWorkout } = useWorkoutByDate(rideDate)

  // Sync post_ride_comments into local state when ride loads
  useEffect(() => {
    if (ride) {
      setPostRideNotes(ride.post_ride_comments ?? '')
      setNotesDirty(false)
    }
  }, [ride?.id, ride?.post_ride_comments])

  // Open to initial ride
  useEffect(() => {
    if (initialRideId != null) {
      setSelectedRideId(initialRideId)
      setSelectedDate(null)
    }
  }, [initialRideId])

  // Open to initial date (workout-only)
  useEffect(() => {
    if (initialDate != null) {
      setSelectedDate(initialDate)
      setSelectedRideId(null)
    }
  }, [initialDate])

  function handleFilter() {
    const params: { start_date?: string; end_date?: string } = {}
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    setFilterParams(params)
  }

  function handleSaveNotes() {
    if (selectedRideId == null) return
    updateComments.mutate({ id: selectedRideId, body: { post_ride_comments: postRideNotes || null } }, {
      onSuccess: () => setNotesDirty(false),
    })
  }

  async function handleGetFeedback() {
    if (!ride) return
    setAnalyzing(true)
    try {
      const prompt = `Analyze ride ${ride.id} from ${ride.date}. ` +
        `Sport: ${ride.sport ?? 'cycling'}. Duration: ${fmtDuration(ride.duration_s)}. ` +
        `Distance: ${fmtDistance(ride.distance_m, units)}. TSS: ${ride.tss ?? '--'}. ` +
        `Avg Power: ${ride.avg_power ?? '--'}w. NP: ${ride.normalized_power ?? '--'}w. ` +
        `Avg HR: ${ride.avg_hr ?? '--'}bpm. IF: ${ride.intensity_factor?.toFixed(2) ?? '--'}. ` +
        `Ascent: ${fmtElevation(ride.total_ascent, units)}. ` +
        (ride.post_ride_comments ? `Athlete notes: "${ride.post_ride_comments}". ` : '') +
        `Please provide post-ride coaching analysis and save it as coach comments on ride ${ride.id}.`
      await sendChat.mutateAsync({ message: prompt })
      queryClient.invalidateQueries({ queryKey: ['ride', ride.id] })
    } finally {
      setAnalyzing(false)
    }
  }

  // ── Detail View (ride or workout-only) ──
  const showDetail = selectedRideId != null || selectedDate != null
  const [highlightedStep, setHighlightedStep] = useState<number | null>(null)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const updateTitle = useUpdateRideTitle()

  // Reverse geocode location from start_lat/start_lon
  const [locationName, setLocationName] = useState<string | null>(null)
  useEffect(() => {
    if (!ride?.start_lat || !ride?.start_lon) {
      setLocationName(null)
      return
    }
    let cancelled = false
    fetch(`https://nominatim.openstreetmap.org/reverse?lat=${ride.start_lat}&lon=${ride.start_lon}&format=json&zoom=10`)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return
        const addr = data.address || {}
        const parts = [addr.city || addr.town || addr.village || addr.hamlet, addr.state].filter(Boolean)
        setLocationName(parts.join(', ') || data.display_name?.split(',').slice(0, 2).join(',') || null)
      })
      .catch(() => { if (!cancelled) setLocationName(null) })
    return () => { cancelled = true }
  }, [ride?.start_lat, ride?.start_lon])

  // Calendar-based prev/next navigation
  const { data: activityDates } = useActivityDates()
  const currentDate = rideDate ?? null
  const { prevDate, nextDate } = useMemo(() => {
    if (!activityDates || !currentDate) return { prevDate: null, nextDate: null }
    const idx = activityDates.indexOf(currentDate)
    if (idx < 0) {
      // Current date not in list; find nearest neighbors
      let prev: string | null = null
      let next: string | null = null
      for (const d of activityDates) {
        if (d < currentDate) prev = d
        if (d > currentDate && !next) next = d
      }
      return { prevDate: prev, nextDate: next }
    }
    return {
      prevDate: idx > 0 ? activityDates[idx - 1] : null,
      nextDate: idx < activityDates.length - 1 ? activityDates[idx + 1] : null,
    }
  }, [activityDates, currentDate])

  function navigateToDate(date: string) {
    // Find if there's a ride on this date; if so, navigate to it, otherwise use date-based view
    const rideOnDate = rides?.find(r => r.date?.slice(0, 10) === date)
    if (rideOnDate) {
      setSelectedRideId(rideOnDate.id)
      setSelectedDate(null)
    } else {
      setSelectedRideId(null)
      setSelectedDate(date)
    }
  }

  if (showDetail) {
    const isRideView = selectedRideId != null && ride != null
    const isWorkoutOnly = !isRideView && plannedWorkout != null

    // Start time: prefer ride.start_time, fall back to first record timestamp
    const startTime = (() => {
      if (!isRideView) return null
      const raw = ride?.start_time || ride?.records?.[0]?.timestamp_utc
      if (!raw) return null
      // Append Z if no timezone indicator present so JS parses as UTC
      const ts = raw.includes('Z') || raw.includes('+') || raw.includes('T') && raw.match(/[+-]\d{2}:?\d{2}$/)
        ? raw
        : raw + 'Z'
      return new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    })()

    const displayTitle = ride?.title || ride?.sport || 'Cycling'

    return (
      <div className="space-y-6">
        {/* Navigation */}
        <div className="flex items-center justify-end">
          <div className="flex items-center gap-2">
            <button
              onClick={() => prevDate && navigateToDate(prevDate)}
              disabled={!prevDate}
              className="px-3 py-1 text-sm rounded-md transition-colors disabled:opacity-30 disabled:cursor-not-allowed bg-surface2 text-text-muted hover:text-text border border-border"
              title={prevDate ?? undefined}
            >
              &larr; Prev
            </button>
            <span className="text-sm font-medium text-text text-center leading-tight">
              {currentDate && <span className="block text-text-muted text-xs">{new Date(currentDate + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long' })}</span>}
              {currentDate ?? ''}
            </span>
            <button
              onClick={() => nextDate && navigateToDate(nextDate)}
              disabled={!nextDate}
              className="px-3 py-1 text-sm rounded-md transition-colors disabled:opacity-30 disabled:cursor-not-allowed bg-surface2 text-text-muted hover:text-text border border-border"
              title={nextDate ?? undefined}
            >
              Next &rarr;
            </button>
          </div>
        </div>

        {rideLoading && <p className="text-text-muted">Loading ride...</p>}

        {isRideView && ride && (
          <>
            {/* Title */}
            <div className="flex items-baseline gap-2 flex-wrap">
              {editingTitle ? (
                <div className="flex items-center gap-2">
                  <input
                    autoFocus
                    value={titleDraft}
                    onChange={e => setTitleDraft(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        updateTitle.mutate({ id: ride.id, body: { title: titleDraft || null } }, {
                          onSuccess: () => setEditingTitle(false),
                        })
                      } else if (e.key === 'Escape') {
                        setEditingTitle(false)
                      }
                    }}
                    className="text-xl font-semibold text-text bg-surface2 border border-border rounded px-2 py-0.5 focus:outline-none focus:border-accent"
                  />
                  <button
                    onClick={() => {
                      updateTitle.mutate({ id: ride.id, body: { title: titleDraft || null } }, {
                        onSuccess: () => setEditingTitle(false),
                      })
                    }}
                    className="text-xs text-accent hover:underline"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditingTitle(false)}
                    className="text-xs text-text-muted hover:text-text"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div>
                  <h1 className="text-xl font-semibold text-text">
                    {displayTitle}
                    <button
                      onClick={() => { setTitleDraft(ride.title || ride.sport || ''); setEditingTitle(true) }}
                      className="ml-2 text-text-muted hover:text-text transition-colors align-middle"
                      title="Edit title"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                      </svg>
                    </button>
                  </h1>
                  <div className="text-sm text-text-muted mt-1 flex flex-wrap gap-x-4">
                    <span>{ride.date?.slice(0, 10)}{startTime && ` at ${startTime}`}</span>
                    {locationName && <span>{locationName}</span>}
                  </div>
                </div>
              )}
              {plannedWorkout && (
                <span className="text-sm text-yellow font-normal">
                  Planned: {plannedWorkout.name ?? 'Workout'}
                </span>
              )}
            </div>

            {/* Metric cards */}
            {(() => {
              // Compute planned IF from planned TSS and duration
              const pw = plannedWorkout
              const plannedDur = pw?.total_duration_s
              const plannedTss = pw?.planned_tss ? Number(pw.planned_tss) : undefined
              const plannedIF = plannedTss && plannedDur && plannedDur > 0
                ? Math.sqrt(plannedTss / (plannedDur / 3600) / 100)
                : undefined

              return (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <MetricCard
                    label="Duration"
                    value={fmtDuration(ride.duration_s)}
                    planned={plannedDur ? fmtDuration(plannedDur) : null}
                  />
                  <MetricCard label="Distance" value={fmtDistance(ride.distance_m, units)} />
                  <MetricCard
                    label="TSS"
                    value={ride.tss?.toFixed(0) ?? '--'}
                    planned={plannedTss ? plannedTss.toFixed(0) : null}
                  />
                  <MetricCard label="Avg Power" value={ride.avg_power ? `${ride.avg_power}w` : '--'} />
                  <MetricCard label="NP" value={ride.normalized_power ? `${ride.normalized_power}w` : '--'} />
                  <MetricCard label="Avg HR" value={ride.avg_hr ? `${ride.avg_hr} bpm` : '--'} higherIsBetter={false} />
                  <MetricCard
                    label="IF"
                    value={ride.intensity_factor?.toFixed(2) ?? '--'}
                    planned={plannedIF ? plannedIF.toFixed(2) : null}
                  />
                  <MetricCard label="Ascent" value={fmtElevation(ride.total_ascent, units)} />
                </div>
              )
            })()}

            {/* Timeline chart with workout overlay */}
            {ride.records && ride.records.length > 0 && (
              <RideTimelineChart records={ride.records} workout={plannedWorkout ?? undefined} highlightedStep={highlightedStep} />
            )}

            {/* Notes section */}
            <div className="space-y-4">
              {/* Planned workout notes */}
              {plannedWorkout && (
                <div className="space-y-3">
                  {plannedWorkout.coach_notes && (
                    <div>
                      <label className="block text-sm font-medium text-text-muted mb-1">
                        Planned Workout - Coach Notes
                      </label>
                      <div className="bg-surface2 border border-border rounded-lg p-3 text-sm text-text whitespace-pre-wrap">
                        {plannedWorkout.coach_notes}
                      </div>
                    </div>
                  )}
                  {plannedWorkout.athlete_notes && (
                    <div>
                      <label className="block text-sm font-medium text-text-muted mb-1">
                        Planned Workout - Athlete Notes
                      </label>
                      <div className="bg-surface2 border border-border rounded-lg p-3 text-sm text-text whitespace-pre-wrap">
                        {plannedWorkout.athlete_notes}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Post-ride notes (editable) */}
              <div>
                <label className="block text-sm font-medium text-text-muted mb-1">
                  Post-Ride Notes
                </label>
                <textarea
                  value={postRideNotes}
                  onChange={e => { setPostRideNotes(e.target.value); setNotesDirty(true) }}
                  rows={3}
                  className="w-full bg-surface2 border border-border rounded-lg p-3 text-sm text-text placeholder-text-muted resize-y focus:outline-none focus:border-accent"
                  placeholder="How did the ride feel? Any notes..."
                />
                {notesDirty && (
                  <button
                    onClick={handleSaveNotes}
                    disabled={updateComments.isPending}
                    className="mt-2 px-4 py-1.5 rounded-md text-sm font-medium bg-accent text-white hover:bg-accent/80 disabled:opacity-50 transition-colors"
                  >
                    {updateComments.isPending ? 'Saving...' : 'Save Notes'}
                  </button>
                )}
              </div>

              {/* Coach post-ride analysis */}
              {ride.coach_comments && (
                <div>
                  <label className="block text-sm font-medium text-text-muted mb-1">
                    Coach's Post-Ride Analysis
                  </label>
                  <div className="bg-surface2 border border-border rounded-lg p-3 text-sm text-text whitespace-pre-wrap">
                    {ride.coach_comments}
                  </div>
                </div>
              )}

              {/* Get coach feedback button */}
              {!ride.coach_comments && (
                <button
                  onClick={handleGetFeedback}
                  disabled={analyzing}
                  className="px-4 py-2 rounded-md text-sm font-medium bg-yellow text-black hover:opacity-80 disabled:opacity-50 transition-colors"
                >
                  {analyzing ? 'Analyzing...' : 'Get Coach Feedback'}
                </button>
              )}
            </div>

            {/* Workout steps table if planned workout exists */}
            {plannedWorkout && plannedWorkout.steps && plannedWorkout.steps.length > 0 && (
              <WorkoutStepsTable
                steps={plannedWorkout.steps}
                highlightedStep={highlightedStep}
                onHighlight={setHighlightedStep}
              />
            )}
          </>
        )}

        {/* Workout-only view (no completed ride) */}
        {isWorkoutOnly && plannedWorkout && (
          <WorkoutOnlyDetail workout={plannedWorkout} />
        )}

        {/* Loading state for date-only navigation */}
        {selectedDate && !isRideView && !isWorkoutOnly && !rideLoading && (
          <p className="text-text-muted text-sm">No ride or workout found for {selectedDate}.</p>
        )}
      </div>
    )
  }

  // ── List View ──
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-text">Rides</h1>

      {/* Filter row */}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs text-text-muted mb-1">Start Date</label>
          <input
            type="date"
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
            className="bg-surface2 border border-border rounded-md px-2 py-1.5 text-sm text-text focus:outline-none focus:border-accent"
          />
        </div>
        <div>
          <label className="block text-xs text-text-muted mb-1">End Date</label>
          <input
            type="date"
            value={endDate}
            onChange={e => setEndDate(e.target.value)}
            className="bg-surface2 border border-border rounded-md px-2 py-1.5 text-sm text-text focus:outline-none focus:border-accent"
          />
        </div>
        <button
          onClick={handleFilter}
          className="px-4 py-1.5 rounded-md text-sm font-medium bg-accent text-white hover:bg-accent/80 transition-colors"
        >
          Filter
        </button>
      </div>

      {ridesLoading && <p className="text-text-muted text-sm">Loading rides...</p>}

      {rides && rides.length === 0 && (
        <p className="text-text-muted text-sm">No rides found.</p>
      )}

      {rides && rides.length > 0 && (
        <>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-text-muted">
                  <th className="py-2 pr-4 font-medium">Date</th>
                  <th className="py-2 pr-4 font-medium">Sport</th>
                  <th className="py-2 pr-4 font-medium text-right">Duration</th>
                  <th className="py-2 pr-4 font-medium text-right">Distance</th>
                  <th className="py-2 pr-4 font-medium text-right">TSS</th>
                  <th className="py-2 pr-4 font-medium text-right">Avg Power</th>
                  <th className="py-2 pr-4 font-medium text-right">NP</th>
                  <th className="py-2 font-medium text-right">Avg HR</th>
                </tr>
              </thead>
              <tbody>
                {rides.map(r => (
                  <tr
                    key={r.id}
                    onClick={() => setSelectedRideId(r.id)}
                    className="border-b border-border/50 text-text hover:bg-surface2/50 cursor-pointer transition-colors"
                  >
                    <td className="py-2 pr-4">{r.date?.slice(0, 10)}</td>
                    <td className="py-2 pr-4 text-text-muted">{r.sport ?? '--'}</td>
                    <td className="py-2 pr-4 text-right">{fmtDuration(r.duration_s)}</td>
                    <td className="py-2 pr-4 text-right">{fmtDistance(r.distance_m, units)}</td>
                    <td className="py-2 pr-4 text-right">{r.tss?.toFixed(0) ?? '--'}</td>
                    <td className="py-2 pr-4 text-right">{r.avg_power ? `${r.avg_power}w` : '--'}</td>
                    <td className="py-2 pr-4 text-right">{r.normalized_power ? `${r.normalized_power}w` : '--'}</td>
                    <td className="py-2 text-right">{r.avg_hr ? `${r.avg_hr}` : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden space-y-2">
            {rides.map(r => (
              <div
                key={r.id}
                onClick={() => setSelectedRideId(r.id)}
                className="bg-surface border border-border rounded-lg p-3 cursor-pointer hover:bg-surface2/50 transition-colors"
              >
                <div className="flex justify-between items-start mb-1">
                  <span className="text-sm font-medium text-text">{r.date?.slice(0, 10)}</span>
                  <span className="text-xs text-text-muted">{r.sport ?? '--'}</span>
                </div>
                <div className="flex gap-4 text-xs text-text-muted">
                  <span>{fmtDuration(r.duration_s)}</span>
                  <span>{fmtDistance(r.distance_m, units)}</span>
                  {r.tss != null && <span>TSS {r.tss.toFixed(0)}</span>}
                  {r.avg_power != null && <span>{r.avg_power}w</span>}
                  {r.avg_hr != null && <span>{r.avg_hr}bpm</span>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Subcomponents ──

function MetricCard({ label, value, planned, higherIsBetter = true }: {
  label: string
  value: string
  planned?: string | null
  higherIsBetter?: boolean
}) {
  // Parse numeric values for comparison
  let indicator: 'above' | 'below' | 'match' | null = null
  if (planned) {
    const actualNum = parseFloat(value.replace(/[^\d.]/g, ''))
    const plannedNum = parseFloat(planned.replace(/[^\d.]/g, ''))
    if (!isNaN(actualNum) && !isNaN(plannedNum) && plannedNum > 0) {
      const pct = ((actualNum - plannedNum) / plannedNum) * 100
      if (Math.abs(pct) < 3) indicator = 'match'
      else if (actualNum > plannedNum) indicator = 'above'
      else indicator = 'below'
    }
  }

  const indicatorColor = indicator === 'match'
    ? 'text-green'
    : indicator === 'above'
      ? higherIsBetter ? 'text-green' : 'text-yellow'
      : indicator === 'below'
        ? higherIsBetter ? 'text-red' : 'text-green'
        : ''

  const arrow = indicator === 'above' ? '\u25B2' : indicator === 'below' ? '\u25BC' : indicator === 'match' ? '\u2713' : ''

  return (
    <div className="bg-surface border border-border rounded-lg p-3">
      <div className="text-xs text-text-muted mb-1">{label}</div>
      <div className="text-lg font-semibold text-text">
        {value}
        {indicator && <span className={`ml-1.5 text-xs ${indicatorColor}`}>{arrow}</span>}
      </div>
      {planned && (
        <div className="text-xs text-text-muted mt-0.5">
          planned: {planned}
        </div>
      )}
    </div>
  )
}

/** Map each sampled point to its workout step index (or -1). */
function buildStepIndexMap(sampleCount: number, downsampleStep: number, steps: WorkoutStep[]): number[] {
  const map: number[] = []
  for (let i = 0; i < sampleCount; i++) {
    const secs = i * downsampleStep
    let found = -1
    for (let si = 0; si < steps.length; si++) {
      const s = steps[si]
      if (secs >= s.start_s && secs < s.start_s + s.duration_s) {
        found = si
        break
      }
    }
    map.push(found)
  }
  return map
}

/** Store highlight data outside Chart.js options to avoid proxy infinite recursion. */
const highlightDataMap = new WeakMap<ChartJS, {
  activeStep: number | null
  stepIndexMap: number[]
  steps: WorkoutStep[]
}>()

/** Custom Chart.js plugin that draws a highlight overlay on the active workout step. */
const stepHighlightPlugin = {
  id: 'stepHighlight',
  beforeDraw(chart: any) {
    const meta = highlightDataMap.get(chart)
    if (!meta || meta.activeStep == null || !meta.stepIndexMap) return

    const { ctx, chartArea, scales } = chart
    if (!chartArea || !scales?.x) return

    const { activeStep, stepIndexMap, steps } = meta
    if (!steps?.[activeStep]) return

    const xScale = scales.x
    let firstIdx = -1
    let lastIdx = -1
    for (let i = 0; i < stepIndexMap.length; i++) {
      if (stepIndexMap[i] === activeStep) {
        if (firstIdx === -1) firstIdx = i
        lastIdx = i
      }
    }
    if (firstIdx === -1) return

    const x1 = xScale.getPixelForValue(firstIdx)
    const x2 = xScale.getPixelForValue(lastIdx)

    ctx.save()
    ctx.fillStyle = 'rgba(0, 0, 0, 0.35)'
    if (x1 > chartArea.left) {
      ctx.fillRect(chartArea.left, chartArea.top, x1 - chartArea.left, chartArea.bottom - chartArea.top)
    }
    if (x2 < chartArea.right) {
      ctx.fillRect(x2, chartArea.top, chartArea.right - x2, chartArea.bottom - chartArea.top)
    }

    const step = steps[activeStep]
    const color = zoneColor(step.power_pct, 0.8)
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.setLineDash([])
    ctx.beginPath()
    ctx.moveTo(x1, chartArea.top)
    ctx.lineTo(x1, chartArea.bottom)
    ctx.moveTo(x2, chartArea.top)
    ctx.lineTo(x2, chartArea.bottom)
    ctx.stroke()
    ctx.restore()
  },
}

ChartJS.register(stepHighlightPlugin)

function RideTimelineChart({ records, workout, highlightedStep }: {
  records: { timestamp_utc?: string; power?: number; heart_rate?: number; cadence?: number }[]
  workout?: WorkoutDetail
  highlightedStep?: number | null
}) {
  const cc = useChartColors()
  const chartRef = useRef<ChartJS<'line'>>(null)

  // Build chart data (without highlight-dependent colors)
  const { chartData, stepIndexMap } = useMemo(() => {
    const maxPoints = 600
    const step = Math.max(1, Math.floor(records.length / maxPoints))
    const sampled = records.filter((_, i) => i % step === 0)

    const labels = sampled.map((_, i) => {
      const secs = i * step
      const m = Math.floor(secs / 60)
      const h = Math.floor(m / 60)
      if (h > 0) return `${h}:${String(m % 60).padStart(2, '0')}`
      return `${m}m`
    })

    const datasets: any[] = []
    let indexMap: number[] = []

    if (workout && workout.steps && workout.steps.length > 0) {
      indexMap = buildStepIndexMap(sampled.length, step, workout.steps)

      const targetPower = sampled.map((_, i) => {
        const si = indexMap[i]
        return si >= 0 ? workout.steps[si].power_watts : null
      })

      const targetColors = sampled.map((_, i) => {
        const si = indexMap[i]
        if (si < 0) return 'transparent'
        return zoneColor(workout.steps[si].power_pct, 0.2)
      })

      datasets.push({
        label: 'Target Power',
        data: targetPower,
        borderColor: 'rgba(255, 255, 255, 0.4)',
        backgroundColor: targetColors,
        fill: true,
        stepped: 'before' as const,
        borderWidth: 2,
        borderDash: [6, 3],
        pointRadius: 0,
        tension: 0,
        yAxisID: 'y',
        order: 2,
      })
    }

    const hasPower = sampled.some(r => r.power != null)
    const hasHR = sampled.some(r => r.heart_rate != null)
    const hasCadence = sampled.some(r => r.cadence != null)

    if (hasPower) {
      datasets.push({
        label: 'Power (w)',
        data: sampled.map(r => r.power ?? null),
        borderColor: 'rgba(245, 197, 24, 0.9)',
        backgroundColor: 'rgba(245, 197, 24, 0.1)',
        fill: !workout,
        borderWidth: 1,
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'y',
        order: 1,
      })
    }

    if (hasHR) {
      datasets.push({
        label: 'Heart Rate (bpm)',
        data: sampled.map(r => r.heart_rate ?? null),
        borderColor: 'rgba(233, 69, 96, 0.9)',
        backgroundColor: 'transparent',
        fill: false,
        borderWidth: 1,
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'y1',
        order: 1,
      })
    }

    if (hasCadence) {
      datasets.push({
        label: 'Cadence (rpm)',
        data: sampled.map(r => r.cadence ?? null),
        borderColor: 'rgba(126, 200, 227, 0.7)',
        backgroundColor: 'transparent',
        fill: false,
        borderWidth: 1,
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'y2',
        order: 1,
      })
    }

    return { chartData: { labels, datasets }, stepIndexMap: indexMap }
  }, [records, workout])

  // Update highlight data in WeakMap and trigger redraw
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    if (workout?.steps) {
      highlightDataMap.set(chart, {
        activeStep: highlightedStep ?? null,
        stepIndexMap,
        steps: workout.steps,
      })
    }
    chart.update('none')
  }, [highlightedStep, stepIndexMap, workout?.steps])

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      legend: {
        labels: { color: cc.legendColor, font: { size: 11 } },
      },
      tooltip: {
        backgroundColor: cc.tooltipBg,
        titleColor: cc.tooltipTitle,
        bodyColor: cc.tooltipBody,
      },
    },
    scales: {
      x: {
        ticks: { color: cc.tickColor, maxTicksLimit: 12, font: { size: 10 } },
        grid: { color: cc.gridColor },
      },
      y: {
        type: 'linear' as const,
        position: 'left' as const,
        title: { display: true, text: 'Power (w)', color: 'rgba(245, 197, 24, 0.8)', font: { size: 10 } },
        ticks: { color: 'rgba(245, 197, 24, 0.7)', font: { size: 10 } },
        grid: { color: cc.gridColor },
        min: 0,
      },
      y1: {
        type: 'linear' as const,
        position: 'right' as const,
        title: { display: true, text: 'HR (bpm)', color: 'rgba(233, 69, 96, 0.8)', font: { size: 10 } },
        ticks: { color: 'rgba(233, 69, 96, 0.7)', font: { size: 10 } },
        grid: { drawOnChartArea: false },
      },
      y2: {
        type: 'linear' as const,
        display: false,
        min: 0,
        max: 200,
      },
    },
  }), [cc])

  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-text-muted mb-3">
        Ride Timeline
        {workout && <span className="text-yellow ml-2">+ Planned Workout</span>}
      </h2>
      <div className="h-64 sm:h-80">
        <Line ref={chartRef} data={chartData} options={options} />
      </div>
    </div>
  )
}

/** Workout steps table shown below ride detail when there's a planned workout */
function WorkoutStepsTable({ steps, highlightedStep, onHighlight }: {
  steps: WorkoutStep[]
  highlightedStep?: number | null
  onHighlight?: (index: number | null) => void
}) {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-text-muted mb-3">Planned Workout Steps</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-muted text-xs border-b border-border">
              <th className="text-left py-2 px-2 w-6"></th>
              <th className="text-left py-2 px-2">Type</th>
              <th className="text-left py-2 px-2">Time Range</th>
              <th className="text-left py-2 px-2">Duration</th>
              <th className="text-left py-2 px-2">Power</th>
              <th className="text-left py-2 px-2">Zone</th>
            </tr>
          </thead>
          <tbody
            onMouseLeave={() => onHighlight?.(null)}
          >
            {steps.map((step, i) => {
              const isHighlighted = highlightedStep === i
              const isDimmed = highlightedStep != null && highlightedStep !== i
              return (
                <tr
                  key={i}
                  onMouseEnter={() => onHighlight?.(i)}
                  onClick={() => onHighlight?.(isHighlighted ? null : i)}
                  className={`border-b border-border/50 cursor-pointer transition-all duration-150 ${
                    isHighlighted
                      ? 'bg-surface2'
                      : isDimmed
                        ? 'opacity-40'
                        : 'hover:bg-surface2/50'
                  }`}
                >
                  <td className="py-1.5 px-2">
                    <span
                      className="inline-block w-3 h-full rounded-sm"
                      style={{ backgroundColor: zoneColor(step.power_pct, 0.6), minHeight: 20 }}
                    />
                  </td>
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
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** Standalone workout detail view (when no ride exists for the date) */
function WorkoutOnlyDetail({ workout }: { workout: WorkoutDetail }) {
  const cc = useChartColors()
  const updateNotes = useUpdateWorkoutNotes()
  const [athleteNotes, setAthleteNotes] = useState<string | null>(null)
  const [saveStatus, setSaveStatus] = useState('')
  const [highlightedStep, setHighlightedStep] = useState<number | null>(null)

  const notesValue = athleteNotes ?? workout.athlete_notes ?? ''

  const summary = useMemo(() => {
    const { steps, ftp, total_duration_s } = workout
    let weightedSum = 0
    let maxTarget = 0
    for (const step of steps) {
      weightedSum += step.power_watts * step.duration_s
      if (step.power_watts > maxTarget) maxTarget = step.power_watts
    }
    const avgPower = total_duration_s > 0 ? Math.round(weightedSum / total_duration_s) : 0
    const intensityFactor = ftp > 0 ? avgPower / ftp : 0
    const tss = total_duration_s > 0 ? Math.round((total_duration_s * avgPower * intensityFactor) / (ftp * 3600) * 100) : 0
    return { duration: total_duration_s, ftp, avgPower, maxTarget: Math.round(maxTarget), intensityFactor: intensityFactor.toFixed(2), tss }
  }, [workout])

  const workoutChartRef = useRef<ChartJS<'line'>>(null)

  const { chartData, stepIndexMap: woStepMap } = useMemo(() => {
    const labels: string[] = []
    const stepMap: number[] = []
    const SAMPLE = 5
    for (let si = 0; si < workout.steps.length; si++) {
      const step = workout.steps[si]
      const endS = step.start_s + step.duration_s
      for (let t = step.start_s; t < endS; t += SAMPLE) {
        labels.push(fmtTime(t))
        stepMap.push(si)
      }
    }

    // One dataset per step so each interval gets its own zone fill color
    const datasets = workout.steps.map((step, si) => ({
      label: si === 0 ? 'Target Power' : '',
      data: stepMap.map((mappedSi, _i) => mappedSi === si ? step.power_watts : null),
      borderColor: zoneColor(step.power_pct, 0.8),
      backgroundColor: zoneColor(step.power_pct, 0.35),
      fill: true,
      stepped: 'before' as const,
      pointRadius: 0,
      borderWidth: 2,
      tension: 0,
      spanGaps: false,
    }))

    return {
      chartData: { labels, datasets },
      stepIndexMap: stepMap,
    }
  }, [workout])

  // Update highlight data in WeakMap and trigger redraw
  useEffect(() => {
    const chart = workoutChartRef.current
    if (!chart) return
    highlightDataMap.set(chart, {
      activeStep: highlightedStep ?? null,
      stepIndexMap: woStepMap,
      steps: workout.steps,
    })
    chart.update('none')
  }, [highlightedStep, woStepMap, workout.steps])

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        filter: (item: any) => item.parsed.y != null,
        callbacks: { label: (ctx: any) => `${ctx.parsed.y}w` },
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

  const handleSaveNotes = async () => {
    setSaveStatus('')
    try {
      await updateNotes.mutateAsync({ id: workout.id, body: { athlete_notes: notesValue || null } })
      setSaveStatus('Saved!')
      setTimeout(() => setSaveStatus(''), 2000)
    } catch {
      setSaveStatus('Error saving')
    }
  }

  return (
    <>
      <h1 className="text-xl font-semibold text-text">
        {workout.date?.slice(0, 10)} &mdash; {workout.name ?? 'Planned Workout'}
      </h1>

      {/* Summary cards */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
        {[
          { label: 'Duration', value: fmtTime(summary.duration) },
          { label: 'FTP', value: `${summary.ftp}w` },
          { label: 'Avg Power', value: `${summary.avgPower}w` },
          { label: 'Max Target', value: `${summary.maxTarget}w` },
          { label: 'IF (est)', value: summary.intensityFactor },
          { label: 'TSS (est)', value: String(summary.tss) },
        ].map(item => (
          <div key={item.label} className="bg-surface border border-border rounded-lg px-3 py-2 text-center">
            <div className="text-xs text-text-muted">{item.label}</div>
            <div className="text-sm font-semibold text-text">{item.value}</div>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div className="bg-surface border border-border rounded-lg p-4" style={{ height: 280 }}>
        <Line ref={workoutChartRef} data={chartData} options={chartOptions} />
      </div>

      {/* Steps table */}
      <WorkoutStepsTable
        steps={workout.steps}
        highlightedStep={highlightedStep}
        onHighlight={setHighlightedStep}
      />

      {/* Notes */}
      {workout.id && (
        <div className="space-y-4">
          {workout.coach_notes && (
            <div>
              <label className="block text-sm font-medium text-text-muted mb-1">Coach's Notes</label>
              <div className="bg-surface2 border border-border rounded-lg p-3 text-sm text-text whitespace-pre-wrap">
                {workout.coach_notes}
              </div>
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1">Your Pre-Ride Notes</label>
            <textarea
              value={notesValue}
              onChange={e => setAthleteNotes(e.target.value)}
              placeholder="How are you feeling? Any goals for this session?"
              rows={3}
              className="w-full bg-surface2 border border-border rounded-lg p-3 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-accent resize-none"
            />
            <div className="flex items-center gap-3 mt-2">
              <button
                onClick={handleSaveNotes}
                disabled={updateNotes.isPending}
                className="bg-accent text-white px-4 py-1.5 rounded-md text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                {updateNotes.isPending ? 'Saving...' : 'Save'}
              </button>
              {saveStatus && <span className="text-xs text-green">{saveStatus}</span>}
            </div>
          </div>
        </div>
      )}

      {/* Download links */}
      <div className="flex gap-3 border-t border-border pt-4">
        <a href={`/api/plan/workouts/${workout.id}/download?fmt=tcx`} download className="text-sm text-accent hover:underline">
          Download TCX
        </a>
        <a href={`/api/plan/workouts/${workout.id}/download?fmt=zwo`} download className="text-sm text-accent hover:underline">
          Download ZWO
        </a>
      </div>
    </>
  )
}
