const BASE = ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
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
  WorkoutDetail, WeekPlan, PeriodizationPhase,
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

// PMC
export const fetchPMC = () => get<PMCEntry[]>('/api/pmc')

// Analysis
export const fetchPowerCurve = () => get<Record<string, { power: number; date: string }>>('/api/analysis/power-curve')
export const fetchEfficiency = () => get<EfficiencyPoint[]>('/api/analysis/efficiency')
export const fetchZones = () => get<ZoneDistribution[]>('/api/analysis/zones')
export const fetchFTPHistory = () => get<FTPHistoryPoint[]>('/api/analysis/ftp-history')
import type { EfficiencyPoint, ZoneDistribution, FTPHistoryPoint } from '../types/api'

// Plan
export const fetchMacroPlan = () => get<PeriodizationPhase[]>('/api/plan/macro')
export const fetchWeekPlan = (date: string) => get<WeekPlan>(`/api/plan/week/${date}`)
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
