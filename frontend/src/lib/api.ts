import { getToken } from './auth'

const BASE = ''

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...authHeaders(),
      ...init?.headers,
    },
  })
  if (res.status === 401) {
    // Token expired or invalid — will be handled by auth context
    throw new Error('Unauthorized — please sign in again')
  }
  if (res.status === 403) {
    throw new Error('Insufficient permissions')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

function get<T>(path: string) {
  return request<T>(path)
}

function post<T>(path: string, body?: unknown) {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
}

function put<T>(path: string, body: unknown) {
  return request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

import type {
  RideSummary, RideDetail, PMCEntry, WeeklySummary,
  WorkoutDetail, WeekPlan, PeriodizationPhase, WeeklyOverview,
  ChatResponse, SessionSummary, SyncOverview, SyncStatus,
  CoachSettings,
} from '../types/api'

// Rides
export const fetchRides = (params?: { start_date?: string; end_date?: string; sport?: string; limit?: number }) => {
  const q = new URLSearchParams()
  if (params?.start_date) q.set('start_date', params.start_date)
  if (params?.end_date) q.set('end_date', params.end_date)
  if (params?.sport) q.set('sport', params.sport)
  if (params?.limit) q.set('limit', String(params.limit))
  return get<RideSummary[]>(`/api/rides?${q}`)
}
export const fetchRide = (id: number) => get<RideDetail>(`/api/rides/${id}`)
export const fetchWeeklySummary = (params?: { start_date?: string; end_date?: string }) => {
  const q = new URLSearchParams()
  if (params?.start_date) q.set('start_date', params.start_date)
  if (params?.end_date) q.set('end_date', params.end_date)
  return get<WeeklySummary[]>(`/api/rides/summary/weekly?${q}`)
}
export const updateRideComments = (id: number, body: { post_ride_comments?: string | null }) =>
  put<{ status: string }>(`/api/rides/${id}/comments`, body)
export const updateRideTitle = (id: number, body: { title?: string | null }) =>
  put<{ status: string }>(`/api/rides/${id}/title`, body)

// PMC
export const fetchPMC = () => get<PMCEntry[]>('/api/pmc')

// Analysis
export type DateRange = { start_date?: string; end_date?: string }

function dateQuery(params?: DateRange): string {
  const q = new URLSearchParams()
  if (params?.start_date) q.set('start_date', params.start_date)
  if (params?.end_date) q.set('end_date', params.end_date)
  const s = q.toString()
  return s ? `?${s}` : ''
}

export const fetchPowerCurve = (params?: DateRange) =>
  get<{ duration_s: number; power: number; date: string; ride_id: number }[]>(`/api/analysis/power-curve${dateQuery(params)}`)
export const fetchEfficiency = (params?: DateRange) =>
  get<EfficiencyPoint[]>(`/api/analysis/efficiency${dateQuery(params)}`)
export const fetchZones = async (params?: DateRange): Promise<ZoneDistribution[]> => {
  const raw = await get<{ seconds: Record<string, number>; percentages: Record<string, number> }>(`/api/analysis/zones${dateQuery(params)}`)
  return Object.keys(raw.percentages).map((zone) => ({
    zone,
    percentage: raw.percentages[zone],
    hours: (raw.seconds[zone] ?? 0) / 3600,
  }))
}
export const fetchFTPHistory = (params?: DateRange) =>
  get<FTPHistoryPoint[]>(`/api/analysis/ftp-history${dateQuery(params)}`)
import type { EfficiencyPoint, ZoneDistribution, FTPHistoryPoint } from '../types/api'

// Athlete settings
export const fetchAthleteSettings = () => get<Record<string, string>>('/api/athlete/settings')
export const updateAthleteSetting = (body: { key: string; value: string }) =>
  put<{ status: string }>('/api/athlete/settings', body)

// Plan
export const fetchMacroPlan = () => get<PeriodizationPhase[]>('/api/plan/macro')
export const fetchWeeklyOverview = () => get<WeeklyOverview[]>('/api/plan/weekly-overview')
export const fetchWeekPlan = (date: string) => get<WeekPlan>(`/api/plan/week/${date}`)
export const fetchActivityDates = () => get<string[]>('/api/plan/activity-dates')
export const fetchWorkoutByDate = (date: string) => get<WorkoutDetail | null>(`/api/plan/workouts/by-date/${date}`)
export const fetchWorkoutDetail = (id: number) => get<WorkoutDetail>(`/api/plan/workouts/${id}`)
export const updateWorkoutNotes = (id: number, body: { athlete_notes?: string | null }) =>
  put<{ status: string }>(`/api/plan/workouts/${id}/notes`, body)

// Coaching
export const sendChat = (message: string, session_id?: string) =>
  post<ChatResponse>('/api/coaching/chat', { message, session_id })
export const fetchSessions = () => get<SessionSummary[]>('/api/coaching/sessions')
export const fetchSession = (id: string) => get<import('../types/api').SessionDetail>(`/api/coaching/sessions/${id}`)
export const deleteSession = (id: string) => request<{ status: string }>(`/api/coaching/sessions/${id}`, { method: 'DELETE' })

// Settings
export const fetchSettings = () => get<CoachSettings>('/api/coaching/settings')
export const updateSetting = (key: string, value: string) =>
  put<{ status: string }>('/api/coaching/settings', { key, value })
export const resetSettings = () => post<{ status: string }>('/api/coaching/settings/reset', {})

// Sync
export const fetchSyncOverview = () => get<SyncOverview>('/api/sync/overview')
export const startSync = () => post<{ sync_id: string; ws_url: string }>('/api/sync/start')
export const fetchSyncStatus = (id: string) => get<SyncStatus>(`/api/sync/status/${id}`)

// Health
export const fetchHealth = () => get<{ status: string; rides: number }>('/api/health')

// Admin - User Management
export interface UserRecord {
  email: string
  display_name: string | null
  avatar_url: string | null
  role: string
  created_at: string | null
  last_login: string | null
}
export const fetchUsers = () => get<UserRecord[]>('/api/admin/users')
export const createUser = (email: string, role: string) =>
  post<{ status: string }>('/api/admin/users', { email, role })
export const updateUserRole = (email: string, role: string) =>
  put<{ status: string }>(`/api/admin/users/${encodeURIComponent(email)}`, { role })
export const deleteUser = (email: string) =>
  request<{ status: string }>(`/api/admin/users/${encodeURIComponent(email)}`, { method: 'DELETE' })
