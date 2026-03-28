export interface RideSummary {
  id: number
  date: string
  filename: string
  sport?: string
  sub_sport?: string
  duration_s?: number
  distance_m?: number
  avg_power?: number
  normalized_power?: number
  max_power?: number
  avg_hr?: number
  max_hr?: number
  avg_cadence?: number
  total_ascent?: number
  total_descent?: number
  total_calories?: number
  tss?: number
  intensity_factor?: number
  ftp?: number
  total_work_kj?: number
  training_effect?: number
  variability_index?: number
  best_1min_power?: number
  best_5min_power?: number
  best_20min_power?: number
  best_60min_power?: number
  weight?: number
  start_lat?: number
  start_lon?: number
  post_ride_comments?: string
  coach_comments?: string
  title?: string
  start_time?: string
}

export interface RideRecord {
  timestamp_utc?: string
  power?: number
  heart_rate?: number
  cadence?: number
  speed?: number
  altitude?: number
  distance?: number
  lat?: number
  lon?: number
  temperature?: number
}

export interface RideLap {
  lap_index: number
  start_time?: string
  total_timer_time?: number
  total_elapsed_time?: number
  total_distance?: number
  avg_power?: number
  normalized_power?: number
  max_power?: number
  avg_hr?: number
  max_hr?: number
  avg_cadence?: number
  max_cadence?: number
  avg_speed?: number
  max_speed?: number
  total_ascent?: number
  total_descent?: number
  total_calories?: number
  total_work?: number
  intensity?: string
  lap_trigger?: string
  wkt_step_index?: number
  start_lat?: number
  start_lon?: number
  end_lat?: number
  end_lon?: number
  avg_temperature?: number
}

export interface RideDetail extends RideSummary {
  records: RideRecord[]
  laps: RideLap[]
}

export interface PMCEntry {
  date: string
  total_tss?: number
  ctl?: number
  atl?: number
  tsb?: number
  weight?: number
}

export interface WeeklySummary {
  week: string
  rides: number
  duration_h: number
  tss: number
  distance_km: number
  ascent_m: number
  avg_power?: number
  avg_hr?: number
  best_20min?: number
}

export interface PlannedWorkout {
  id: number
  date?: string
  name?: string
  sport?: string
  total_duration_s?: number
  planned_tss?: number
  workout_xml?: string
  coach_notes?: string
  athlete_notes?: string
}

export interface WorkoutDetail {
  id: number
  date?: string
  name?: string
  sport?: string
  total_duration_s: number
  planned_tss?: number
  ftp: number
  steps: WorkoutStep[]
  has_xml?: boolean
  coach_notes?: string
  athlete_notes?: string
}

export interface WorkoutStep {
  type: string
  label: string
  duration_s: number
  start_s: number
  power_pct: number
  power_watts: number
  power_low_pct?: number
  power_high_pct?: number
  power_low_watts?: number
  power_high_watts?: number
}

export interface PeriodizationPhase {
  id: number
  name: string
  start_date: string
  end_date: string
  focus?: string
  hours_per_week_low?: number
  hours_per_week_high?: number
  tss_target_low?: number
  tss_target_high?: number
}

export interface WeeklyOverview {
  week_start: string
  phase: string | null
  target_hours_low: number | null
  target_hours_high: number | null
  target_tss_low: number | null
  target_tss_high: number | null
  planned_hours: number
  planned_tss: number
  planned_workouts: number
  actual_hours: number
  actual_tss: number
  actual_rides: number
}

export interface WeekPlan {
  week_start: string
  week_end: string
  planned: PlannedWorkout[]
  actual: RideSummary[]
}

export interface ChatRequest {
  message: string
  session_id?: string
}

export interface ChatResponse {
  response: string
  session_id: string
}

export interface SessionSummary {
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface SessionMessage {
  author?: string
  role?: string
  content_text?: string
  timestamp: string
}

export interface SessionDetail {
  session_id: string
  title?: string
  created_at: string
  updated_at: string
  messages: SessionMessage[]
}

export interface SyncOverview {
  configured: boolean
  running_sync_id?: string
  last_sync?: {
    id: string
    status: string
    started_at: string
    completed_at?: string
    rides_downloaded?: number
    rides_skipped?: number
    workouts_uploaded?: number
    workouts_skipped?: number
  }
  watermarks: {
    rides_newest?: string
    workouts_synced_through?: string
  }
}

export interface SyncStatus {
  sync_id: string
  status: string
  phase?: string
  detail?: string
  rides_downloaded?: number
  rides_skipped?: number
  workouts_uploaded?: number
  workouts_skipped?: number
  type?: string
}

export interface PowerCurvePoint {
  duration_s: number
  label: string
  power: number
  date: string
}

export interface EfficiencyPoint {
  date: string
  ef: number
  np?: number
  avg_hr?: number
}

export interface ZoneDistribution {
  zone: string
  percentage: number
  hours: number
}

export interface FTPHistoryPoint {
  month: string
  ftp: number
  weight_kg?: number
  w_per_kg?: number
}

export interface CoachSettings {
  athlete_profile: string
  coaching_principles: string
  coach_role: string
  plan_management: string
  intervals_icu_api_key?: string
  intervals_icu_athlete_id?: string
  units?: string
  theme?: string
  gemini_model?: string
  gcp_location?: string
  gemini_api_key?: string
}
