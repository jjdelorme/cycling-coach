import { useState, useMemo } from 'react'
import { useAuth } from './lib/auth'
import Layout, { type TabKey, type ViewContext } from './components/Layout'
import LoginPage from './components/LoginPage'
import Dashboard from './pages/Dashboard'
import Rides from './pages/Rides'
import Calendar from './pages/Calendar'
import Analysis from './pages/Analysis'
import Nutrition from './pages/Nutrition'
import Settings from './pages/Settings'
import Admin from './pages/Admin'

export default function App() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const [tab, setTab] = useState<TabKey>('dashboard')
  const [rideId, setRideId] = useState<number | undefined>()
  const [rideDate, setRideDate] = useState<string | undefined>()
  const [calendarDate, setCalendarDate] = useState<string | undefined>()
  const [nutritionistContext, setNutritionistContext] = useState<string | undefined>()
  const [nutritionistSessionId, setNutritionistSessionId] = useState<string | undefined>()

  const handleOpenNutritionist = (context?: string, sessionId?: string) => {
    setNutritionistContext(context)
    setNutritionistSessionId(sessionId)
  }

  const handleRideSelect = (id: number) => {
    setRideId(id)
    setRideDate(undefined)
    setTab('rides')
  }

  const handleWorkoutSelect = (_id: number, date: string) => {
    setRideDate(date)
    setRideId(undefined)
    setTab('rides')
  }

  const viewContext = useMemo<ViewContext>(() => ({
    tab,
    rideId,
    rideDate,
    calendarDate,
  }), [tab, rideId, rideDate, calendarDate])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-bg">
        <span className="text-text-muted">Loading...</span>
      </div>
    )
  }

  // Not authenticated or no access
  if (!isAuthenticated || !user || user.role === 'none') {
    return <LoginPage />
  }

  return (
    <Layout activeTab={tab} onTabChange={t => { setTab(t); setRideId(undefined); setRideDate(undefined); setCalendarDate(undefined); setNutritionistContext(undefined); setNutritionistSessionId(undefined) }} viewContext={viewContext} nutritionistContext={nutritionistContext} nutritionistSessionId={nutritionistSessionId} onOpenNutritionist={handleOpenNutritionist}>
      {tab === 'dashboard' && <Dashboard onRideSelect={handleRideSelect} onWorkoutSelect={handleWorkoutSelect} onNavigateToNutrition={() => setTab('nutrition')} />}
      {tab === 'rides' && (
        <Rides 
          initialRideId={rideId} 
          initialDate={rideDate} 
          onRideSelect={(id) => setRideId(id ?? undefined)}
          onDateSelect={(date) => setRideDate(date ?? undefined)}
        />
      )}
      {tab === 'calendar' && (
        <Calendar 
          onRideSelect={handleRideSelect} 
          onWorkoutSelect={handleWorkoutSelect} 
          onDateSelect={(date) => setCalendarDate(date ?? undefined)}
        />
      )}
      {tab === 'analysis' && <Analysis />}
      {tab === 'nutrition' && (
        <Nutrition onOpenNutritionist={handleOpenNutritionist} />
      )}
      {tab === 'settings' && <Settings />}
      {tab === 'admin' && user?.role === 'admin' && <Admin />}
    </Layout>
  )
}
