import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useActivityDates } from '../hooks/useApi'
import { fetchRides } from '../lib/api'
import { fmtDateStr } from '../lib/format'

interface DayDetailShellProps {
  currentDate: string | null
  backTo: { href: string; label: string }
  children: React.ReactNode
}

export default function DayDetailShell({ currentDate, backTo, children }: DayDetailShellProps) {
  const navigate = useNavigate()
  const { data: activityDates } = useActivityDates()
  const [isLoading, setIsLoading] = useState(false)

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

  async function navigateToDate(date: string) {
    setIsLoading(true)
    try {
      const ridesOnDate = await fetchRides({ start_date: date, end_date: date, limit: 1 })
      if (ridesOnDate && ridesOnDate.length > 0) {
        navigate(`/rides/${ridesOnDate[0].id}`)
        return
      }
    } catch (err) {
      console.warn('Failed to fetch ride for date:', err)
    } finally {
      setIsLoading(false)
    }
    navigate(`/rides/by-date/${date}`)
  }

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <Link
          to={backTo.href}
          className="flex items-center gap-2 text-text-muted hover:text-accent transition-colors text-xs font-bold uppercase tracking-widest"
        >
          <ChevronLeft size={14} /> {backTo.label}
        </Link>

        <div className="flex items-center bg-surface rounded-lg p-1 border border-border shadow-sm">
          <button
            onClick={() => prevDate && navigateToDate(prevDate)}
            disabled={!prevDate || isLoading}
            className={`p-2 rounded-md transition-all text-text-muted hover:text-text hover:bg-surface-low disabled:opacity-20 ${isLoading ? 'cursor-wait' : ''}`}
            title={prevDate ?? undefined}
          >
            <ChevronLeft size={18} />
          </button>
          <div className="px-4 text-center min-w-[140px]">
            <span className="block text-[10px] font-bold text-accent uppercase tracking-tighter">
              {currentDate && fmtDateStr(currentDate)}
            </span>
            <span className="text-xs font-mono font-bold text-text">{currentDate ?? ''}</span>
          </div>
          <button
            onClick={() => nextDate && navigateToDate(nextDate)}
            disabled={!nextDate || isLoading}
            className={`p-2 rounded-md transition-all text-text-muted hover:text-text hover:bg-surface-low disabled:opacity-20 ${isLoading ? 'cursor-wait' : ''}`}
            title={nextDate ?? undefined}
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </div>

      {children}
    </div>
  )
}
