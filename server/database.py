"""Database setup and connection management for PostgreSQL."""

import os
import re
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:dev@localhost:5432/coach",
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
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
    notes TEXT
);

CREATE TABLE IF NOT EXISTS athlete_log (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    value REAL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS power_bests (
    id SERIAL PRIMARY KEY,
    ride_id INTEGER NOT NULL REFERENCES rides(id),
    date TEXT NOT NULL,
    duration_s INTEGER NOT NULL,
    power REAL NOT NULL
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
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

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
"""

# ---------------------------------------------------------------------------
# Connection wrapper
# ---------------------------------------------------------------------------


class _DbConnection:
    """Wrapper providing a dict-cursor interface over psycopg2."""

    def __init__(self, conn):
        self._conn = conn
        self._cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    @staticmethod
    def _adapt_sql(sql):
        """Convert SQLite-style placeholders to psycopg2 format."""
        # Convert ? positional params to %s
        sql = sql.replace("?", "%s")
        # Convert :name named params to %(name)s
        sql = re.sub(r":([a-zA-Z_]\w*)", r"%(\1)s", sql)
        return sql

    def execute(self, sql, params=None):
        sql = self._adapt_sql(sql)
        self._cursor.execute(sql, params)
        return self._cursor

    def executemany(self, sql, params_list):
        sql = self._adapt_sql(sql)
        for params in params_list:
            self._cursor.execute(sql, params)
        return self._cursor

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._cursor.close()
        self._conn.close()


# ---------------------------------------------------------------------------
# Settings defaults
# ---------------------------------------------------------------------------

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

DEFAULT_PLAN_MANAGEMENT = """- CRITICAL: When you recommend changing, swapping, or adjusting a workout, you MUST call replace_workout to persist the change to the database. Never just verbally recommend a different workout without updating the plan. The calendar and all other views read from the database — if you don't call the tool, your advice will contradict what the athlete sees everywhere else.
- You can generate weekly training plans using generate_weekly_plan
- You can replace a single day's workout using replace_workout — use this when the athlete wants to change one day without affecting the rest of the week
  - For standard workouts, use template mode (workout_type) — use list_workout_templates to see what's available
  - For specific prescriptions, use custom mode (name + description + steps) to design the exact intervals, power targets, and durations
  - Always include coaching notes in the description: RPE cues, cadence targets, terrain suggestions, what to focus on
- You can browse and manage workout templates using list_workout_templates and save_workout_template
  - If the athlete likes a workout, offer to save it as a reusable template with save_workout_template
  - You can create templates from scratch or extract them from existing planned workouts (from_workout_id)
  - Templates are stored in the database and available for future use
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
    "intervals_icu_api_key": "",
    "intervals_icu_athlete_id": "",
    "units": "imperial",
}


def get_setting(key: str) -> str:
    """Get a coach setting value, returning the default if not set."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM coach_settings WHERE key = %s", (key,)).fetchone()
    if row:
        return row["value"]
    return SETTINGS_DEFAULTS.get(key, "")


def set_setting(key: str, value: str):
    """Set a coach setting value."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO coach_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
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


# ---------------------------------------------------------------------------
# Athlete settings (structured numeric/string values)
# ---------------------------------------------------------------------------

ATHLETE_SETTINGS_DEFAULTS = {
    "lthr": "158",          # Lactate threshold HR (bpm)
    "max_hr": "175",        # Max heart rate (bpm)
    "resting_hr": "48",     # Resting heart rate (bpm)
    "ftp": "261",           # Functional threshold power (watts)
    "weight_kg": "74",      # Weight in kg
    "age": "50",            # Age
    "gender": "male",       # Gender (for hrTSS scaling)
}


def get_athlete_setting(key: str) -> str:
    """Get an athlete setting value, returning the default if not set."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM athlete_settings WHERE key = %s", (key,)).fetchone()
    if row:
        return row["value"]
    return ATHLETE_SETTINGS_DEFAULTS.get(key, "")


def set_athlete_setting(key: str, value: str):
    """Set an athlete setting value."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO athlete_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, value),
        )


