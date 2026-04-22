import { useSyncSingleRide } from '../hooks/useSyncSingleRide'
import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  useRides,
  useRide,
  useUpdateRideComments,
  useUpdateRideTitle,
  useDeleteRide,
  useWorkoutByDate,
  useUpdateWorkoutNotes,
  useSendChat
} from '../hooks/useApi'
import { fmtDuration, fmtDistance, fmtElevation, fmtTime, zoneColor, fmtSport, fmtTimestamp } from '../lib/format'
import { useUnits } from '../lib/units'
import { useQueryClient } from '@tanstack/react-query'
import {
  Calendar,
  Clock,
  Zap,
  Activity,
  TrendingUp,
  Heart,
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
  Search,
  Target,
  Trash2,
  Flame,
  ChevronDown,
  ChevronUp,
  X
} from 'lucide-react'
import SportIcon from '../components/SportIcon'
import DayDetailShell from '../components/DayDetailShell'
import type { WorkoutDetail, WorkoutStep, RideLap } from '../types/api'
import RideTimelineChart from '../components/RideTimelineChart'
import { calculateStepActuals } from '../lib/workout-utils'

/**
 * Rides page — list view + ride/workout-by-date detail view.
 *
 * Detail selection is now URL-driven:
 *   - `/rides`            → list view
 *   - `/rides/:id`        → detail for a specific recorded ride
 *   - `/rides/by-date/:date` → detail for a planned workout (or "no activity")
 *                              on the given YYYY-MM-DD
 */
