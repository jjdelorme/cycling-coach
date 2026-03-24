"""SQLite database setup and connection management."""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("COACH_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "coach.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS rides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    start_lon REAL
);

CREATE TABLE IF NOT EXISTS ride_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ride_id INTEGER NOT NULL,
    timestamp TEXT,
    power INTEGER,
    heart_rate INTEGER,
    cadence INTEGER,
    speed REAL,
    altitude REAL,
    distance REAL,
    lat REAL,
    lon REAL,
    temperature REAL,
    FOREIGN KEY (ride_id) REFERENCES rides(id)
);

CREATE TABLE IF NOT EXISTS planned_workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    name TEXT,
    sport TEXT,
    total_duration_s REAL,
    workout_xml TEXT
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    total_tss REAL,
    ctl REAL,
    atl REAL,
    tsb REAL,
    weight REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS athlete_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    value REAL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS power_bests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ride_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    duration_s INTEGER NOT NULL,
    power REAL NOT NULL,
    FOREIGN KEY (ride_id) REFERENCES rides(id)
);

CREATE TABLE IF NOT EXISTS periodization_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    author TEXT,
    role TEXT,
    content_text TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS coach_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    author TEXT,
    content_text TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coach_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_events_session ON chat_events(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_coach_memory_user ON coach_memory(user_id);
"""

DEFAULT_ATHLETE_PROFILE = """- 50-year-old male, ~163 lbs (75 kg), 5'10"
- Current FTP: ~261w, W/kg: ~3.45
- A-race: Big Sky Biggie (late August 2026) - ~50mi MTB, ~6,000ft climbing
- Experience: 291 rides / 581 hours over the past year
- Peaked at CTL 106.8 (Oct 2025), FTP 287w
- Power meter has been broken since ~Feb 25, 2026"""

DEFAULT_COACHING_PRINCIPLES = """- 12-14h/week is the sweet spot (not 15-19h)
- 3-week build / 1-week recovery cycles
- Structured intervals are essential, not just terrain-driven intensity
- 48-72h recovery after hard efforts (age-appropriate)
- Polarized approach: easy days easy, hard days hard
- Weight is a lever: every pound matters on the climbs
- When days are missed, adjust the week - don't panic, protect key workouts"""

DEFAULT_COACH_ROLE = """- Be direct, specific, and actionable
- Use the tools to check current fitness data before giving advice
- Reference specific numbers (CTL, TSS, power) when relevant
- Consider the athlete's age and recovery needs
- Always relate advice back to the athlete's goals and target events
- If asked about the plan, check the periodization status tool
- Keep responses concise - this athlete wants coaching, not lectures"""

DEFAULT_PLAN_MANAGEMENT = """- You can generate weekly training plans using generate_weekly_plan
- You can reschedule missed workouts using replan_missed_day
- You can adjust periodization phases using adjust_phase
- After adjusting phases, ASK the athlete if they want you to regenerate workouts for the affected dates
- Use regenerate_phase_workouts to rebuild workouts for a date range based on the current phases
  - It automatically applies 3-week build / 1-week recovery cycles within each phase
  - It matches workout types to the phase focus (base, build, peak, taper)
  - It scales weekly hours to the phase's target range
- Always check current fitness (PMC) before planning intensity
- When generating plans, match the focus to the current periodization phase
- After any plan changes, summarize what you did and show the updated schedule
- You can sync planned workouts to Garmin via intervals.icu using sync_workouts_to_garmin
- When asked to sync, you can sync by date, by workout name, or sync all remaining workouts this week
- After generating a weekly plan, offer to sync the workouts to Garmin
- You can update the athlete profile and coaching settings using update_coach_settings when the athlete tells you about changes (new FTP, new goals, weight changes, etc.)"""

SETTINGS_DEFAULTS = {
    "athlete_profile": DEFAULT_ATHLETE_PROFILE,
    "coaching_principles": DEFAULT_COACHING_PRINCIPLES,
    "coach_role": DEFAULT_COACH_ROLE,
    "plan_management": DEFAULT_PLAN_MANAGEMENT,
}


def get_setting(key: str) -> str:
    """Get a coach setting value, returning the default if not set."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM coach_settings WHERE key = ?", (key,)).fetchone()
    if row:
        return row["value"]
    return SETTINGS_DEFAULTS.get(key, "")


def set_setting(key: str, value: str):
    """Set a coach setting value."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO coach_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_all_settings() -> dict:
    """Get all coach settings, filling in defaults for any not yet customized."""
    result = dict(SETTINGS_DEFAULTS)
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM coach_settings").fetchall()
    for row in rows:
        result[row["key"]] = row["value"]
    return result


def get_db_path():
    return os.path.abspath(DB_PATH)


def init_db(db_path=None):
    path = db_path or get_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    return path


def get_connection(db_path=None):
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(db_path=None):
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
