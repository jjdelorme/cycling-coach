import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from './lib/auth'
import { NutritionistHandoffProvider, useNutritionistHandoff } from './lib/nutritionist-handoff'
import Layout from './components/Layout'
import LoginPage from './components/LoginPage'
import Dashboard from './pages/Dashboard'
import Rides from './pages/Rides'
import Calendar from './pages/Calendar'
import Analysis from './pages/Analysis'
import Nutrition from './pages/Nutrition'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import NotFound from './pages/NotFound'

/**
 * Adapter pages — these wrap legacy page components that still expect the
 * pre-router prop API (e.g. `onRideSelect`, `onWorkoutSelect`,
 * `onOpenNutritionist`). They keep Phase 1 a pure routing change; the
 * underlying state-based detail flow inside `Rides.tsx` continues to work.
 *
 * Phase 2 will replace these with URL-driven detail views and these adapters
 * will collapse into direct `<Page />` routes.
 */
function DashboardRoute() {
  const navigate = useNavigate()
  // For Phase 1, "select ride" still hands off to the Rides page's local
  // state. We pass the desired ride/date through React Router's location
  // state, which the Rides adapter reads.
  const handleRideSelect = (id: number) => {
    navigate('/rides', { state: { rideId: id } })
  }
  const handleWorkoutSelect = (_id: number, date: string) => {
    navigate('/rides', { state: { rideDate: date } })
  }
  const handleNavigateToNutrition = () => navigate('/nutrition')
  return (
    <Dashboard
      onRideSelect={handleRideSelect}
      onWorkoutSelect={handleWorkoutSelect}
      onNavigateToNutrition={handleNavigateToNutrition}
    />
  )
}

function RidesRoute() {
  // Read any ride/date selection passed through navigation state.
  const location = useLocation()
  const state = location.state as { rideId?: number; rideDate?: string } | null
  return (
    <Rides
      initialRideId={state?.rideId}
      initialDate={state?.rideDate}
    />
  )
}

function CalendarRoute() {
  const navigate = useNavigate()
  const handleRideSelect = (id: number) => {
    navigate('/rides', { state: { rideId: id } })
  }
  const handleWorkoutSelect = (_id: number, date: string) => {
    navigate('/rides', { state: { rideDate: date } })
  }
  return (
    <Calendar
      onRideSelect={handleRideSelect}
      onWorkoutSelect={handleWorkoutSelect}
    />
  )
}

function NutritionRoute() {
  const handoff = useNutritionistHandoff()
  return <Nutrition onOpenNutritionist={handoff.open} />
}

function AdminRoute() {
  const { user } = useAuth()
  if (user?.role !== 'admin') return <NotFound />
  return <Admin />
}

export default function App() {
  const { user, isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-bg">
        <span className="text-text-muted">Loading...</span>
      </div>
    )
  }

  // Not authenticated or no access — Phase 1 keeps the original early-return.
  // Phase 6 will introduce a proper /login route + RequireAuth wrapper.
  if (!isAuthenticated || !user || user.role === 'none') {
    return <LoginPage />
  }

  return (
    <NutritionistHandoffProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardRoute />} />
          <Route path="rides" element={<RidesRoute />} />
          <Route path="calendar" element={<CalendarRoute />} />
          <Route path="analysis" element={<Analysis />} />
          <Route path="nutrition" element={<NutritionRoute />} />
          <Route path="settings" element={<Settings />} />
          <Route path="admin" element={<AdminRoute />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </NutritionistHandoffProvider>
  )
}