export default function Rides() {
  const units = useUnits()
  const navigate = useNavigate()
  const params = useParams<{ id?: string; date?: string }>()

  const selectedRideId = params.id ? Number(params.id) : null
  const selectedDate = params.date ?? null

  // URL-driven setters — navigate instead of mutating local state.
  const handleSetSelectedRideId = (id: number | null) => {
    if (id == null) navigate('/rides')
    else navigate(`/rides/${id}`)
  }

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [searchText, setSearchText] = useState('')
  // Geo / radius filter state
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [searchPlace, setSearchPlace] = useState('')
  const [radiusValue, setRadiusValue] = useState<string>('25')
  const [radiusUnit, setRadiusUnit] = useState<'km' | 'mi'>(units === 'imperial' ? 'mi' : 'km')
  const [nearLat, setNearLat] = useState<number | null>(null)
  const [nearLon, setNearLon] = useState<number | null>(null)
  const [geoError, setGeoError] = useState<string | null>(null)
  const [resolvedPlace, setResolvedPlace] = useState<string | null>(null)
  const [resolvedRadiusKm, setResolvedRadiusKm] = useState<number | null>(null)
  const [filterParams, setFilterParams] = useState<{
    start_date?: string
    end_date?: string
    q?: string
    near?: string
    near_lat?: number
    near_lon?: number
    radius_km?: number
  }>({})
  const [postRideNotes, setPostRideNotes] = useState('')
  const [notesDirty, setNotesDirty] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)

  // Highlighting states
  const [hoveredStep, setHoveredStep] = useState<number | null>(null)
  const [selectedStep, setSelectedStep] = useState<number | null>(null)
  const [hoveredLap, setHoveredLap] = useState<number | null>(null)
  const [selectedLap, setSelectedLap] = useState<number | null>(null)

  const queryClient = useQueryClient()
  const { data: rides, isLoading: ridesLoading, error: ridesError } = useRides(filterParams)
  const { data: ride, isLoading: rideLoading } = useRide(selectedRideId)
  const updateComments = useUpdateRideComments()
  const deleteRideMutation = useDeleteRide()
  const sendChat = useSendChat()

  // Only use ride.date if we're actually viewing a ride (not stale data when selectedRideId is null)
  const rideDate = (selectedRideId !== null && ride?.date) ? ride.date.slice(0, 10) : selectedDate
  const { data: plannedWorkout, isLoading: workoutLoading } = useWorkoutByDate(rideDate)

  async function handleDeleteRide() {
    if (selectedRideId == null) return
    if (!window.confirm("Are you sure you want to delete this ride? This will permanently remove its data and recalculate your Fitness/Fatigue metrics from this date forward.")) return
    
    try {
      await deleteRideMutation.mutateAsync(selectedRideId)
      handleSetSelectedRideId(null)
    } catch {
      alert("Failed to delete ride")
    }
  }

  useEffect(() => {
    if (ride) {
      setPostRideNotes(ride.post_ride_comments ?? '')
      setNotesDirty(false)
    }
  }, [ride])

  useEffect(() => {
    if (ridesError && (filterParams.near || filterParams.near_lat !== undefined)) {
      setGeoError((ridesError as Error).message || 'Could not resolve location')
    }
  }, [ridesError, filterParams.near, filterParams.near_lat])

  function handleFilter() {
    const params: {
      start_date?: string
      end_date?: string
      q?: string
      near?: string
      near_lat?: number
      near_lon?: number
      radius_km?: number
    } = {}
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    const trimmed = searchText.trim()
    if (trimmed) params.q = trimmed

    // Geo / radius
    setGeoError(null)
    const placeTrim = searchPlace.trim()
    const hasCoords = nearLat !== null && nearLon !== null
    const radiusNum = Number(radiusValue)
    const radiusKm = Number.isFinite(radiusNum) && radiusNum > 0
      ? (radiusUnit === 'mi' ? radiusNum * 1.609344 : radiusNum)
      : null

    if (placeTrim || hasCoords) {
      if (radiusKm === null) {
        setGeoError('Radius must be a positive number')
        return
      }
      if (radiusKm > 500) {
        setGeoError('Radius must be 500 km or less')
        return
      }
      params.radius_km = Math.round(radiusKm * 100) / 100
      if (hasCoords) {
        params.near_lat = nearLat as number
        params.near_lon = nearLon as number
        setResolvedPlace(placeTrim || `${(nearLat as number).toFixed(3)}, ${(nearLon as number).toFixed(3)}`)
      } else {
        params.near = placeTrim
        setResolvedPlace(placeTrim)
      }
      setResolvedRadiusKm(params.radius_km)
    } else {
      setResolvedPlace(null)
      setResolvedRadiusKm(null)
    }

    setFilterParams(params)
  }

  function clearGeoFilter() {
    setSearchPlace('')
    setNearLat(null)
    setNearLon(null)
    setGeoError(null)
    setResolvedPlace(null)
    setResolvedRadiusKm(null)
    setFilterParams(prev => {
      const next = { ...prev }
      delete next.near
      delete next.near_lat
      delete next.near_lon
      delete next.radius_km
      return next
    })
  }

  function useMyLocation() {
    if (!('geolocation' in navigator)) {
      setGeoError('Geolocation is not supported by this browser')
      return
    }
    setGeoError(null)
    navigator.geolocation.getCurrentPosition(
      pos => {
        setNearLat(pos.coords.latitude)
        setNearLon(pos.coords.longitude)
        setSearchPlace('')
      },
      err => {
        setGeoError(`Could not get current location: ${err.message}`)
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    )
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

const syncSingleRide = useSyncSingleRide()


  const [locationName, setLocationName] = useState<string | null>(null)
  useEffect(() => {
    if (!ride?.start_lat || !ride?.start_lon) {
      setLocationName(null)
      return
    }
    let cancelled = false
    fetch(`https://nominatim.openstreetmap.org/reverse?lat=${ride.start_lat}&lon=${ride.start_lon}&format=json&zoom=12`)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return
        const addr = data.address || {}
        const locality = addr.city || addr.town || addr.village || addr.hamlet || addr.suburb || addr.county
        const region = addr.state_code || addr.state
        const parts = [locality, region].filter(Boolean)
        setLocationName(parts.join(', ') || data.display_name?.split(',').slice(0, 2).join(',') || null)
      })
      .catch(() => { if (!cancelled) setLocationName(null) })
    return () => { cancelled = true }
  }, [ride?.start_lat, ride?.start_lon])

  const currentDate = rideDate ?? null

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
      return fmtTimestamp(ts)
    })()

    const displayTitle = ride?.title || fmtSport(ride?.sport)

    return (
      <DayDetailShell currentDate={currentDate} backTo={{ href: '/rides', label: 'Back to List' }}>
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
                      <SportIcon sport={ride.sport} size={28} className="text-accent" />
                      {displayTitle}
                      <button
                        onClick={() => { setTitleDraft(ride.title || ride.sport || ''); setEditingTitle(true) }}
                        className="p-1.5 text-text-muted hover:text-accent hover:bg-accent/10 rounded-md transition-all opacity-0 group-hover:opacity-100"
                      >
                        <Edit3 size={16} />
                      </button>
                    </h1>
                    <div className="flex items-center gap-2 mt-3">
                      {ride?.filename?.startsWith('icu_') && (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => syncSingleRide.mutate(ride.filename!.replace('icu_', ''))}
                            disabled={syncSingleRide.isPending}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface text-[10px] font-bold text-text-muted hover:text-accent border border-border rounded-lg transition-colors uppercase tracking-widest disabled:opacity-50"
                          >
                            <RefreshCw size={12} className={syncSingleRide.isPending ? 'animate-spin' : ''} />
                            {syncSingleRide.isPending ? 'Syncing...' : 'Re-sync Ride'}
                          </button>
                          {syncSingleRide.isError && (
                            <span className="text-red text-[10px] font-bold px-2 py-1 bg-red/10 rounded-lg max-w-[200px] truncate" title={syncSingleRide.error?.message || 'Sync failed'}>
                              Error
                            </span>
                          )}
                          {syncSingleRide.isSuccess && (
                            <span className="text-green text-[10px] font-bold px-2 py-1 bg-green/10 rounded-lg">
                              Synced!
                            </span>
                          )}
                        </div>
                      )}
                      <button
                        onClick={handleDeleteRide}
                        disabled={deleteRideMutation.isPending}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-surface text-[10px] font-bold text-red hover:bg-red/10 border border-border rounded-lg transition-colors uppercase tracking-widest disabled:opacity-50"
                        title="Delete Ride"
                      >
                        <Trash2 size={12} className={deleteRideMutation.isPending ? 'animate-pulse' : ''} />
                        {deleteRideMutation.isPending ? 'Deleting...' : 'Delete Ride'}
                      </button>
                    </div>

                    <div className="flex items-center gap-4 mt-3 text-text-muted text-xs font-medium">
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

              const plannedAvgPower = pw?.steps?.length ? (() => {
                let ws = 0
                let totalDur = 0
                for (const s of pw.steps) {
                  ws += s.power_watts * s.duration_s
                  totalDur += s.duration_s
                }
                return totalDur > 0 ? Math.round(ws / totalDur) : undefined
              })() : undefined


              return (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
                  <MetricCard label="Duration" value={fmtDuration(ride.duration_s)} planned={plannedDur ? fmtDuration(plannedDur) : null} icon={Clock} color="text-text" />
                  <MetricCard label="Distance" value={fmtDistance(ride.distance_m, units)} icon={TrendingUp} color="text-text" />
                  <MetricCard label="TSS" value={ride.tss?.toFixed(0) ?? '--'} planned={plannedTss ? plannedTss.toFixed(0) : null} icon={Zap} color="text-accent" />
                  <MetricCard label="Power" value={ride.avg_power ? `${ride.avg_power}w AVG` : '--'} secondaryValue={ride.normalized_power ? `${ride.normalized_power}w NP` : undefined} color="text-blue/60" secondaryColor="text-blue" planned={plannedAvgPower ? `${plannedAvgPower}w` : null} icon={Activity} />
                  <MetricCard label="Avg HR" value={ride.avg_hr ? `${ride.avg_hr}bpm` : '--'} higherIsBetter={false} icon={Heart} color="text-red" />
                  <MetricCard label="IF" value={ride.intensity_factor?.toFixed(2) ?? '--'} planned={plannedIF ? plannedIF.toFixed(2) : null} icon={Layers} color="text-text" />
                  <MetricCard label="Ascent" value={fmtElevation(ride.total_ascent, units)} icon={TrendingUp} color="text-green" />
                  <MetricCard label="Calories" value={ride.total_calories ? `${ride.total_calories.toLocaleString()} kcal` : '--'} icon={Flame} color="text-orange-400" />
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
                selectedStep={selectedStep}
                selectedLapIndex={selectedLap}
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
                    records={ride.records}
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
                      <div className="text-base md:text-sm text-text leading-relaxed prose prose-sm prose-invert max-w-none
                        [&_p]:my-1.5 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5
                        [&_li]:my-1 [&_li]:pl-1 [&_strong]:text-accent [&_strong]:font-bold
                        [&_h1]:text-lg [&_h1]:font-bold [&_h1]:mt-3 [&_h1]:mb-1
                        [&_h2]:text-base [&_h2]:font-bold [&_h2]:mt-3 [&_h2]:mb-1
                        [&_h3]:text-sm [&_h3]:font-bold [&_h3]:mt-2 [&_h3]:mb-1 [&_h3]:uppercase [&_h3]:tracking-wide
                        [&_code]:bg-surface-low [&_code]:px-1 [&_code]:rounded [&_code]:text-blue
                        coach-prose">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{ride.coach_comments}</ReactMarkdown>
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
                      className="w-full bg-surface-low text-text border border-border rounded-lg px-4 py-3 text-base md:text-sm focus:outline-none focus:border-accent placeholder:text-text-muted/30 resize-none transition-all"
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
                          <p className="text-sm md:text-xs text-text-muted leading-relaxed">{plannedWorkout.coach_notes}</p>
                        </div>
                      )}
                      {plannedWorkout.athlete_notes && (
                        <div className="space-y-1">
                          <p className="text-[9px] font-bold text-blue uppercase tracking-tighter">My Objectives</p>
                          <p className="text-sm md:text-xs text-text-muted leading-relaxed">{plannedWorkout.athlete_notes}</p>
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
      </DayDetailShell>
    )
  }

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h1 className="text-2xl font-bold text-text">Rides</h1>
        <div className="flex flex-wrap bg-surface rounded-lg p-1 border border-border shadow-sm gap-1">
          <div className="px-2 flex items-center gap-2">
            <Search size={14} className="text-text-muted" />
            <input
              type="text"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleFilter() }}
              placeholder="Search by name or notes..."
              aria-label="Search rides by name or notes"
              className="bg-surface-low border-none rounded px-2 py-1 text-xs font-medium text-text focus:ring-0 placeholder:text-text-muted/50 w-44 sm:w-56"
            />
            {searchText && (
              <button
                onClick={() => {
                  setSearchText('')
                  setFilterParams(prev => { const { q, ...rest } = prev; return rest })
                }}
                aria-label="Clear search"
                className="text-text-muted hover:text-text"
              >
                <X size={13} />
              </button>
            )}
          </div>
          <div className="w-px bg-border/50 mx-1 self-stretch hidden sm:block" />
          <div className="px-2 flex items-center gap-2">
            <Filter size={14} className="text-text-muted" />
            <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest hidden sm:inline">Date</span>
          </div>
          <input
            type="date"
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleFilter() }}
            className="bg-surface-low border-none rounded px-2 py-1 text-xs font-bold text-text focus:ring-0 cursor-pointer"
          />
          <span className="px-1 text-text-muted opacity-30 text-xs self-center">to</span>
          <input
            type="date"
            value={endDate}
            onChange={e => setEndDate(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleFilter() }}
            className="bg-surface-low border-none rounded px-2 py-1 text-xs font-bold text-text focus:ring-0 cursor-pointer mr-1"
          />
          <button
            onClick={handleFilter}
            className="px-4 py-1 bg-accent text-white text-[10px] font-bold uppercase tracking-widest rounded-md hover:opacity-90 transition-all shadow-md shadow-accent/10"
          >
            Go
          </button>
          <button
            onClick={() => setShowAdvanced(v => !v)}
            aria-expanded={showAdvanced}
            aria-controls="rides-advanced-panel"
            className="ml-1 flex items-center gap-1 px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-accent transition-colors"
            title="Advanced filters"
          >
            Advanced {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </div>
      </div>

      {showAdvanced && (
        <div
          id="rides-advanced-panel"
          className="bg-surface rounded-lg border border-border shadow-sm p-4 animate-in fade-in slide-in-from-top-1 duration-200"
        >
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest" htmlFor="rides-place-input">
                Place
              </label>
              <input
                id="rides-place-input"
                type="text"
                value={searchPlace}
                onChange={e => { setSearchPlace(e.target.value); setNearLat(null); setNearLon(null) }}
                onKeyDown={e => { if (e.key === 'Enter') handleFilter() }}
                placeholder="e.g. Santa Fe, NM"
                aria-label="Search rides near a place"
                className="bg-surface-low border border-border rounded px-3 py-1.5 text-xs font-medium text-text focus:outline-none focus:border-accent placeholder:text-text-muted/50 w-56"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest" htmlFor="rides-radius-input">
                Radius
              </label>
              <div className="flex items-center gap-1">
                <input
                  id="rides-radius-input"
                  type="number"
                  min={1}
                  max={radiusUnit === 'mi' ? 310 : 500}
                  step={1}
                  value={radiusValue}
                  onChange={e => setRadiusValue(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleFilter() }}
                  className="bg-surface-low border border-border rounded px-2 py-1.5 text-xs font-bold text-text focus:outline-none focus:border-accent w-20"
                />
                <select
                  value={radiusUnit}
                  onChange={e => setRadiusUnit(e.target.value as 'km' | 'mi')}
                  className="bg-surface-low border border-border rounded px-2 py-1.5 text-xs font-bold text-text focus:outline-none focus:border-accent"
                  aria-label="Radius unit"
                >
                  <option value="km">km</option>
                  <option value="mi">mi</option>
                </select>
              </div>
            </div>
            <div className="flex items-end gap-2">
              <button
                onClick={useMyLocation}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-low border border-border rounded text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-accent hover:border-accent transition-all"
                title="Use my current location"
              >
                <MapPin size={12} /> Use My Location
              </button>
              <button
                onClick={handleFilter}
                className="px-3 py-1.5 bg-accent text-white text-[10px] font-bold uppercase tracking-widest rounded hover:opacity-90 transition-all shadow-sm"
              >
                Apply
              </button>
              {(resolvedPlace || nearLat !== null || searchPlace) && (
                <button
                  onClick={clearGeoFilter}
                  className="flex items-center gap-1 px-2 py-1.5 text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-red transition-colors"
                  title="Clear location filter"
                >
                  <X size={12} /> Clear
                </button>
              )}
            </div>
          </div>
          {nearLat !== null && nearLon !== null && (
            <p className="mt-2 text-[10px] text-text-muted font-medium">
              Using current location: {nearLat.toFixed(4)}, {nearLon.toFixed(4)}
            </p>
          )}
          {geoError && (
            <p className="mt-2 text-[11px] text-red font-bold">{geoError}</p>
          )}
        </div>
      )}

      {resolvedPlace && resolvedRadiusKm !== null && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-accent/5 border border-accent/20 rounded-lg w-fit">
          <MapPin size={12} className="text-accent" />
          <span className="text-[11px] font-bold text-text">
            Showing rides within{' '}
            {radiusUnit === 'mi'
              ? `${(resolvedRadiusKm / 1.609344).toFixed(0)} mi`
              : `${resolvedRadiusKm.toFixed(0)} km`}{' '}
            of {resolvedPlace}
          </span>
          <button
            onClick={clearGeoFilter}
            className="ml-1 text-text-muted hover:text-red transition-colors"
            aria-label="Clear location filter"
          >
            <X size={12} />
          </button>
        </div>
      )}

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
                      onClick={() => handleSetSelectedRideId(r.id)}
                      className="text-text hover:bg-surface2/50 cursor-pointer transition-all group"
                    >
                      <td className="py-3 px-5 font-mono text-xs font-bold text-text-muted group-hover:text-accent transition-colors">{r.date?.slice(0, 10)}</td>
                      <td className="py-3 px-5">
                        <div className="flex items-center gap-2">
                          <SportIcon sport={r.sport} size={16} />
                          <div>
                            <span className="font-bold">{r.title || fmtSport(r.sport)}</span>
                            {r.sub_sport && <span className="block text-[10px] text-text-muted uppercase tracking-tighter">{fmtSport(r.sub_sport)}</span>}
                          </div>
                        </div>
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
                  onClick={() => handleSetSelectedRideId(r.id)}
                  className="p-4 active:bg-surface-high transition-colors"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex items-center gap-3">
                      <SportIcon sport={r.sport} size={20} className="text-accent" />
                      <div>
                        <p className="text-[10px] font-bold text-accent uppercase tracking-tighter mb-0.5">{r.date?.slice(0, 10)}</p>
                        <h3 className="font-bold text-text">{r.title || fmtSport(r.sport)}</h3>
                      </div>
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

