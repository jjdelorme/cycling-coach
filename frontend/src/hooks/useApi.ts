import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../lib/api'
import { useAuth } from '../lib/auth'

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

export function useDeleteRide() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.deleteRide(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['rides'] })
      qc.invalidateQueries({ queryKey: ['pmc'] })
      qc.invalidateQueries({ queryKey: ['weekly-summary'] })
      qc.invalidateQueries({ queryKey: ['ride', id] })
      qc.invalidateQueries({ queryKey: ['power-curve'] })
      qc.invalidateQueries({ queryKey: ['efficiency'] })
      qc.invalidateQueries({ queryKey: ['zones'] })
      qc.invalidateQueries({ queryKey: ['ftp-history'] })
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
export function useActivityDates() {
  return useQuery({ queryKey: ['activity-dates'], queryFn: api.fetchActivityDates })
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
export function useDeleteWorkout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.deleteWorkout(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calendar-week-plans'] })
      qc.invalidateQueries({ queryKey: ['week-plan'] })
      qc.invalidateQueries({ queryKey: ['weekly-overview'] })
    },
  })
}

// Coaching
export function useSendChat() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ message, session_id }: { message: string; session_id?: string }) =>
      api.sendChat(message, session_id),
    onSuccess: () => {
      // Refresh calendar/plan data in case the coach modified workouts
      qc.invalidateQueries({ queryKey: ['calendar-week-plans'] })
      qc.invalidateQueries({ queryKey: ['week-plan'] })
      qc.invalidateQueries({ queryKey: ['weekly-overview'] })
      qc.invalidateQueries({ queryKey: ['macro-plan'] })
    },
  })
}
export function useSessions() {
  return useQuery({ queryKey: ['sessions'], queryFn: api.fetchSessions })
}

// Settings
export function useSettings() {
  const { isAuthenticated } = useAuth()
  return useQuery({ queryKey: ['settings'], queryFn: api.fetchSettings, enabled: isAuthenticated })
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

// Daily summary (rolling window)
export function useDailySummary(days = 7) {
  return useQuery({
    queryKey: ['daily-summary', days],
    queryFn: () => api.fetchDailySummary(days),
  })
}

// Nutrition
export function useMeals(params?: Parameters<typeof api.fetchMeals>[0]) {
  return useQuery({
    queryKey: ['meals', params],
    queryFn: () => api.fetchMeals(params),
  })
}

export function useMeal(id: number | null) {
  return useQuery({
    queryKey: ['meal', id],
    queryFn: () => api.fetchMeal(id!),
    enabled: id !== null,
  })
}

export function useLogMeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, comment, mealType, audio, audioMimeType }: {
      file: File; comment?: string; mealType?: string;
      audio?: Blob; audioMimeType?: string;
    }) => api.uploadMealPhoto(file, comment, mealType, audio, audioMimeType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
      qc.invalidateQueries({ queryKey: ['weekly-nutrition'] })
    },
  })
}

export function useUpdateMeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.updateMeal>[1] }) =>
      api.updateMeal(id, body),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['meal', id] })
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
      qc.invalidateQueries({ queryKey: ['weekly-nutrition'] })
    },
  })
}

export function useDeleteMeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.deleteMeal(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
      qc.invalidateQueries({ queryKey: ['weekly-nutrition'] })
    },
  })
}

export function useDailyNutrition(date?: string) {
  return useQuery({
    queryKey: ['daily-nutrition', date],
    queryFn: () => api.fetchDailyNutrition(date),
  })
}

export function useWeeklyNutrition(date?: string) {
  return useQuery({
    queryKey: ['weekly-nutrition', date],
    queryFn: () => api.fetchWeeklyNutrition(date),
  })
}

export function useMacroTargets() {
  return useQuery({
    queryKey: ['macro-targets'],
    queryFn: api.fetchMacroTargets,
  })
}

export function useUpdateMacroTargets() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.updateMacroTargets,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['macro-targets'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
    },
  })
}

export function useNutritionistChat() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ message, session_id }: { message: string; session_id?: string }) =>
      api.sendNutritionChat(message, session_id),
    onSuccess: () => {
      // Refresh meal data in case the nutritionist modified meals
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
    },
  })
}

export function useNutritionSessions() {
  return useQuery({
    queryKey: ['nutrition-sessions'],
    queryFn: api.fetchNutritionSessions,
  })
}
