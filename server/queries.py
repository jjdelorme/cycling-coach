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
    return row["ftp"] if row else 261


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


def get_ftp_history_rows(conn) -> list[dict]:
    """Get FTP progression by month from daily_metrics."""
    rows = conn.execute(
        """SELECT SUBSTR(date, 1, 7) as month, MAX(ftp) as ftp, MAX(weight) as weight
           FROM daily_metrics 
           WHERE ftp > 0 
           GROUP BY SUBSTR(date, 1, 7)
           ORDER BY month"""
    ).fetchall()

    return [
        {
            "month": r["month"],
            "ftp": int(r["ftp"]),
            "weight": round(r["weight"], 1) if r["weight"] else None,
            "w_per_kg": round(r["ftp"] / r["weight"], 2) if r["weight"] and r["weight"] > 0 else None,
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
