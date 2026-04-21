import { Routes, Route } from 'react-router-dom'
import { useAuth } from './lib/auth'
import { NutritionistHandoffProvider, useNutritionistHandoff } from './lib/nutritionist-handoff'
import Layout from './components/Layout'
import LoginPage from './components/LoginPage'
import Dashboard from './pages/Dashboard'
import Rides from './pages/Rides'
import WorkoutDetail from './pages/WorkoutDetail'
import Calendar from './pages/Calendar'
import Analysis from './pages/Analysis'
import Nutrition from './pages/Nutrition'
import MealDetail from './pages/MealDetail'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import NotFound from './pages/NotFound'

function NutritionRoute() {
  const handoff = useNutritionistHandoff()
  return <Nutrition onOpenNutritionist={handoff.open} />
}

function MealDetailRoute() {
  const handoff = useNutritionistHandoff()
  return <MealDetail onOpenNutritionist={handoff.open} />
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
          <Route index element={<Dashboard />} />
          <Route path="rides" element={<Rides />} />
          <Route path="rides/:id" element={<Rides />} />
          <Route path="rides/by-date/:date" element={<Rides />} />
          <Route path="workouts/:id" element={<WorkoutDetail />} />
          <Route path="calendar" element={<Calendar />} />
          <Route path="analysis" element={<Analysis />} />
          <Route path="nutrition" element={<NutritionRoute />} />
          <Route path="nutrition/week" element={<NutritionRoute />} />
          <Route path="nutrition/plan" element={<NutritionRoute />} />
          <Route path="nutrition/plan/:date" element={<NutritionRoute />} />
          <Route path="nutrition/meals/:id" element={<MealDetailRoute />} />
          <Route path="settings" element={<Settings />} />
          <Route path="admin" element={<AdminRoute />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </NutritionistHandoffProvider>
  )
}
