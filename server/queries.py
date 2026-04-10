"""Shared data-access functions used by both ADK tools and REST routers.

Each function takes an open DB connection and returns plain dicts/rows.
Callers are responsible for managing the get_db() context and shaping
results for their consumer (LLM context vs Pydantic models vs JSON API).
"""

from datetime import datetime
from server.database import get_athlete_setting, ATHLETE_SETTINGS_DEFAULTS


def get_latest_metric(conn, key: str, as_of_date: str) -> float:
    """Get the latest metric value as of a specific date.

    Checks athlete_settings for historical accuracy (most recent entry <= as_of_date).
    Falls back to defaults if not found.
    """
    if key == 'weight':
        key = 'weight_kg'

    row = conn.execute(
        "SELECT value FROM athlete_settings WHERE key = %s AND date_set <= %s ORDER BY date_set DESC, id DESC LIMIT 1",
        (key, as_of_date),
    ).fetchone()
    if row and row["value"] is not None:
        try:
            return float(row["value"])
        except ValueError:
            return 0.0

    # Fallback to defaults
    return float(ATHLETE_SETTINGS_DEFAULTS.get(key, 0.0))


def get_current_ftp(conn) -> int:
    """Get current FTP: prefer athlete_log/settings, fall back to latest ride."""
    val = int(get_latest_metric(conn, "ftp", datetime.now().strftime("%Y-%m-%d")))
    if val > 0:
        return val

    row = conn.execute(
        "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY date DESC LIMIT 1"
    ).fetchone()
    return row["ftp"] if row else 0


def get_current_pmc_row(conn) -> dict | None:
    """Get the most recent daily_metrics row."""
    row = conn.execute(
        "SELECT * FROM daily_metrics ORDER BY date DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_pmc_row_for_date(conn, date: str) -> dict | None:
    """Get the daily_metrics row on or before a given date."""
    row = conn.execute(
        "SELECT * FROM daily_metrics WHERE date <= %s ORDER BY date DESC LIMIT 1",
        (date,),
    ).fetchone()
    return dict(row) if row else None


def get_power_bests_rows(conn, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """Get best power at each standard duration, optionally filtered by date range.

    Returns list of dicts with: duration_s, power, avg_hr, date, ride_id.
    Uses DISTINCT ON to pick the single best row per duration.
    """
    if start_date or end_date:
        sd = start_date or "2000-01-01"
        ed = end_date or datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT DISTINCT ON (duration_s) duration_s, power, avg_hr, date, ride_id
               FROM power_bests
               WHERE date >= %s AND date <= %s
               ORDER BY duration_s, power DESC, date DESC""",
            (sd, ed),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT DISTINCT ON (duration_s) duration_s, power, avg_hr, date, ride_id
               FROM power_bests
               ORDER BY duration_s, power DESC, date DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_ftp_history_rows(conn, start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """Get FTP progression by month from daily_metrics."""
    query = """SELECT SUBSTR(date, 1, 7) as month, MAX(ftp) as ftp, MAX(weight) as weight_kg
               FROM daily_metrics
               WHERE ftp > 0"""
    params = []
    if start_date:
        query += " AND date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND date <= %s"
        params.append(end_date)
    query += " GROUP BY SUBSTR(date, 1, 7) ORDER BY month"

    rows = conn.execute(query, params).fetchall()

    return [
        {
            "month": r["month"],
            "ftp": int(r["ftp"]),
            "weight_kg": round(r["weight_kg"], 1) if r["weight_kg"] else None,
            "w_per_kg": round(r["ftp"] / r["weight_kg"], 2) if r["weight_kg"] and r["weight_kg"] > 0 else None,
        }
        for r in rows
    ]


def get_periodization_phases(conn) -> list[dict]:
    """Get all periodization phases ordered by start date."""
    rows = conn.execute(
        "SELECT * FROM periodization_phases ORDER BY start_date"
    ).fetchall()
    return [dict(r) for r in rows]


def get_week_planned_and_actual(conn, start_str: str, end_str: str) -> tuple[list[dict], list[dict]]:
    """Get planned workouts and actual rides for a Mon-Sun date range.

    Returns (planned_rows, actual_rows) as lists of dicts.
    """
    planned = conn.execute(
        "SELECT * FROM planned_workouts WHERE date >= %s AND date <= %s ORDER BY date",
        (start_str, end_str),
    ).fetchall()

    actual = conn.execute(
        """SELECT id, date, sport, sub_sport, duration_s, tss, avg_power,
                  normalized_power, avg_hr, distance_m, total_ascent
           FROM rides WHERE date >= %s AND date <= %s ORDER BY date""",
        (start_str, end_str),
    ).fetchall()

    return [dict(p) for p in planned], [dict(a) for a in actual]


def get_meals_for_date(conn, date: str, user_id: str = "athlete") -> list[dict]:
    """Get all meals for a given date, ordered by logged_at."""
    rows = conn.execute(
        "SELECT * FROM meal_logs WHERE date = %s AND user_id = %s ORDER BY logged_at",
        (date, user_id),
    ).fetchall()
    return [dict(r) for r in rows]


def get_meal_items(conn, meal_id: int) -> list[dict]:
    """Get itemized breakdown for a meal."""
    rows = conn.execute(
        "SELECT * FROM meal_items WHERE meal_id = %s ORDER BY id",
        (meal_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_macro_targets(conn, user_id: str = "athlete") -> dict:
    """Get daily macro targets, falling back to defaults if no row exists."""
    row = conn.execute(
        "SELECT * FROM macro_targets WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    if row:
        return dict(row)
    return {
        "calories": 2500,
        "protein_g": 150.0,
        "carbs_g": 300.0,
        "fat_g": 80.0,
    }


def get_daily_meal_totals(conn, date: str, user_id: str = "athlete") -> dict:
    """Get aggregate macro totals for a date."""
    row = conn.execute(
        "SELECT COALESCE(SUM(total_calories), 0) AS calories, "
        "COALESCE(SUM(total_protein_g), 0) AS protein_g, "
        "COALESCE(SUM(total_carbs_g), 0) AS carbs_g, "
        "COALESCE(SUM(total_fat_g), 0) AS fat_g, "
        "COUNT(*) AS meal_count "
        "FROM meal_logs WHERE date = %s AND user_id = %s",
        (date, user_id),
    ).fetchone()
    return dict(row) if row else {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "meal_count": 0}
