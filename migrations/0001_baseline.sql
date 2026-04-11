-- 0001_baseline.sql
-- Baseline migration: creates the schema_migrations tracking table,
-- then the full application schema, and seeds initial data.

-- Self-bootstrap: migration tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum TEXT
);

-- ---------------------------------------------------------------------------
-- Full application schema (verbatim from _SCHEMA in server/database.py)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rides (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    filename TEXT UNIQUE NOT NULL,
    sport TEXT,
    sub_sport TEXT,
    duration_s REAL,
    distance_m REAL,
    avg_power INTEGER,
    normalized_power INTEGER,
    max_power INTEGER,
    avg_hr INTEGER,
    max_hr INTEGER,
    avg_cadence INTEGER,
    total_ascent INTEGER,
    total_descent INTEGER,
    total_calories INTEGER,
    tss REAL,
    intensity_factor REAL,
    ftp INTEGER,
    total_work_kj REAL,
    training_effect REAL,
    variability_index REAL,
    best_1min_power INTEGER,
    best_5min_power INTEGER,
    best_20min_power INTEGER,
    best_60min_power INTEGER,
    weight REAL,
    start_lat REAL,
    start_lon REAL,
    post_ride_comments TEXT,
    coach_comments TEXT,
    title TEXT,
    start_time TEXT
);

CREATE TABLE IF NOT EXISTS ride_records (
    id SERIAL PRIMARY KEY,
    ride_id INTEGER NOT NULL REFERENCES rides(id),
    timestamp_utc TEXT,
    power INTEGER,
    heart_rate INTEGER,
    cadence INTEGER,
    speed REAL,
    altitude REAL,
    distance REAL,
    lat REAL,
    lon REAL,
    temperature REAL
);

CREATE TABLE IF NOT EXISTS ride_laps (
    id SERIAL PRIMARY KEY,
    ride_id INTEGER NOT NULL REFERENCES rides(id),
    lap_index INTEGER NOT NULL,
    start_time TEXT,
    total_timer_time REAL,
    total_elapsed_time REAL,
    total_distance REAL,
    avg_power INTEGER,
    normalized_power INTEGER,
    max_power INTEGER,
    avg_hr INTEGER,
    max_hr INTEGER,
    avg_cadence INTEGER,
    max_cadence INTEGER,
    avg_speed REAL,
    max_speed REAL,
    total_ascent INTEGER,
    total_descent INTEGER,
    total_calories INTEGER,
    total_work INTEGER,
    intensity TEXT,
    lap_trigger TEXT,
    wkt_step_index INTEGER,
    start_lat REAL,
    start_lon REAL,
    end_lat REAL,
    end_lon REAL,
    avg_temperature REAL
);

CREATE INDEX IF NOT EXISTS idx_ride_laps_ride_id ON ride_laps(ride_id);

