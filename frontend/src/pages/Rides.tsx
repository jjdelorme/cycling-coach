import { useState, useEffect, useMemo, useCallback } from 'react'
import { 
  useRides, 
  useRide, 
  useUpdateRideComments, 
  useUpdateRideTitle, 
  useWorkoutByDate, 
  useUpdateWorkoutNotes, 
  useSendChat, 
  useActivityDates 
} from '../hooks/useApi'
import { fmtDuration, fmtDistance, fmtElevation, fmtTime, zoneColor } from '../lib/format'
import { useUnits } from '../lib/units'
import { useQueryClient } from '@tanstack/react-query'
import { 
  Calendar, 
  Clock, 
  Zap, 
  Activity, 
  TrendingUp, 
  Heart, 
  ChevronLeft, 
  ChevronRight, 
  Edit3, 
  Save, 
  MessageSquare, 
  Download,
  MapPin,
  Filter,
  ArrowUpRight,
  ArrowDownRight,
  Info,
  Layers,
  List,
  RefreshCw,
  Target
} from 'lucide-react'
import type { WorkoutDetail, WorkoutStep, RideLap } from '../types/api'
import RideTimelineChart from '../components/RideTimelineChart'

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

  // Highlighting states
  const [hoveredStep, setHoveredStep] = useState<number | null>(null)
  const [selectedStep, setSelectedStep] = useState<number | null>(null)
  const [hoveredLap, setHoveredLap] = useState<number | null>(null)
  const [selectedLap, setSelectedLap] = useState<number | null>(null)

  const queryClient = useQueryClient()
  const { data: rides, isLoading: ridesLoading } = useRides(filterParams)
  const { data: ride, isLoading: rideLoading } = useRide(selectedRideId)
  const updateComments = useUpdateRideComments()
  const sendChat = useSendChat()

  const rideDate = ride?.date?.slice(0, 10) ?? selectedDate
  const { data: plannedWorkout, isLoading: workoutLoading } = useWorkoutByDate(rideDate)

  useEffect(() => {
    if (ride) {
      setPostRideNotes(ride.post_ride_comments ?? '')
      setNotesDirty(false)
    }
  }, [ride?.id, ride?.post_ride_comments])

  useEffect(() => {
    if (initialRideId != null) {
      setSelectedRideId(initialRideId)
      setSelectedDate(null)
    }
  }, [initialRideId])

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

  const showDetail = selectedRideId != null || selectedDate != null
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const updateTitle = useUpdateRideTitle()

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

  const { data: activityDates } = useActivityDates()
  const currentDate = rideDate ?? null
  const { prevDate, nextDate } = useMemo(() => {
    if (!activityDates || !currentDate) return { prevDate: null, nextDate: null }
    const idx = activityDates.indexOf(currentDate)
    if (idx < 0) {
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

    const startTime = (() => {
      if (!isRideView) return null
      const raw = ride?.start_time || ride?.records?.[0]?.timestamp_utc
      if (!raw) return null
      const ts = raw.includes('Z') || raw.includes('+') || raw.includes('T') && raw.match(/[+-]\d{2}:?\d{2}$/)
        ? raw
        : raw + 'Z'
      return new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    })()

    const displayTitle = ride?.title || ride?.sport || 'Cycling'

    return (
      <div className="space-y-6 pb-12">
        {/* Navigation & Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <button 
            onClick={() => { setSelectedRideId(null); setSelectedDate(null) }}
            className="flex items-center gap-2 text-text-muted hover:text-accent transition-colors text-xs font-bold uppercase tracking-widest"
          >
            <ChevronLeft size={14} /> Back to List
          </button>

          <div className="flex items-center bg-surface rounded-lg p-1 border border-border shadow-sm">
            <button
              onClick={() => prevDate && navigateToDate(prevDate)}
              disabled={!prevDate}
              className="p-2 rounded-md transition-all disabled:opacity-20 text-text-muted hover:text-text hover:bg-surface-low"
              title={prevDate ?? undefined}
            >
              <ChevronLeft size={18} />
            </button>
            <div className="px-4 text-center min-w-[140px]">
              <span className="block text-[10px] font-bold text-accent uppercase tracking-tighter">
                {currentDate && new Date(currentDate + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
              </span>
              <span className="text-xs font-mono font-bold text-text">{currentDate ?? ''}</span>
            </div>
            <button
              onClick={() => nextDate && navigateToDate(nextDate)}
              disabled={!nextDate}
              className="p-2 rounded-md transition-all disabled:opacity-20 text-text-muted hover:text-text hover:bg-surface-low"
              title={nextDate ?? undefined}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>

        {(rideLoading || workoutLoading) && (
          <div className="flex items-center justify-center py-24">
            <RefreshCw size={32} className="animate-spin text-accent opacity-50" />
          </div>
        )}

        {isRideView && ride && (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
            {/* Title Section */}
            <div className="flex items-start justify-between flex-wrap gap-4">
              <div className="flex-1 min-w-[300px]">
                {editingTitle ? (
                  <div className="flex items-center gap-3">
                    <input
                      autoFocus
                      value={titleDraft}
                      onChange={e => setTitleDraft(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          updateTitle.mutate({ id: ride.id, body: { title: titleDraft || null } }, {
                            onSuccess: () => setEditingTitle(false),
                          })
                        } else if (e.key === 'Escape') setEditingTitle(false)
                      }}
                      className="text-2xl font-bold text-text bg-surface-low border border-accent rounded-lg px-3 py-1 focus:outline-none w-full max-w-md"
                    />
                    <button
                      onClick={() => updateTitle.mutate({ id: ride.id, body: { title: titleDraft || null } }, { onSuccess: () => setEditingTitle(false) })}
                      className="p-2 bg-accent text-white rounded-lg shadow-lg shadow-accent/20 hover:opacity-90"
                    >
                      <Save size={18} />
                    </button>
                  </div>
                ) : (
                  <div>
                    <h1 className="text-2xl font-bold text-text flex items-center gap-3 group">
                      {displayTitle}
                      <button
                        onClick={() => { setTitleDraft(ride.title || ride.sport || ''); setEditingTitle(true) }}
                        className="p-1.5 text-text-muted hover:text-accent hover:bg-accent/10 rounded-md transition-all opacity-0 group-hover:opacity-100"
                      >
                        <Edit3 size={16} />
                      </button>
                    </h1>
                    <div className="flex items-center gap-4 mt-2 text-text-muted text-xs font-medium">
                      <span className="flex items-center gap-1.5"><Clock size={14} className="text-accent" /> {startTime || 'No start time'}</span>
                      {locationName && <span className="flex items-center gap-1.5"><MapPin size={14} className="text-accent" /> {locationName}</span>}
                    </div>
                  </div>
                )}
              </div>
              {plannedWorkout && (
                <div className="px-4 py-2 bg-yellow/10 border border-yellow/20 rounded-lg flex items-center gap-3">
                  <Activity size={18} className="text-yellow" />
                  <div>
                    <p className="text-[10px] font-bold text-yellow uppercase tracking-widest">Matched Workout</p>
                    <p className="text-sm font-bold text-text">{plannedWorkout.name ?? 'Workout'}</p>
                  </div>
                </div>
              )}
            </div>

            {/* Metric Grid */}
            {(() => {
              const pw = plannedWorkout
              const plannedDur = pw?.total_duration_s
              const plannedTss = pw?.planned_tss ? Number(pw.planned_tss) : undefined
              const plannedIF = plannedTss && plannedDur && plannedDur > 0
                ? Math.sqrt(plannedTss / (plannedDur / 3600) / 100)
                : undefined

              return (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
                  <MetricCard label="Duration" value={fmtDuration(ride.duration_s)} planned={plannedDur ? fmtDuration(plannedDur) : null} icon={Clock} color="text-text" />
                  <MetricCard label="Distance" value={fmtDistance(ride.distance_m, units)} icon={TrendingUp} color="text-text" />
                  <MetricCard label="TSS" value={ride.tss?.toFixed(0) ?? '--'} planned={plannedTss ? plannedTss.toFixed(0) : null} icon={Zap} color="text-accent" />
                  <MetricCard label="Avg Power" value={ride.avg_power ? `${ride.avg_power}w` : '--'} icon={Activity} color="text-blue" />
                  <MetricCard label="NP" value={ride.normalized_power ? `${ride.normalized_power}w` : '--'} icon={ArrowUpRight} color="text-blue" />
                  <MetricCard label="Avg HR" value={ride.avg_hr ? `${ride.avg_hr}bpm` : '--'} higherIsBetter={false} icon={Heart} color="text-red" />
                  <MetricCard label="IF" value={ride.intensity_factor?.toFixed(2) ?? '--'} planned={plannedIF ? plannedIF.toFixed(2) : null} icon={Layers} color="text-text" />
                  <MetricCard label="Ascent" value={fmtElevation(ride.total_ascent, units)} icon={TrendingUp} color="text-green" />
                </div>
              )
            })()}

            {/* Main Timeline Card */}
            {ride.records && ride.records.length > 0 && (
              <RideTimelineChart 
                records={ride.records} 
                laps={ride.laps}
                workout={plannedWorkout ?? undefined} 
                highlightedStep={hoveredStep ?? selectedStep} 
                highlightedLapIndex={hoveredLap ?? selectedLap} 
              />
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* Left Column: Laps & Steps */}
              <div className="lg:col-span-2 space-y-8">
                {ride.laps && ride.laps.length > 1 && (
                  <LapsTable 
                    laps={ride.laps} 
                    highlightedLap={hoveredLap ?? selectedLap} 
                    selectedLap={selectedLap}
                    onHover={setHoveredLap}
                    onSelect={setSelectedLap}
                  />
                )}
                
                {plannedWorkout && plannedWorkout.steps && plannedWorkout.steps.length > 0 && (
                  <WorkoutStepsTable
                    steps={plannedWorkout.steps}
                    highlightedStep={hoveredStep ?? selectedStep}
                    selectedStep={selectedStep}
                    onHover={setHoveredStep}
                    onSelect={setSelectedStep}
                  />
                )}
              </div>

              {/* Right Column: Coaching & Notes */}
              <div className="space-y-6">
                {/* AI Coaching Card */}
                <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm flex flex-col">
                  <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <MessageSquare size={18} className="text-accent" />
                      <h3 className="text-sm font-bold text-text uppercase tracking-wider">AI Coaching</h3>
                    </div>
                    {!ride.coach_comments && (
                      <button
                        onClick={handleGetFeedback}
                        disabled={analyzing}
                        className="px-3 py-1 bg-yellow text-bg rounded-lg text-[10px] font-bold uppercase tracking-widest hover:opacity-90 disabled:opacity-50 transition-all flex items-center gap-1.5"
                      >
                        {analyzing ? <RefreshCw size={12} className="animate-spin" /> : <Zap size={12} />} Analyze
                      </button>
                    )}
                  </div>
                  <div className="p-5">
                    {ride.coach_comments ? (
                      <div className="text-sm text-text leading-relaxed whitespace-pre-wrap italic opacity-90">
                        "{ride.coach_comments}"
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <MessageSquare size={32} className="text-text-muted mx-auto mb-3 opacity-20" />
                        <p className="text-xs text-text-muted font-medium px-4">Get professional insights from your AI coach about this performance.</p>
                      </div>
                    )}
                  </div>
                </section>

                {/* Athlete Notes Card */}
                <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm flex flex-col">
                  <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Edit3 size={18} className="text-blue" />
                      <h3 className="text-sm font-bold text-text uppercase tracking-wider">Athlete Notes</h3>
                    </div>
                    {notesDirty && (
                      <button
                        onClick={handleSaveNotes}
                        disabled={updateComments.isPending}
                        className="p-1.5 bg-accent text-white rounded-lg shadow-lg shadow-accent/20 hover:opacity-90"
                      >
                        <Save size={14} />
                      </button>
                    )}
                  </div>
                  <div className="p-4">
                    <textarea
                      value={postRideNotes}
                      onChange={e => { setPostRideNotes(e.target.value); setNotesDirty(true) }}
                      rows={4}
                      className="w-full bg-surface-low text-text border border-border rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-accent placeholder:text-text-muted/30 resize-none transition-all"
                      placeholder="How did you feel? RPE, fueling, conditions..."
                    />
                  </div>
                </section>

                {/* Planned Notes if any */}
                {plannedWorkout && (plannedWorkout.coach_notes || plannedWorkout.athlete_notes) && (
                  <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm opacity-80">
                    <div className="px-5 py-3 border-b border-border bg-surface-low flex items-center gap-2">
                      <Info size={16} className="text-text-muted" />
                      <h3 className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Pre-Ride Plan</h3>
                    </div>
                    <div className="p-4 space-y-4">
                      {plannedWorkout.coach_notes && (
                        <div className="space-y-1">
                          <p className="text-[9px] font-bold text-accent uppercase tracking-tighter">Coach's Instructions</p>
                          <p className="text-xs text-text-muted leading-relaxed">{plannedWorkout.coach_notes}</p>
                        </div>
                      )}
                      {plannedWorkout.athlete_notes && (
                        <div className="space-y-1">
                          <p className="text-[9px] font-bold text-blue uppercase tracking-tighter">My Objectives</p>
                          <p className="text-xs text-text-muted leading-relaxed">{plannedWorkout.athlete_notes}</p>
                        </div>
                      )}
                    </div>
                  </section>
                )}
              </div>
            </div>
          </div>
        )}

        {isWorkoutOnly && plannedWorkout && (
          <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
            <WorkoutOnlyDetail workout={plannedWorkout} />
          </div>
        )}

        {selectedDate && !isRideView && !isWorkoutOnly && !rideLoading && !workoutLoading && (
          <div className="text-center py-24 bg-surface rounded-xl border border-border border-dashed">
            <Calendar size={48} className="text-text-muted mx-auto mb-4 opacity-10" />
            <p className="text-text-muted font-bold uppercase tracking-widest text-xs">No activity found for {selectedDate}</p>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6 pb-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-text">Rides</h1>
        <div className="flex bg-surface rounded-lg p-1 border border-border shadow-sm">
          <div className="px-3 flex items-center gap-2">
            <Filter size={14} className="text-text-muted" />
            <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest hidden sm:inline">Filter</span>
          </div>
          <input
            type="date"
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
            className="bg-surface-low border-none rounded px-2 py-1 text-xs font-bold text-text focus:ring-0 cursor-pointer"
          />
          <span className="px-1 text-text-muted opacity-30 text-xs self-center">to</span>
          <input
            type="date"
            value={endDate}
            onChange={e => setEndDate(e.target.value)}
            className="bg-surface-low border-none rounded px-2 py-1 text-xs font-bold text-text focus:ring-0 cursor-pointer mr-1"
          />
          <button
            onClick={handleFilter}
            className="px-4 py-1 bg-accent text-white text-[10px] font-bold uppercase tracking-widest rounded-md hover:opacity-90 transition-all shadow-md shadow-accent/10"
          >
            Go
          </button>
        </div>
      </div>

      <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
          <List size={18} className="text-accent" />
          <h2 className="text-sm font-bold text-text uppercase tracking-wider">Activity History</h2>
        </div>
        
        {ridesLoading ? (
          <div className="py-24 text-center text-text-muted animate-pulse font-bold uppercase tracking-widest text-xs italic">Loading activities...</div>
        ) : rides && rides.length === 0 ? (
          <div className="py-24 text-center">
            <Layers size={48} className="text-text-muted mx-auto mb-4 opacity-10" />
            <p className="text-text-muted font-bold uppercase tracking-widest text-xs">No rides match your filters</p>
          </div>
        ) : (
          <>
            {/* Desktop View */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] font-bold text-text-muted uppercase tracking-widest bg-surface-low/50 border-b border-border">
                    <th className="py-3 px-5 text-left">Date</th>
                    <th className="py-3 px-5 text-left">Activity</th>
                    <th className="py-3 px-5 text-right">Duration</th>
                    <th className="py-3 px-5 text-right">Distance</th>
                    <th className="py-3 px-5 text-right">TSS</th>
                    <th className="py-3 px-5 text-right">Power</th>
                    <th className="py-3 px-5 text-right">HR</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {rides?.map(r => (
                    <tr
                      key={r.id}
                      onClick={() => setSelectedRideId(r.id)}
                      className="text-text hover:bg-surface2/50 cursor-pointer transition-all group"
                    >
                      <td className="py-3 px-5 font-mono text-xs font-bold text-text-muted group-hover:text-accent transition-colors">{r.date?.slice(0, 10)}</td>
                      <td className="py-3 px-5">
                        <span className="font-bold">{r.title || r.sport || '--'}</span>
                        {r.sub_sport && <span className="block text-[10px] text-text-muted uppercase tracking-tighter">{r.sub_sport}</span>}
                      </td>
                      <td className="py-3 px-5 text-right font-mono">{fmtDuration(r.duration_s)}</td>
                      <td className="py-3 px-5 text-right font-mono text-xs">{fmtDistance(r.distance_m, units)}</td>
                      <td className="py-3 px-5 text-right font-bold text-accent">{r.tss?.toFixed(0) ?? '--'}</td>
                      <td className="py-3 px-5 text-right">
                        <span className="font-bold text-blue">{r.avg_power ?? '--'}w</span>
                        <span className="text-[10px] text-text-muted ml-1.5 opacity-50">{r.normalized_power ?? '--'}w</span>
                      </td>
                      <td className="py-3 px-5 text-right font-bold text-red">{r.avg_hr ?? '--'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile View */}
            <div className="md:hidden divide-y divide-border/50">
              {rides?.map(r => (
                <div
                  key={r.id}
                  onClick={() => setSelectedRideId(r.id)}
                  className="p-4 active:bg-surface-high transition-colors"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <p className="text-[10px] font-bold text-accent uppercase tracking-tighter mb-0.5">{r.date?.slice(0, 10)}</p>
                      <h3 className="font-bold text-text">{r.title || r.sport || '--'}</h3>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-bold text-accent leading-none">{r.tss?.toFixed(0) ?? '--'}</p>
                      <p className="text-[9px] font-bold text-text-muted uppercase tracking-widest mt-1">TSS</p>
                    </div>
                  </div>
                  <div className="flex gap-4 text-[10px] font-bold text-text-muted uppercase tracking-widest overflow-x-auto no-scrollbar">
                    <span className="flex items-center gap-1"><Clock size={10} /> {fmtDuration(r.duration_s)}</span>
                    <span className="flex items-center gap-1"><TrendingUp size={10} /> {fmtDistance(r.distance_m, units)}</span>
                    <span className="flex items-center gap-1 text-blue"><Activity size={10} /> {r.avg_power ?? '--'}w</span>
                    <span className="flex items-center gap-1 text-red"><Heart size={10} /> {r.avg_hr ?? '--'}</span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function MetricCard({ label, value, planned, higherIsBetter = true, icon: Icon, color }: {
  label: string
  value: string
  planned?: string | null
  higherIsBetter?: boolean
  icon: any
  color?: string
}) {
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

  const indicatorColor = indicator === 'match' ? 'text-green' : indicator === 'above' ? (higherIsBetter ? 'text-green' : 'text-yellow') : (higherIsBetter ? 'text-red' : 'text-green')
  const ArrowIcon = indicator === 'above' ? ArrowUpRight : indicator === 'below' ? ArrowDownRight : null

  return (
    <div className="bg-surface border border-border rounded-xl p-3 shadow-sm hover:border-accent/20 transition-all flex flex-col justify-between h-full">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[9px] font-bold text-text-muted uppercase tracking-widest truncate">{label}</span>
        <Icon size={12} className="text-text-muted opacity-40 shrink-0" />
      </div>
      <div>
        <div className={`text-base font-bold truncate ${color || 'text-text'}`}>
          {value}
          {ArrowIcon && <ArrowIcon size={12} className={`inline ml-1 ${indicatorColor}`} />}
          {indicator === 'match' && <span className="ml-1 text-green">✓</span>}
        </div>
        {planned && (
          <div className="text-[9px] font-bold text-text-muted/50 mt-0.5 truncate">
            Target: {planned}
          </div>
        )}
      </div>
    </div>
  )
}

function LapsTable({ laps, highlightedLap, selectedLap, onHover, onSelect }: { 
  laps: RideLap[]; 
  highlightedLap: number | null; 
  selectedLap: number | null;
  onHover: (index: number | null) => void;
  onSelect: (index: number | null) => void;
}) {
  const units = useUnits()
  const fmtLap = (s?: number) => { if (!s) return '-'; const m = Math.floor(s / 60); return `${m}:${Math.round(s % 60).toString().padStart(2, '0')}` }
  return (
    <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
        <Layers size={18} className="text-blue" />
        <h3 className="text-sm font-bold text-text uppercase tracking-wider">Interval Laps</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="text-[10px] font-bold text-text-muted uppercase tracking-widest bg-surface-low/50 border-b border-border">
              <th className="py-3 px-5">#</th>
              <th className="py-3 px-5">Duration</th>
              <th className="py-3 px-5">Distance</th>
              <th className="py-3 px-5 text-right">Power</th>
              <th className="py-3 px-5 text-right">NP</th>
              <th className="py-3 px-5 text-right">HR</th>
              <th className="py-3 px-5 text-center">Type</th>
            </tr>
          </thead>
          <tbody 
            onMouseLeave={() => onHover(null)}
            className="divide-y divide-border/50"
          >
            {laps.map((lap, i) => {
              const isH = highlightedLap === i
              const isS = selectedLap === i
              const isD = highlightedLap !== null && highlightedLap !== i
              const isRest = lap.intensity === 'rest' || (lap.lap_trigger === 'session_end' && laps.length > 1)
              return (
                <tr 
                  key={lap.lap_index} 
                  onMouseEnter={() => onHover(i)}
                  onClick={() => onSelect(isS ? null : i)}
                  className={`text-text transition-all duration-200 cursor-pointer ${isS ? 'bg-accent/10' : isH ? 'bg-accent/5' : isD ? 'opacity-30 grayscale' : 'hover:bg-surface2/30'} ${isRest && !isH && !isS ? 'opacity-50' : ''}`}
                >
                  <td className="py-2.5 px-5 font-mono text-text-muted">{lap.lap_index + 1}</td>
                  <td className="py-2.5 px-5 font-bold">{fmtLap(lap.total_timer_time)}</td>
                  <td className="py-2.5 px-5 text-text-muted">{lap.total_distance ? fmtDistance(lap.total_distance, units) : '-'}</td>
                  <td className="py-2.5 px-5 text-right font-bold text-blue">{lap.avg_power ?? '-'}{lap.avg_power ? 'w' : ''}</td>
                  <td className="py-2.5 px-5 text-right text-text-muted">{lap.normalized_power ?? '-'}{lap.normalized_power ? 'w' : ''}</td>
                  <td className="py-2.5 px-5 text-right font-bold text-red">{lap.avg_hr ?? '-'}{lap.avg_hr ? 'bpm' : ''}</td>
                  <td className="py-2.5 px-5 text-center">
                    {lap.intensity === 'active' ? <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-widest bg-green/10 text-green border border-green/20">Active</span> : isRest ? <span className="px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-widest bg-blue/10 text-blue border border-blue/20">Rest</span> : null}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function WorkoutStepsTable({ steps, highlightedStep, selectedStep, onHover, onSelect }: { 
  steps: WorkoutStep[]; 
  highlightedStep: number | null; 
  selectedStep: number | null;
  onHover: (index: number | null) => void;
  onSelect: (index: number | null) => void;
}) {
  return (
    <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
        <Target size={18} className="text-yellow" />
        <h3 className="text-sm font-bold text-text uppercase tracking-wider">Planned Intervals</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="text-[10px] font-bold text-text-muted uppercase tracking-widest bg-surface-low/50 border-b border-border">
              <th className="py-3 px-5 w-12">Zone</th>
              <th className="py-3 px-5">Type</th>
              <th className="py-3 px-5">Time</th>
              <th className="py-3 px-5">Duration</th>
              <th className="py-3 px-5 text-right">Target Power</th>
            </tr>
          </thead>
          <tbody onMouseLeave={() => onHover(null)} className="divide-y divide-border/50">
            {steps.map((step, i) => {
              const isH = highlightedStep === i
              const isS = selectedStep === i
              const isD = highlightedStep != null && highlightedStep !== i
              return (
                <tr key={i} onMouseEnter={() => onHover(i)} onClick={() => onSelect(isS ? null : i)} className={`cursor-pointer transition-all duration-200 ${isS ? 'bg-accent/10' : isH ? 'bg-accent/5' : isD ? 'opacity-30 grayscale' : 'hover:bg-surface2/30'}`}>
                  <td className="py-3 px-5"><div className="w-full h-1.5 rounded-full shadow-[0_0_8px] shadow-current" style={{ backgroundColor: zoneColor(step.power_pct), color: zoneColor(step.power_pct) }} /></td>
                  <td className="py-3 px-5 font-bold text-text uppercase text-[10px] tracking-widest">{step.type}</td>
                  <td className="py-3 px-5 font-mono text-xs text-text-muted">{fmtTime(step.start_s)} - {fmtTime(step.start_s + step.duration_s)}</td>
                  <td className="py-3 px-5 font-bold text-text">{fmtTime(step.duration_s)}</td>
                  <td className="py-3 px-5 text-right font-mono font-bold text-blue">{step.power_watts}w <span className="text-[10px] text-text-muted opacity-50 ml-1">({Math.round(step.power_pct * 100)}%)</span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function WorkoutOnlyDetail({ workout }: { workout: WorkoutDetail }) {
  const updateNotes = useUpdateWorkoutNotes(), [athleteNotes, setAthleteNotes] = useState<string | null>(null), [saveStatus, setSaveStatus] = useState('')
  const [hoveredStep, setHoveredStep] = useState<number | null>(null)
  const [selectedStep, setSelectedStep] = useState<number | null>(null)
  const nVal = athleteNotes ?? workout.athlete_notes ?? ''
  
  const summary = useMemo(() => { const { steps, ftp, total_duration_s } = workout; let ws = 0, mt = 0; for (const s of steps) { ws += s.power_watts * s.duration_s; if (s.power_watts > mt) mt = s.power_watts } const ap = total_duration_s > 0 ? Math.round(ws / total_duration_s) : 0, ifac = ftp > 0 ? ap / ftp : 0; return { duration: total_duration_s, ftp, ap, mt: Math.round(mt), ifac: ifac.toFixed(2), tss: total_duration_s > 0 ? Math.round((total_duration_s * ap * ifac) / (ftp * 3600) * 100) : 0 } }, [workout])
  
  const hS = async () => { setSaveStatus(''); try { await updateNotes.mutateAsync({ id: workout.id, body: { athlete_notes: nVal || null } }); setSaveStatus('SAVED'); setTimeout(() => setSaveStatus(''), 2000) } catch { setSaveStatus('ERROR') } }

  return (
    <div className="space-y-8 pb-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold text-accent uppercase tracking-[0.2em] mb-1">Upcoming Performance</p>
          <h1 className="text-3xl font-bold text-text">{workout.name ?? 'Planned Workout'}</h1>
        </div>
        <div className="flex gap-3">
          <a href={`/api/plan/workouts/${workout.id}/download?fmt=tcx`} download className="flex items-center gap-2 px-4 py-2 bg-surface border border-border rounded-lg text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-accent hover:border-accent transition-all shadow-sm">
            <Download size={14} /> TCX
          </a>
          <a href={`/api/plan/workouts/${workout.id}/download?fmt=zwo`} download className="flex items-center gap-2 px-4 py-2 bg-surface border border-border rounded-lg text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-accent hover:border-accent transition-all shadow-sm">
            <Download size={14} /> ZWO
          </a>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MetricCard label="Duration" value={fmtTime(summary.duration)} icon={Clock} color="text-text" />
        <MetricCard label="FTP" value={`${summary.ftp}w`} icon={Zap} color="text-text" />
        <MetricCard label="Avg Target" value={`${summary.ap}w`} icon={Activity} color="text-blue" />
        <MetricCard label="Peak Target" value={`${summary.mt}w`} icon={ArrowUpRight} color="text-blue" />
        <MetricCard label="Est. IF" value={summary.ifac} icon={Layers} color="text-text" />
        <MetricCard label="Est. TSS" value={String(summary.tss)} icon={Zap} color="text-accent" />
      </div>

      <RideTimelineChart 
        records={[]} 
        laps={[]} 
        workout={workout} 
        highlightedStep={hoveredStep ?? selectedStep} 
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <WorkoutStepsTable 
            steps={workout.steps} 
            highlightedStep={hoveredStep ?? selectedStep} 
            selectedStep={selectedStep}
            onHover={setHoveredStep}
            onSelect={setSelectedStep}
          />
        </div>
        <div className="space-y-6">
          <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
            <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center justify-between">
              <div className="flex items-center gap-2"><Edit3 size={18} className="text-accent" /><h3 className="text-sm font-bold text-text uppercase tracking-wider">Objectives</h3></div>
              {athleteNotes !== null && <button onClick={hS} disabled={updateNotes.isPending} className="p-1.5 bg-accent text-white rounded-lg shadow-lg shadow-accent/20"><Save size={14} /></button>}
            </div>
            <div className="p-4"><textarea value={nVal} onChange={e => setAthleteNotes(e.target.value)} placeholder="Strategy, fueling goals, or focus areas..." rows={5} className="w-full bg-surface-low text-text border border-border rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-accent placeholder:text-text-muted/30 resize-none transition-all leading-relaxed" />{saveStatus && <p className="text-[10px] font-bold text-green mt-2 animate-in fade-in">✓ {saveStatus}</p>}</div>
          </section>
          {workout.coach_notes && (
            <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm opacity-90">
              <div className="px-5 py-3 border-b border-border bg-surface-low flex items-center gap-2"><Info size={16} className="text-yellow" /><h3 className="text-[10px] font-bold text-text uppercase tracking-wider">Coach Guidance</h3></div>
              <div className="p-5 italic text-sm text-text-muted leading-relaxed whitespace-pre-wrap">"{workout.coach_notes}"</div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
