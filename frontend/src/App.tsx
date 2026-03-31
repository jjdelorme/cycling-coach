import { useState, useMemo } from 'react'
import { useAuth } from './lib/auth'
import Layout, { type TabKey, type ViewContext } from './components/Layout'
import LoginPage from './components/LoginPage'
import Dashboard from './pages/Dashboard'
import Rides from './pages/Rides'
import Calendar from './pages/Calendar'
import Analysis from './pages/Analysis'
import Settings from './pages/Settings'
import Admin from './pages/Admin'

export default function App() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const [tab, setTab] = useState<TabKey>('dashboard')
  const [rideId, setRideId] = useState<number | undefined>()
  const [rideDate, setRideDate] = useState<string | undefined>()
  const [calendarDate, setCalendarDate] = useState<string | undefined>()

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
    <Layout activeTab={tab} onTabChange={t => { setTab(t); setRideId(undefined); setRideDate(undefined); setCalendarDate(undefined) }} viewContext={viewContext}>
      {tab === 'dashboard' && <Dashboard onRideSelect={handleRideSelect} onWorkoutSelect={handleWorkoutSelect} />}
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
      {tab === 'settings' && <Settings />}
      {tab === 'admin' && user?.role === 'admin' && <Admin />}
    </Layout>
  )
}
