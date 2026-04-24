import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from '../lib/auth'
import { roleSatisfies, type Role } from '../lib/routes'
import LoadingScreen from './LoadingScreen'

interface Props {
  role: Role
  children: ReactNode
}

export default function RequireRole({ role, children }: Props) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <LoadingScreen />
  if (!roleSatisfies(user?.role, role)) return <Navigate to="/" replace />
  return <>{children}</>
}
