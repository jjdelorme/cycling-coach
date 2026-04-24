import { useParams } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { useWorkoutDetail } from '../hooks/useApi'
import { WorkoutOnlyDetail } from './Rides'
import NotFound from './NotFound'
import DayDetailShell from '../components/DayDetailShell'

/**
 * Standalone planned-workout detail page.
 *
 * Mounted at `/workouts/:id`. Reuses the `WorkoutOnlyDetail` component
 * exported from `Rides.tsx` so the visual layout stays consistent with the
 * "workout-only" branch of the rides detail flow.
 */
export default function WorkoutDetail() {
  const params = useParams<{ id: string }>()
  const id = params.id ? Number(params.id) : null
  const { data: workout, isLoading, isError } = useWorkoutDetail(id)
  const currentDate = workout?.date ? workout.date.slice(0, 10) : null

  return (
    <DayDetailShell currentDate={currentDate} backTo={{ href: '/calendar', label: 'Back to Calendar' }}>
      {isLoading && (
        <div className="flex items-center justify-center py-24">
          <RefreshCw size={32} className="animate-spin text-accent opacity-50" />
        </div>
      )}

      {!isLoading && (isError || !workout) && <NotFound />}

      {workout && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
          <WorkoutOnlyDetail workout={workout} />
        </div>
      )}
    </DayDetailShell>
  )
}
