import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import LoadingScreen from './LoadingScreen'

export default function RequireAuth() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <LoadingScreen />
  if (!isAuthenticated || !user || user.role === 'none') {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return <Outlet />
}