def get_all_athlete_settings() -> dict:
    """Get all athlete settings, filling in defaults for any not yet customized."""
    result = dict(ATHLETE_SETTINGS_DEFAULTS)
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM athlete_settings").fetchall()
    for row in rows:
        result[row["key"]] = row["value"]
    return result


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def _get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Initialize database schema and seed data."""
    conn = _get_connection()
    cur = conn.cursor()
    for stmt in _SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            cur.execute(stmt)
    conn.commit()
    _seed_workout_templates(conn)
    cur.close()
    conn.close()


def _seed_workout_templates(conn):
    """Seed built-in workout templates if the table is empty."""
    import json
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM workout_templates")
    count = cur.fetchone()[0]
    if count > 0:
        cur.close()
        return

    templates = _get_seed_templates()
    for t in templates:
        cur.execute(
            "INSERT INTO workout_templates (key, name, description, category, steps, source) VALUES (%s, %s, %s, %s, %s, %s)",
            (t["key"], t["name"], t["description"], t["category"], json.dumps(t["steps"]), "built-in"),
        )
    conn.commit()
    cur.close()


def _get_seed_templates():
    return [
        {
            "key": "z2_endurance",
            "name": "Z2 Endurance",
            "description": "Steady aerobic endurance ride. Keep power in Z2 (65-75% FTP).",
            "category": "base",
            "steps": [
                {"type": "Warmup", "duration_seconds": 600, "power_low": 0.40, "power_high": 0.65},
                {"type": "SteadyState", "duration_seconds": None, "power": 0.65},
                {"type": "Cooldown", "duration_seconds": 300, "power_low": 0.65, "power_high": 0.40},
            ],
        },
        {
            "key": "threshold_2x20",
            "name": "2x20 Threshold",
            "description": "Two 20-minute intervals at FTP. Key workout for building sustained power.",
            "category": "build",
            "steps": [
                {"type": "Warmup", "duration_seconds": 600, "power_low": 0.40, "power_high": 0.75},
                {"type": "SteadyState", "duration_seconds": 1200, "power": 1.00},
                {"type": "SteadyState", "duration_seconds": 300, "power": 0.50},
                {"type": "SteadyState", "duration_seconds": 1200, "power": 1.00},
                {"type": "Cooldown", "duration_seconds": 600, "power_low": 0.65, "power_high": 0.40},
            ],
        },
        {
            "key": "sweetspot_3x15",
            "name": "3x15 Sweet Spot",
            "description": "Three 15-minute intervals at 88-93% FTP. High training stress with manageable fatigue.",
            "category": "build",
            "steps": [
                {"type": "Warmup", "duration_seconds": 600, "power_low": 0.40, "power_high": 0.75},
                {"type": "SteadyState", "duration_seconds": 900, "power": 0.90},
                {"type": "SteadyState", "duration_seconds": 300, "power": 0.50},
                {"type": "SteadyState", "duration_seconds": 900, "power": 0.90},
                {"type": "SteadyState", "duration_seconds": 300, "power": 0.50},
                {"type": "SteadyState", "duration_seconds": 900, "power": 0.90},
                {"type": "Cooldown", "duration_seconds": 600, "power_low": 0.65, "power_high": 0.40},
            ],
        },
        {
            "key": "vo2max_4x4",
            "name": "4x4min VO2max",
            "description": "Four 4-minute intervals at 115-120% FTP. Builds aerobic ceiling.",
            "category": "peak",
            "steps": [
                {"type": "Warmup", "duration_seconds": 600, "power_low": 0.40, "power_high": 0.75},
                {"type": "Intervals", "repeat": 4, "on_duration_seconds": 240, "off_duration_seconds": 240, "on_power": 1.18, "off_power": 0.50},
                {"type": "Cooldown", "duration_seconds": 600, "power_low": 0.65, "power_high": 0.40},
            ],
        },
        {
            "key": "race_simulation",
            "name": "Race Simulation",
            "description": "Variable-terrain simulation with surges. Mimics MTB race demands.",
            "category": "peak",
            "steps": [
                {"type": "Warmup", "duration_seconds": 600, "power_low": 0.40, "power_high": 0.65},
                {"type": "SteadyState", "duration_seconds": 600, "power": 0.75},
                {"type": "SteadyState", "duration_seconds": 180, "power": 1.10},
                {"type": "SteadyState", "duration_seconds": 300, "power": 0.65},
                {"type": "SteadyState", "duration_seconds": 240, "power": 1.15},
                {"type": "SteadyState", "duration_seconds": 600, "power": 0.70},
                {"type": "SteadyState", "duration_seconds": 300, "power": 1.05},
                {"type": "SteadyState", "duration_seconds": 300, "power": 0.55},
                {"type": "SteadyState", "duration_seconds": 180, "power": 1.20},
                {"type": "SteadyState", "duration_seconds": 600, "power": 0.65},
                {"type": "Cooldown", "duration_seconds": 300, "power_low": 0.65, "power_high": 0.40},
            ],
        },
        {
            "key": "recovery",
            "name": "Recovery Spin",
            "description": "Easy recovery ride. Keep it in Z1, legs spinning, no effort.",
            "category": "recovery",
            "steps": [
                {"type": "SteadyState", "duration_seconds": None, "power": 0.45},
            ],
        },
    ]


def get_connection():
    return _DbConnection(_get_connection())


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
