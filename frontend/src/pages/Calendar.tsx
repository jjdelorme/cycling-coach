import { useState, useMemo } from 'react'
import { useRides, useDeleteWorkout } from '../hooks/useApi'
import { fetchWeekPlan } from '../lib/api'
import { fmtDuration, fmtDistance, fmtSport } from '../lib/format'
import { useUnits } from '../lib/units'
import { useQuery } from '@tanstack/react-query'
import { 
  ChevronLeft, 
  ChevronRight, 
  RotateCw, 
  Calendar as CalendarIcon, 
  Trash2, 
  ExternalLink, 
  Zap,
  Clock,
  TrendingUp,
  Heart,
  Info,
  CalendarDays,
  Activity
} from 'lucide-react'
import type { PlannedWorkout, RideSummary } from '../types/api'
import SportIcon from '../components/SportIcon'

interface Props {
  onRideSelect: (id: number) => void
  onWorkoutSelect: (id: number, date: string) => void
  onDateSelect?: (date: string | null) => void
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const DAY_HEADERS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function toDateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function weekMonday(d: Date): Date {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const dow = copy.getDay() // 0=Sun
  const diff = dow === 0 ? -6 : 1 - dow
  copy.setDate(copy.getDate() + diff)
  return copy
}

function buildCalendarDays(year: number, month: number): Date[] {
  const firstOfMonth = new Date(year, month, 1)
  const lastOfMonth = new Date(year, month + 1, 0)
  const startDate = weekMonday(firstOfMonth)
  const endSunday = new Date(lastOfMonth)
  const dow = endSunday.getDay()
  if (dow !== 0) endSunday.setDate(endSunday.getDate() + (7 - dow))

  const days: Date[] = []
  const cursor = new Date(startDate)
  while (cursor <= endSunday) {
    days.push(new Date(cursor))
    cursor.setDate(cursor.getDate() + 1)
  }
  return days
}

function getWeekMondays(calendarDays: Date[]): string[] {
  const set = new Set<string>()
  for (const d of calendarDays) set.add(toDateStr(weekMonday(d)))
  return Array.from(set).sort()
}

export default function Calendar({ onRideSelect, onWorkoutSelect, onDateSelect }: Props) {
  const units = useUnits()
  const deleteWorkout = useDeleteWorkout()
  const [currentDate, setCurrentDate] = useState(() => {
    const now = new Date()
    return { year: now.getFullYear(), month: now.getMonth() }
  })
  const [selectedDay, setSelectedDay] = useState<string | null>(() => toDateStr(new Date()))

  const handleSetSelectedDay = (date: string | null) => {
    setSelectedDay(date)
    onDateSelect?.(date)
  }

  const calendarDays = useMemo(
    () => buildCalendarDays(currentDate.year, currentDate.month),
    [currentDate.year, currentDate.month],
  )

  const weekMondays = useMemo(() => getWeekMondays(calendarDays), [calendarDays])
  const gridStart = toDateStr(calendarDays[0])
  const gridEnd = toDateStr(calendarDays[calendarDays.length - 1])

  const { data: rides, isLoading: ridesLoading } = useRides({ start_date: gridStart, end_date: gridEnd, limit: 500 })

  const { data: weekPlans, isLoading: plansLoading, refetch } = useQuery({
    queryKey: ['calendar-week-plans', weekMondays],
    queryFn: async () => Promise.all(weekMondays.map((m) => fetchWeekPlan(m))),
    enabled: weekMondays.length > 0,
  })

  const allWorkouts = useMemo(() => {
    if (!weekPlans) return []
    const seen = new Set<number>(), result: PlannedWorkout[] = []
    for (const wp of weekPlans) for (const w of wp.planned) if (w.id && !seen.has(w.id)) { seen.add(w.id); result.push(w) }
    return result
  }, [weekPlans])

  const ridesByDate = useMemo(() => {
    const map = new Map<string, RideSummary[]>()
    if (rides) for (const r of rides) { const d = r.date?.slice(0, 10); if (d) { if (!map.has(d)) map.set(d, []); map.get(d)!.push(r) } }
    return map
  }, [rides])

  const workoutsByDate = useMemo(() => {
    const map = new Map<string, PlannedWorkout[]>()
    for (const w of allWorkouts) { const d = w.date?.slice(0, 10); if (d) { if (!map.has(d)) map.set(d, []); map.get(d)!.push(w) } }
    return map
  }, [allWorkouts])

  function prevMonth() { setCurrentDate(p => p.month === 0 ? { year: p.year - 1, month: 11 } : { year: p.year, month: p.month - 1 }); handleSetSelectedDay(null) }
  function nextMonth() { setCurrentDate(p => p.month === 11 ? { year: p.year + 1, month: 0 } : { year: p.year, month: p.month + 1 }); handleSetSelectedDay(null) }

  const selectedRides = selectedDay ? ridesByDate.get(selectedDay) ?? [] : []
  const selectedWorkouts = selectedDay ? workoutsByDate.get(selectedDay) ?? [] : []

  return (
    <div className="space-y-6 pb-12">
      {/* Month Navigation */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-text flex items-center gap-3">
          <CalendarDays size={24} className="text-accent" />
          {MONTH_NAMES[currentDate.month]} {currentDate.year}
        </h1>
        
        <div className="flex items-center gap-2 bg-surface rounded-lg p-1 border border-border shadow-sm">
          <button onClick={prevMonth} className="p-2 rounded-md transition-all text-text-muted hover:text-text hover:bg-surface-low"><ChevronLeft size={18} /></button>
          <button onClick={() => refetch()} className="p-2 rounded-md transition-all text-text-muted hover:text-accent hover:bg-surface-low" title="Refresh"><RotateCw size={16} /></button>
          <button onClick={nextMonth} className="p-2 rounded-md transition-all text-text-muted hover:text-text hover:bg-surface-low"><ChevronRight size={18} /></button>
        </div>
      </div>

      {(ridesLoading || plansLoading) && (
        <div className="fixed top-20 right-8 z-50 animate-in fade-in zoom-in duration-300">
          <div className="flex items-center gap-3 px-4 py-2 bg-accent text-white rounded-full shadow-lg shadow-accent/20">
            <RotateCw size={14} className="animate-spin" />
            <span className="text-[10px] font-bold uppercase tracking-widest">Syncing Data</span>
          </div>
        </div>
      )}

      {/* Calendar Grid */}
      <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-md">
        <div className="grid grid-cols-7 border-b border-border bg-surface-low">
          {DAY_HEADERS.map((d) => (
            <div key={d} className="text-center text-[10px] font-bold text-text-muted uppercase tracking-[0.2em] py-3">
              {d}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-px bg-border">
          {calendarDays.map((date) => {
            const dateStr = toDateStr(date), isCM = date.getMonth() === currentDate.month, isT = dateStr === toDateStr(new Date()), isS = dateStr === selectedDay
            const dayRides = ridesByDate.get(dateStr) ?? [], dayWOs = workoutsByDate.get(dateStr) ?? []
            const totalTSS = dayRides.reduce((sum, r) => sum + (r.tss ?? 0), 0)

            return (
              <div
                key={dateStr}
                onClick={() => handleSetSelectedDay(isS ? null : dateStr)}
                className={`min-h-[100px] md:min-h-[130px] p-2 cursor-pointer transition-all relative group
                  ${isCM ? 'bg-surface' : 'bg-bg opacity-40'}
                  ${isT ? 'after:absolute after:inset-0 after:ring-2 after:ring-accent after:ring-inset' : ''}
                  ${isS ? 'bg-yellow/10 ring-1 ring-yellow/30 ring-inset' : 'hover:bg-yellow/5'}
                `}
              >
                <div className={`text-xs font-bold mb-1 ${isT ? 'text-accent' : isCM ? 'text-text' : 'text-text-muted'}`}>
                  {date.getDate()}
                </div>

                <div className="space-y-1 overflow-hidden">
                  {dayRides.map((r) => (
                    <div key={r.id} className="flex items-center gap-1 text-[9px] font-bold text-green uppercase tracking-tighter truncate leading-none">
                      <SportIcon sport={r.sport} size={8} /> {Math.round(r.tss ?? 0)}
                    </div>
                  ))}
                  {dayWOs.map((w, i) => (
                    <div key={w.id ?? i} className="flex items-center gap-1 text-[9px] font-bold text-yellow uppercase tracking-tighter truncate leading-none">
                      <Zap size={8} /> {w.name?.split(' ')[0] ?? 'WORKOUT'}
                    </div>
                  ))}
                </div>
                
                {dayRides.length > 0 && totalTSS > 0 && (
                  <div className="absolute bottom-2 right-2 text-[9px] font-black text-text-muted/30 uppercase tracking-widest group-hover:text-accent/40 transition-colors">
                    {Math.round(totalTSS)} TSS
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Day Detail Panel */}
      {selectedDay && (
        <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-lg animate-in fade-in slide-in-from-bottom-4 duration-300">
          <div className="px-6 py-4 border-b border-border bg-surface-low flex items-center justify-between">
            <h3 className="text-sm font-bold text-text uppercase tracking-wider flex items-center gap-3">
              <CalendarIcon size={18} className="text-accent" />
              {new Date(selectedDay + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
            </h3>
            {selectedRides.length === 0 && selectedWorkouts.length === 0 && (
              <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest px-3 py-1 bg-surface rounded-full border border-border/50 italic">Recovery Day</span>
            )}
          </div>

          <div className="p-6 space-y-8">
            {/* Rides Section */}
            {selectedRides.length > 0 && (
              <div className="space-y-6">
                {selectedRides.map((r) => (
                  <div key={r.id} className="group">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-green/10 rounded-lg"><SportIcon sport={r.sport} size={20} className="text-green" /></div>
                        <div>
                          <h4 className="font-bold text-lg text-text leading-none">{r.title || fmtSport(r.sport)}</h4>
                          <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{fmtSport(r.sub_sport || r.sport)}</span>
                        </div>
                      </div>
                      <button onClick={() => onRideSelect(r.id)} className="flex items-center gap-2 px-4 py-2 bg-accent text-white text-[10px] font-bold uppercase tracking-widest rounded-lg hover:opacity-90 transition-all shadow-lg shadow-accent/20">
                        View Analysis <ExternalLink size={12} />
                      </button>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4">
                      <MiniMetric label="Duration" value={fmtDuration(r.duration_s)} icon={Clock} color="text-text" />
                      <MiniMetric label="Distance" value={fmtDistance(r.distance_m, units)} icon={TrendingUp} color="text-text" />
                      <MiniMetric label="TSS" value={String(Math.round(r.tss ?? 0))} icon={Zap} color="text-accent" />
                      <MiniMetric label="Avg Power" value={r.avg_power ? `${r.avg_power}w` : '--'} icon={Activity} color="text-blue" />
                      <MiniMetric label="NP" value={r.normalized_power ? `${r.normalized_power}w` : '--'} icon={TrendingUp} color="text-blue" />
                      <MiniMetric label="Avg HR" value={r.avg_hr ? `${r.avg_hr}bpm` : '--'} icon={Heart} color="text-red" />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Workouts Section */}
            {selectedWorkouts.length > 0 && (
              <div className={`space-y-6 ${selectedRides.length > 0 ? 'pt-8 border-t border-border/50' : ''}`}>
                {selectedWorkouts.map((w, i) => (
                  <div key={w.id ?? i} className="group">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-yellow/10 rounded-lg"><Zap size={20} className="text-yellow" /></div>
                        <div>
                          <h4 className="font-bold text-lg text-text leading-none">{w.name || 'Planned Workout'}</h4>
                          <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{fmtSport(w.sport)} Session</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {w.id && (
                          <button onClick={() => onWorkoutSelect(w.id, selectedDay!)} className="flex items-center gap-2 px-4 py-2 bg-surface border border-border text-[10px] font-bold uppercase tracking-widest rounded-lg hover:text-accent hover:border-accent transition-all shadow-sm">
                            Show Details <ExternalLink size={12} />
                          </button>
                        )}
                        {w.id && (
                          <button onClick={() => { if (confirm(`Delete "${w.name ?? 'Workout'}"?`)) deleteWorkout.mutate(w.id) }} className="p-2 text-text-muted hover:text-red hover:bg-red/5 rounded-lg transition-all" title="Delete Workout">
                            <Trash2 size={16} />
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4">
                      <MiniMetric label="Target Duration" value={fmtDuration(w.total_duration_s)} icon={Clock} color="text-text" />
                      <MiniMetric label="Est. TSS" value={String(Math.round(Number(w.planned_tss)))} icon={Zap} color="text-yellow" />
                      <MiniMetric label="Sport" value={fmtSport(w.sport)} icon={(props: any) => <SportIcon sport={w.sport} {...props} />} color="text-text" />
                    </div>
                    {w.coach_notes && (
                      <div className="mt-4 flex gap-3 p-4 bg-surface-low rounded-xl border border-border">
                        <Info size={16} className="text-accent shrink-0 mt-0.5" />
                        <p className="text-xs text-text-muted leading-relaxed italic">"{w.coach_notes}"</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function MiniMetric({ label, value, icon: Icon, color }: { label: string; value: string; icon: any; color?: string }) {
  return (
    <div className="bg-surface-low rounded-lg p-3 border border-border/50">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider">{label}</span>
        <Icon size={10} className="text-text-muted opacity-30" />
      </div>
      <div className={`text-sm font-bold ${color || 'text-text'}`}>{value}</div>
    </div>
  )
}
