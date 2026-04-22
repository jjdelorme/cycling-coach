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
# Connection wrapper
# ---------------------------------------------------------------------------


class _DbConnection:
    """Wrapper providing a dict-cursor interface over psycopg2."""

    def __init__(self, conn):
        self._conn = conn

    @staticmethod
    def _adapt_sql(sql):
        """Convert SQLite-style placeholders to psycopg2 format."""
        # Convert ? positional params to %s
        sql = sql.replace("?", "%s")
        # Convert :name named params to %(name)s
        sql = re.sub(r"(?<!:):([a-zA-Z_]\w*)", r"%(\1)s", sql)
        return sql

    def execute(self, sql, params=None):
        adapted = self._adapt_sql(sql)
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        t0 = time.monotonic()
        cursor.execute(adapted, params)
        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms >= SLOW_QUERY_MS:
            sql_preview = adapted[:200] + ("..." if len(adapted) > 200 else "")
            logger.warning(
                "slow_query",
                latency_ms=round(elapsed_ms, 1),
                sql=sql_preview,
                trace_id=get_trace_id(),
            )
        return cursor

    def executemany(self, sql, params_list, page_size=1000):
        adapted = self._adapt_sql(sql)
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        t0 = time.monotonic()
        psycopg2.extras.execute_batch(cursor, adapted, params_list, page_size=page_size)
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
        return cursor

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
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

DEFAULT_DIETARY_PREFERENCES = """- Diet type: [e.g., no restrictions, vegetarian, Mediterranean]
- Allergies: [e.g., none, tree nuts, shellfish]
- Intolerances: [e.g., lactose, gluten]
- Disliked foods: [e.g., liver, beets]
- Liked foods: [e.g., salmon, oatmeal, sweet potatoes]
- Eating schedule: [e.g., 3 meals + 2 snacks, intermittent fasting 16:8]
- Cooking ability: [e.g., enjoys cooking, prefers simple meals]
- Supplement use: [e.g., whey protein post-ride, electrolyte mix]"""

DEFAULT_NUTRITIONIST_PRINCIPLES = """- Periodize nutrition to match training load — more carbs on hard/long days, moderate on easy days
- Prioritize whole foods over supplements
- Pre-ride meals: easily digestible carbs 2-3h before, avoid high fat/fiber
- Post-ride: 3:1 carb:protein within 30 minutes of hard sessions
- On-bike fueling: 60-90g carbs/hour for rides > 90 minutes
- Rest day: maintain protein (1.6-2.0 g/kg), reduce total carbs
- Don't over-restrict — chronic deficit impairs training adaptation"""

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
    "dietary_preferences": DEFAULT_DIETARY_PREFERENCES,
    "nutritionist_principles": DEFAULT_NUTRITIONIST_PRINCIPLES,
    "intervals_icu_api_key": "",
    "intervals_icu_athlete_id": "",
    "units": "imperial",
    "theme": "dark",
    "gemini_model": "",
    "gcp_location": "",
    "gemini_api_key": "",
    "withings_access_token": "",
    "withings_refresh_token": "",
    "withings_token_expiry": "",
    "withings_user_id": "",
    "withings_oauth_state": "",
    "withings_webhook_url": "",
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
    "lthr": "0",            # Lactate threshold HR (bpm)
    "max_hr": "0",          # Max heart rate (bpm)
    "resting_hr": "0",      # Resting heart rate (bpm)
    "ftp": "0",             # Functional threshold power (watts)
    "weight_kg": "0",       # Weight in kg
    "age": "0",             # Age
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
    if not date_set:
        from server.utils.dates import user_today
        date_set = user_today()
    
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
