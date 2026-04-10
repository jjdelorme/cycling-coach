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
  if (res.status === 429) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || 'Rate limit reached — please try again later')
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
  RideSummary, RideDetail, PMCEntry, WeeklySummary, DailySummary,
  WorkoutDetail, WeekPlan, PeriodizationPhase, WeeklyOverview,
  ChatResponse, SessionSummary, SyncOverview, SyncStatus,
  CoachSettings,
  MealDetail, MealListResponse, MacroTargets,
  DailyNutritionSummary, WeeklyNutritionSummary,
  NutritionChatResponse,
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
export const fetchDailySummary = (days = 7) =>
  get<DailySummary[]>(`/api/rides/summary/daily?days=${days}`)
export const updateRideComments = (id: number, body: { post_ride_comments?: string | null }) =>
  put<{ status: string }>(`/api/rides/${id}/comments`, body)
export const updateRideTitle = (id: number, body: { title?: string | null }) =>
  put<{ status: string }>(`/api/rides/${id}/title`, body)
export const deleteRide = (id: number) => request<{ status: string }>(`/api/rides/${id}`, { method: 'DELETE' })

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
export const deleteWorkout = (id: number) =>
  request<{ status: string }>(`/api/plan/workouts/${id}`, { method: 'DELETE' })

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

// Health & Version
export const fetchHealth = () => get<{ status: string; rides: number }>('/api/health')
export const fetchVersion = () => get<{ version: string }>('/api/version')

// Auth
export interface LoginResponse {
  token: string
  email: string
  display_name: string
  avatar_url: string
  role: string
}
export const exchangeGoogleToken = (googleToken: string) =>
  post<LoginResponse>('/api/auth/login', { google_token: googleToken })

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

export const syncSingleRide = (icuId: string) => post<{ status: string; sync_id: string }>(`/api/sync/ride/${icuId}`)

// Nutrition
export const fetchMeals = (params?: { start_date?: string; end_date?: string; limit?: number; offset?: number }) => {
  const q = new URLSearchParams()
  if (params?.start_date) q.set('start_date', params.start_date)
  if (params?.end_date) q.set('end_date', params.end_date)
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.offset) q.set('offset', String(params.offset))
  return get<MealListResponse>(`/api/nutrition/meals?${q}`)
}

export const fetchMeal = (id: number) => get<MealDetail>(`/api/nutrition/meals/${id}`)

export const uploadMealPhoto = async (
  file: File,
  comment?: string,
  mealType?: string,
  audio?: Blob,
  audioMimeType?: string,
) => {
  const form = new FormData()
  form.append('file', file)
  if (comment) form.append('comment', comment)
  if (mealType) form.append('meal_type', mealType)
  if (audio) form.append('audio', audio, `voice.${audioMimeType === 'audio/mp4' ? 'mp4' : 'webm'}`)
  return request<MealDetail>('/api/nutrition/meals', {
    method: 'POST',
    body: form,
    // Note: do NOT set Content-Type header — browser sets it with boundary for multipart
  })
}

export const updateMeal = (id: number, body: {
  total_calories?: number; total_protein_g?: number; total_carbs_g?: number;
  total_fat_g?: number; meal_type?: string; date?: string; items?: MealDetail['items']
}) => put<{ status: string }>(`/api/nutrition/meals/${id}`, body)

export const deleteMeal = (id: number) =>
  request<{ status: string }>(`/api/nutrition/meals/${id}`, { method: 'DELETE' })

export const fetchDailyNutrition = (date?: string) => {
  const q = date ? `?date=${date}` : ''
  return get<DailyNutritionSummary>(`/api/nutrition/daily-summary${q}`)
}

export const fetchWeeklyNutrition = (date?: string) => {
  const q = date ? `?date=${date}` : ''
  return get<WeeklyNutritionSummary>(`/api/nutrition/weekly-summary${q}`)
}

export const fetchMacroTargets = () => get<MacroTargets>('/api/nutrition/targets')

export const updateMacroTargets = (body: MacroTargets) =>
  put<{ status: string }>('/api/nutrition/targets', body)

export const sendNutritionChat = (message: string, sessionId?: string) =>
  post<NutritionChatResponse>('/api/nutrition/chat', { message, session_id: sessionId })

export const fetchNutritionSessions = () => get<SessionSummary[]>('/api/nutrition/sessions')

export const fetchNutritionSession = (id: string) =>
  get<import('../types/api').SessionDetail>(`/api/nutrition/sessions/${id}`)

export const deleteNutritionSession = (id: string) =>
  request<{ status: string }>(`/api/nutrition/sessions/${id}`, { method: 'DELETE' })

