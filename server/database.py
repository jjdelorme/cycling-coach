"""Database setup and connection management for PostgreSQL."""

import os
import re
import time
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

from server.logging_config import get_logger, get_trace_id

logger = get_logger(__name__)
SLOW_QUERY_MS = int(os.environ.get("SLOW_QUERY_MS", "100"))

load_dotenv()

DATABASE_URL = os.environ.get(
    "CYCLING_COACH_DATABASE_URL",
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
ALTER TABLE power_bests ADD COLUMN IF NOT EXISTS avg_hr INTEGER;
ALTER TABLE power_bests ADD COLUMN IF NOT EXISTS avg_cadence INTEGER;
ALTER TABLE power_bests ADD COLUMN IF NOT EXISTS start_offset_s INTEGER;
CREATE INDEX IF NOT EXISTS idx_power_bests_composite ON power_bests(duration_s, date DESC);
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
        adapted = self._adapt_sql(sql)
        t0 = time.monotonic()
        self._cursor.execute(adapted, params)
        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms >= SLOW_QUERY_MS:
            sql_preview = adapted[:200] + ("..." if len(adapted) > 200 else "")
            logger.warning(
                "slow_query",
                latency_ms=round(elapsed_ms, 1),
                sql=sql_preview,
                trace_id=get_trace_id(),
            )
        return self._cursor

    def executemany(self, sql, params_list, page_size=1000):
        adapted = self._adapt_sql(sql)
        t0 = time.monotonic()
        psycopg2.extras.execute_batch(self._cursor, adapted, params_list, page_size=page_size)
        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms >= SLOW_QUERY_MS:
            sql_preview = adapted[:200] + ("..." if len(adapted) > 200 else "")
            logger.warning(
                "slow_executemany",
                latency_ms=round(elapsed_ms, 1),
                rows=len(params_list),
                sql=sql_preview,
                trace_id=get_trace_id(),
            )
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

DEFAULT_ATHLETE_PROFILE = """- Experience: [Set your training background and years of experience]
- Goals: [Describe your A-race or primary goal event with date and distance]
- Strengths: [e.g., climbing, sustained power, sprinting]
- Limiters: [e.g., VO2max, lactate threshold, technical skills]
- Constraints: [Available training hours per week, preferred training days/times]"""

DEFAULT_COACHING_PRINCIPLES = """- Match weekly volume to the athlete's available time and current periodization phase
- Build/recovery cycle length should reflect the athlete's recovery capacity and training age
- Structured intervals are essential, not just terrain-driven intensity
- Allow 48-72h recovery after hard efforts; adjust for athlete age and accumulated fatigue
- Polarized approach: easy days easy, hard days hard
- When days are missed, adjust the week - don't panic, protect key workouts"""

DEFAULT_COACH_ROLE = """- Be direct, specific, and actionable
- Use the tools to check current fitness data before giving advice
- Reference specific numbers (CTL, TSS, power) when relevant
- Consider the athlete's age and recovery needs
- Always relate advice back to the athlete's goals and target events
- If asked about the plan, check the periodization status tool
- Keep responses concise - this athlete wants coaching, not lectures
- When analyzing a specific ride, use get_ride_analysis first for the computed summary, then get_ride_segments to see how the ride progressed over time
- Use get_ride_records_window to drill into specific intervals (use start_offset_s from best efforts)
- Use get_power_curve with date ranges to compare fitness across training blocks
- When power data is unavailable (has_power = false), focus on HR zones, HR drift, and perceived effort"""

DEFAULT_PLAN_MANAGEMENT = """CRITICAL: When you recommend changing, swapping, or adjusting a workout, you MUST call replace_workout or generate_week_from_spec to persist the change. Never just verbally recommend a different workout — the calendar reads from the database.

BEFORE PRESCRIBING ANY WORKOUT OR PLANNING A WEEK, you MUST check:
1. get_pmc_metrics — current CTL, ATL, TSB
2. get_recent_rides(14) — recent load, ride quality, power trends
3. get_periodization_status — current phase focus, hour/TSS targets
4. Consider: Is TSB dropping? Is power declining? Is the athlete fresh or buried?

ADAPTIVE DECISIONS:
- TSB below -20: prescribe easier workouts; consider early recovery week
- TSB above +10: athlete is fresh — can handle more intensity or volume
- Power declining or high HR drift in recent rides: fatigue signal — back off
- Strong recent power, low decoupling: good form — can push harder
- Phase focus determines workout TYPE (base=aerobic/endurance, build=threshold+VO2max, peak=race-specific)
- Phase hour/TSS targets set volume, but adjust down if athlete is fatigued

WEEKLY PLANNING — use generate_week_from_spec:
- Call list_workout_templates to see what's available by category
- Choose templates OR design custom workouts based on athlete state
- Provide personalized coach_notes for EVERY workout referencing current TSB and recent load
- Do NOT follow a rigid 3:1 build/recovery cycle — insert recovery weeks based on actual fatigue
- After generating, offer to sync to Garmin via sync_workouts_to_garmin

SINGLE WORKOUT CHANGES — use replace_workout:
- Template mode for standard workouts; custom mode for specific interval prescriptions
- Always call set_workout_coach_notes after replace_workout with contextual notes
- Use replan_missed_day to reschedule, then update notes for new date context

COACH NOTES — MANDATORY:
Every workout needs personalized notes. Include:
- Current form context ("TSB is -15 after a hard block — keep this truly easy")
- Specific execution cues (target HR cap, power range, cadence, terrain)
- How it fits the week ("This is your quality session — the Wednesday Z2 was prep for this")
Never write notes like "Easy ride today" when you have athlete data — use it."""

SETTINGS_DEFAULTS = {
    "athlete_profile": DEFAULT_ATHLETE_PROFILE,
    "coaching_principles": DEFAULT_COACHING_PRINCIPLES,
    "coach_role": DEFAULT_COACH_ROLE,
    "plan_management": DEFAULT_PLAN_MANAGEMENT,
    "intervals_icu_api_key": "",
    "intervals_icu_athlete_id": "",
    "units": "imperial",
    "theme": "dark",
    "gemini_model": "",
    "gcp_location": "",
    "gemini_api_key": "",
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
    "lthr": "",             # Lactate threshold HR (bpm)
    "max_hr": "",           # Max heart rate (bpm)
    "resting_hr": "",       # Resting heart rate (bpm)
    "ftp": "0",             # Functional threshold power (watts)
    "weight_kg": "0",       # Weight in kg
    "age": "",              # Age
    "gender": "",           # Gender (for hrTSS scaling)
}


def get_athlete_setting(key: str) -> str:
    """Get an athlete setting value, returning the default if not set."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM athlete_settings WHERE key = %s AND is_active = TRUE", (key,)).fetchone()
    if row:
        return row["value"]
    return ATHLETE_SETTINGS_DEFAULTS.get(key, "")


def set_athlete_setting(key: str, value: str, date_set: str = None):
    """Set an athlete setting value, deactivating the old one."""
    from datetime import datetime
    if not date_set:
        date_set = datetime.now().strftime("%Y-%m-%d")
    
    with get_db() as conn:
        # Deactivate current active setting
        conn.execute(
            "UPDATE athlete_settings SET is_active = FALSE WHERE key = %s AND is_active = TRUE",
            (key,)
        )
        # Insert new active setting
        conn.execute(
            "INSERT INTO athlete_settings (key, value, date_set, is_active) VALUES (%s, %s, %s, TRUE)",
            (key, value, date_set),
        )


def get_all_athlete_settings() -> dict:
    """Get all active athlete settings, filling in defaults for any not yet customized."""
    result = dict(ATHLETE_SETTINGS_DEFAULTS)
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM athlete_settings WHERE is_active = TRUE").fetchall()
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
    # Migrations: add sync tracking columns to planned_workouts
    for col, col_type in [("icu_event_id", "INTEGER"), ("sync_hash", "TEXT"), ("synced_at", "TEXT")]:
        try:
            cur = conn.cursor()
            cur.execute(f"ALTER TABLE planned_workouts ADD COLUMN {col} {col_type}")
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
    
    # Migrations for v1.5.2: Foundations & Metric Integrity
    v152_migrations = [
        "ALTER TABLE rides ADD COLUMN IF NOT EXISTS has_power_data BOOLEAN DEFAULT FALSE",
        "ALTER TABLE rides ADD COLUMN IF NOT EXISTS data_status TEXT DEFAULT 'raw'",
        "ALTER TABLE power_bests ADD COLUMN IF NOT EXISTS avg_hr INTEGER",
        "ALTER TABLE power_bests ADD COLUMN IF NOT EXISTS avg_cadence INTEGER",
        "ALTER TABLE power_bests ADD COLUMN IF NOT EXISTS start_offset_s INTEGER",
        "CREATE INDEX IF NOT EXISTS idx_power_bests_composite ON power_bests(duration_s, date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_power_bests_duration_power ON power_bests(duration_s, power DESC, date DESC)"
    ]
    for stmt in v152_migrations:
        try:
            cur = conn.cursor()
            cur.execute(stmt)
            conn.commit()
            cur.close()
        except Exception as e:
            logger.warning("migration_skipped", reason=str(e), stmt=stmt[:80])
            conn.rollback()
    
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