function MetricCard({ label, value, secondaryValue, secondaryColor, planned, higherIsBetter = true, icon: Icon, color }: {
  label: string
  value: string
  secondaryValue?: string
  secondaryColor?: string
  planned?: string | null
  higherIsBetter?: boolean
  icon: React.ElementType
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
        {secondaryValue ? (
          <div className="flex flex-col gap-0.5">
            <div className={`text-sm font-bold truncate ${color || 'text-text'}`}>
              {value}
              {ArrowIcon && <ArrowIcon size={11} className={`inline ml-1 ${indicatorColor}`} />}
              {indicator === 'match' && <span className="ml-1 text-green">✓</span>}
            </div>
            <div className={`text-sm font-bold truncate ${secondaryColor || 'text-text-muted'}`}>{secondaryValue}</div>
          </div>
        ) : (
          <div className={`text-base font-bold truncate ${color || 'text-text'}`}>
            {value}
            {ArrowIcon && <ArrowIcon size={12} className={`inline ml-1 ${indicatorColor}`} />}
            {indicator === 'match' && <span className="ml-1 text-green">✓</span>}
          </div>
        )}
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
                  <td className="py-2.5 px-5 font-bold">{lap.total_timer_time != null ? fmtTime(lap.total_timer_time) : '-'}</td>
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

function WorkoutStepsTable({ steps, records, highlightedStep, selectedStep, onHover, onSelect }: { 
  steps: WorkoutStep[]; 
  records?: { power?: number, timestamp_utc?: string }[];
  highlightedStep: number | null; 
  selectedStep: number | null;
  onHover: (index: number | null) => void;
  onSelect: (index: number | null) => void;
}) {
  const hasRecords = records && records.length > 0;
  
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
              {hasRecords && <th className="py-3 px-5 text-right">Actual Power</th>}
              {hasRecords && <th className="py-3 px-5 text-right w-24">Diff</th>}
            </tr>
          </thead>
          <tbody onMouseLeave={() => onHover(null)} className="divide-y divide-border/50">
            {steps.map((step, i) => {
              const isH = highlightedStep === i
              const isS = selectedStep === i
              const isD = highlightedStep != null && highlightedStep !== i
              
              const { actualPower, powerDiff, diffColor } = hasRecords 
                ? calculateStepActuals(step, records!)
                : { actualPower: null, powerDiff: null, diffColor: 'text-text-muted' }

              return (
                <tr key={i} onMouseEnter={() => onHover(i)} onClick={() => onSelect(isS ? null : i)} className={`cursor-pointer transition-all duration-200 ${isS ? 'bg-accent/10' : isH ? 'bg-accent/5' : isD ? 'opacity-30 grayscale' : 'hover:bg-surface2/30'}`}>
                  <td className="py-3 px-5"><div className="w-full h-1.5 rounded-full shadow-[0_0_8px] shadow-current" style={{ backgroundColor: zoneColor(step.power_pct), color: zoneColor(step.power_pct) }} /></td>
                  <td className="py-3 px-5 font-bold text-text uppercase text-[10px] tracking-widest">{step.type}</td>
                  <td className="py-3 px-5 font-mono text-xs text-text-muted">{fmtTime(step.start_s)} - {fmtTime(step.start_s + step.duration_s)}</td>
                  <td className="py-3 px-5 font-bold text-text">{fmtTime(step.duration_s)}</td>
                  <td className="py-3 px-5 text-right font-mono font-bold text-blue">{step.power_watts}w <span className="text-[10px] text-text-muted opacity-50 ml-1">({Math.round(step.power_pct * 100)}%)</span></td>
                  {hasRecords && (
                    <td className="py-3 px-5 text-right font-mono font-bold text-text">
                      {actualPower !== null ? `${actualPower}w` : '--'}
                    </td>
                  )}
                  {hasRecords && (
                    <td className={`py-3 px-5 text-right font-mono font-bold text-xs ${diffColor}`}>
                      {powerDiff !== null ? `${powerDiff > 0 ? '+' : ''}${powerDiff}w` : '--'}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function WorkoutOnlyDetail({ workout }: { workout: WorkoutDetail }) {
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
        selectedStep={selectedStep}
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
            <div className="p-4"><textarea value={nVal} onChange={e => setAthleteNotes(e.target.value)} placeholder="Strategy, fueling goals, or focus areas..." rows={5} className="w-full bg-surface-low text-text border border-border rounded-lg px-4 py-3 text-base md:text-sm focus:outline-none focus:border-accent placeholder:text-text-muted/30 resize-none transition-all leading-relaxed" />{saveStatus && <p className="text-[10px] font-bold text-green mt-2 animate-in fade-in">✓ {saveStatus}</p>}</div>
          </section>
          {workout.coach_notes && (
            <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm opacity-90">
              <div className="px-5 py-3 border-b border-border bg-surface-low flex items-center gap-2"><Info size={16} className="text-yellow" /><h3 className="text-[10px] font-bold text-text uppercase tracking-wider">Coach Guidance</h3></div>
              <div className="p-5 italic text-base md:text-sm text-text-muted leading-relaxed whitespace-pre-wrap">"{workout.coach_notes}"</div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