CREATE TABLE IF NOT EXISTS planned_workouts (
    id SERIAL PRIMARY KEY,
    date TEXT,
    name TEXT,
    sport TEXT,
    total_duration_s REAL,
    planned_tss REAL,
    workout_xml TEXT,
    coach_notes TEXT,
    athlete_notes TEXT
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    total_tss REAL,
    ctl REAL,
    atl REAL,
    tsb REAL,
    weight REAL,
    ftp REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS power_bests (
    id SERIAL PRIMARY KEY,
    ride_id INTEGER NOT NULL REFERENCES rides(id),
    date TEXT NOT NULL,
    duration_s INTEGER NOT NULL,
    power REAL NOT NULL,
    avg_hr INTEGER,
    avg_cadence INTEGER,
    start_offset_s INTEGER
);

CREATE TABLE IF NOT EXISTS periodization_phases (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    focus TEXT,
    hours_per_week_low REAL,
    hours_per_week_high REAL,
    tss_target_low REAL,
    tss_target_high REAL
);

CREATE INDEX IF NOT EXISTS idx_rides_date ON rides(date);
CREATE INDEX IF NOT EXISTS idx_ride_records_ride_id ON ride_records(ride_id);
CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(date);
CREATE INDEX IF NOT EXISTS idx_power_bests_date ON power_bests(date);
CREATE INDEX IF NOT EXISTS idx_power_bests_duration ON power_bests(duration_s);
CREATE INDEX IF NOT EXISTS idx_power_bests_composite ON power_bests(duration_s, date DESC);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_events (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(session_id),
    author TEXT,
    role TEXT,
    content_text TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coach_memory (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    author TEXT,
    content_text TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coach_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS athlete_settings (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    date_set TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_athlete_settings_key_active ON athlete_settings(key, is_active);

CREATE TABLE IF NOT EXISTS workout_templates (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'general',
    steps TEXT NOT NULL,
    source TEXT DEFAULT 'built-in',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TEXT,
    completed_at TEXT,
    rides_downloaded INTEGER DEFAULT 0,
    rides_skipped INTEGER DEFAULT 0,
    workouts_uploaded INTEGER DEFAULT 0,
    workouts_skipped INTEGER DEFAULT 0,
    errors TEXT,
    log TEXT
);

CREATE TABLE IF NOT EXISTS sync_watermarks (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS body_measurements (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'withings',
    weight_kg REAL,
    fat_percent REAL,
    measured_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, source)
);

CREATE INDEX IF NOT EXISTS idx_body_measurements_date ON body_measurements(date);
CREATE INDEX IF NOT EXISTS idx_body_measurements_source ON body_measurements(source);

CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_status ON sync_runs(status);
CREATE INDEX IF NOT EXISTS idx_sync_runs_started ON sync_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_chat_events_session ON chat_events(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_coach_memory_user ON coach_memory(user_id);

ALTER TABLE rides ADD COLUMN IF NOT EXISTS has_power_data BOOLEAN DEFAULT FALSE;
ALTER TABLE rides ADD COLUMN IF NOT EXISTS data_status TEXT DEFAULT 'raw';

CREATE TABLE IF NOT EXISTS macro_targets (
    user_id TEXT PRIMARY KEY DEFAULT 'athlete',
    calories INTEGER NOT NULL DEFAULT 2500,
    protein_g REAL NOT NULL DEFAULT 150,
    carbs_g REAL NOT NULL DEFAULT 300,
    fat_g REAL NOT NULL DEFAULT 80,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meal_logs (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    date TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    meal_type TEXT,
    description TEXT NOT NULL,
    total_calories INTEGER NOT NULL,
    total_protein_g REAL NOT NULL,
    total_carbs_g REAL NOT NULL,
    total_fat_g REAL NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    photo_gcs_path TEXT,
    agent_notes TEXT,
    edited_by_user BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_meal_logs_date ON meal_logs(date);
CREATE INDEX IF NOT EXISTS idx_meal_logs_user_date ON meal_logs(user_id, date);

CREATE TABLE IF NOT EXISTS meal_items (
    id SERIAL PRIMARY KEY,
    meal_id INTEGER NOT NULL REFERENCES meal_logs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    serving_size TEXT,
    calories INTEGER NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meal_items_meal_id ON meal_items(meal_id);

-- ---------------------------------------------------------------------------
-- Extra DDL from init_db() not in _SCHEMA
-- ---------------------------------------------------------------------------

ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS icu_event_id INTEGER;
ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS sync_hash TEXT;
ALTER TABLE planned_workouts ADD COLUMN IF NOT EXISTS synced_at TEXT;
CREATE INDEX IF NOT EXISTS idx_power_bests_duration_power ON power_bests(duration_s, power DESC, date DESC);

-- ---------------------------------------------------------------------------
-- Seed data (idempotent)
-- ---------------------------------------------------------------------------

-- Default macro targets
INSERT INTO macro_targets (user_id, calories, protein_g, carbs_g, fat_g, updated_at)
VALUES ('athlete', 2500, 150, 300, 80, CURRENT_TIMESTAMP)
ON CONFLICT (user_id) DO NOTHING;

-- Built-in workout templates
INSERT INTO workout_templates (key, name, description, category, steps, source)
VALUES ('z2_endurance', 'Z2 Endurance', 'Steady aerobic endurance ride. Keep power in Z2 (65-75% FTP).', 'base',
  '[{"type": "Warmup", "duration_seconds": 600, "power_low": 0.4, "power_high": 0.65}, {"type": "SteadyState", "duration_seconds": null, "power": 0.65}, {"type": "Cooldown", "duration_seconds": 300, "power_low": 0.65, "power_high": 0.4}]',
  'built-in')
ON CONFLICT (key) DO NOTHING;

INSERT INTO workout_templates (key, name, description, category, steps, source)
VALUES ('threshold_2x20', '2x20 Threshold', 'Two 20-minute intervals at FTP. Key workout for building sustained power.', 'build',
  '[{"type": "Warmup", "duration_seconds": 600, "power_low": 0.4, "power_high": 0.75}, {"type": "SteadyState", "duration_seconds": 1200, "power": 1.0}, {"type": "SteadyState", "duration_seconds": 300, "power": 0.5}, {"type": "SteadyState", "duration_seconds": 1200, "power": 1.0}, {"type": "Cooldown", "duration_seconds": 600, "power_low": 0.65, "power_high": 0.4}]',
  'built-in')
ON CONFLICT (key) DO NOTHING;

INSERT INTO workout_templates (key, name, description, category, steps, source)
VALUES ('sweetspot_3x15', '3x15 Sweet Spot', 'Three 15-minute intervals at 88-93% FTP. High training stress with manageable fatigue.', 'build',
  '[{"type": "Warmup", "duration_seconds": 600, "power_low": 0.4, "power_high": 0.75}, {"type": "SteadyState", "duration_seconds": 900, "power": 0.9}, {"type": "SteadyState", "duration_seconds": 300, "power": 0.5}, {"type": "SteadyState", "duration_seconds": 900, "power": 0.9}, {"type": "SteadyState", "duration_seconds": 300, "power": 0.5}, {"type": "SteadyState", "duration_seconds": 900, "power": 0.9}, {"type": "Cooldown", "duration_seconds": 600, "power_low": 0.65, "power_high": 0.4}]',
  'built-in')
ON CONFLICT (key) DO NOTHING;

INSERT INTO workout_templates (key, name, description, category, steps, source)
VALUES ('vo2max_4x4', '4x4min VO2max', 'Four 4-minute intervals at 115-120% FTP. Builds aerobic ceiling.', 'peak',
  '[{"type": "Warmup", "duration_seconds": 600, "power_low": 0.4, "power_high": 0.75}, {"type": "Intervals", "repeat": 4, "on_duration_seconds": 240, "off_duration_seconds": 240, "on_power": 1.18, "off_power": 0.5}, {"type": "Cooldown", "duration_seconds": 600, "power_low": 0.65, "power_high": 0.4}]',
  'built-in')
ON CONFLICT (key) DO NOTHING;

INSERT INTO workout_templates (key, name, description, category, steps, source)
VALUES ('race_simulation', 'Race Simulation', 'Variable-terrain simulation with surges. Mimics MTB race demands.', 'peak',
  '[{"type": "Warmup", "duration_seconds": 600, "power_low": 0.4, "power_high": 0.65}, {"type": "SteadyState", "duration_seconds": 600, "power": 0.75}, {"type": "SteadyState", "duration_seconds": 180, "power": 1.1}, {"type": "SteadyState", "duration_seconds": 300, "power": 0.65}, {"type": "SteadyState", "duration_seconds": 240, "power": 1.15}, {"type": "SteadyState", "duration_seconds": 600, "power": 0.7}, {"type": "SteadyState", "duration_seconds": 300, "power": 1.05}, {"type": "SteadyState", "duration_seconds": 300, "power": 0.55}, {"type": "SteadyState", "duration_seconds": 180, "power": 1.2}, {"type": "SteadyState", "duration_seconds": 600, "power": 0.65}, {"type": "Cooldown", "duration_seconds": 300, "power_low": 0.65, "power_high": 0.4}]',
  'built-in')
ON CONFLICT (key) DO NOTHING;

INSERT INTO workout_templates (key, name, description, category, steps, source)
VALUES ('recovery', 'Recovery Spin', 'Easy recovery ride. Keep it in Z1, legs spinning, no effort.', 'recovery',
  '[{"type": "SteadyState", "duration_seconds": null, "power": 0.45}]',
  'built-in')
ON CONFLICT (key) DO NOTHING;
