import { Routes, Route } from 'react-router-dom'
import { NutritionistHandoffProvider, useNutritionistHandoff } from './lib/nutritionist-handoff'
import Layout from './components/Layout'
import LoginPage from './components/LoginPage'
import RequireAuth from './components/RequireAuth'
import RequireRole from './components/RequireRole'
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

export default function App() {
  return (
    <NutritionistHandoffProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
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
            <Route path="settings" element={<RequireRole role="read"><Settings /></RequireRole>} />
            <Route path="admin" element={<RequireRole role="admin"><Admin /></RequireRole>} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Route>
      </Routes>
    </NutritionistHandoffProvider>
  )
}
