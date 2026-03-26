import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../lib/api'

// Rides
export function useRides(params?: Parameters<typeof api.fetchRides>[0]) {
  return useQuery({
    queryKey: ['rides', params],
    queryFn: () => api.fetchRides(params),
  })
}

export function useRide(id: number | null) {
  return useQuery({
    queryKey: ['ride', id],
    queryFn: () => api.fetchRide(id!),
    enabled: id !== null,
  })
}

export function useUpdateRideComments() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: { post_ride_comments?: string | null } }) =>
      api.updateRideComments(id, body),
    onSuccess: (_, { id }) => qc.invalidateQueries({ queryKey: ['ride', id] }),
  })
}

export function useUpdateRideTitle() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: { title?: string | null } }) =>
      api.updateRideTitle(id, body),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['ride', id] })
      qc.invalidateQueries({ queryKey: ['rides'] })
    },
  })
}

// PMC
export function usePMC() {
  return useQuery({ queryKey: ['pmc'], queryFn: api.fetchPMC })
}

// Analysis
export function usePowerCurve(params?: api.DateRange) {
  return useQuery({ queryKey: ['power-curve', params], queryFn: () => api.fetchPowerCurve(params) })
}
export function useEfficiency(params?: api.DateRange) {
  return useQuery({ queryKey: ['efficiency', params], queryFn: () => api.fetchEfficiency(params) })
}
export function useZones(params?: api.DateRange) {
  return useQuery({ queryKey: ['zones', params], queryFn: () => api.fetchZones(params) })
}
export function useFTPHistory(params?: api.DateRange) {
  return useQuery({ queryKey: ['ftp-history', params], queryFn: () => api.fetchFTPHistory(params) })
}

// Athlete settings
export function useAthleteSettings() {
  return useQuery({ queryKey: ['athlete-settings'], queryFn: api.fetchAthleteSettings })
}
export function useUpdateAthleteSetting() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.updateAthleteSetting,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['athlete-settings'] }),
  })
}

// Plan
export function useMacroPlan() {
  return useQuery({ queryKey: ['macro-plan'], queryFn: api.fetchMacroPlan })
}
export function useWeeklyOverview() {
  return useQuery({ queryKey: ['weekly-overview'], queryFn: api.fetchWeeklyOverview })
}
export function useWeekPlan(date: string) {
  return useQuery({
    queryKey: ['week-plan', date],
    queryFn: () => api.fetchWeekPlan(date),
  })
}
export function useWorkoutDetail(id: number | null) {
  return useQuery({
    queryKey: ['workout', id],
    queryFn: () => api.fetchWorkoutDetail(id!),
    enabled: id !== null,
  })
}
export function useWorkoutByDate(date: string | null) {
  return useQuery({
    queryKey: ['workout-by-date', date],
    queryFn: () => api.fetchWorkoutByDate(date!),
    enabled: date !== null,
  })
}
export function useUpdateWorkoutNotes() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: { athlete_notes?: string | null } }) =>
      api.updateWorkoutNotes(id, body),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['workout', id] })
      qc.invalidateQueries({ queryKey: ['workout-by-date'] })
    },
  })
}

// Coaching
export function useSendChat() {
  return useMutation({
    mutationFn: ({ message, session_id }: { message: string; session_id?: string }) =>
      api.sendChat(message, session_id),
  })
}
export function useSessions() {
  return useQuery({ queryKey: ['sessions'], queryFn: api.fetchSessions })
}

// Settings
export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: api.fetchSettings })
}
export function useUpdateSetting() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => api.updateSetting(key, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })
}
export function useResetSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.resetSettings,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })
}

// Sync
export function useSyncOverview() {
  return useQuery({ queryKey: ['sync-overview'], queryFn: api.fetchSyncOverview })
}

// Weekly summary
export function useWeeklySummary(params?: Parameters<typeof api.fetchWeeklySummary>[0]) {
  return useQuery({
    queryKey: ['weekly-summary', params],
    queryFn: () => api.fetchWeeklySummary(params),
  })
}
