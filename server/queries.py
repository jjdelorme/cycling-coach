"""Shared data-access functions used by both ADK tools and REST routers.

Each function takes an open DB connection and returns plain dicts/rows.
Callers are responsible for managing the get_db() context and shaping
results for their consumer (LLM context vs Pydantic models vs JSON API).
"""

from datetime import datetime
from server.database import get_athlete_setting


def get_current_ftp(conn) -> int:
    """Get current FTP: prefer athlete_settings, fall back to latest ride."""
    try:
        val = int(get_athlete_setting("ftp") or 0)
        if val > 0:
            return val
    except (ValueError, TypeError):
        pass
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

    Returns list of dicts with: duration_s, power, date, ride_id.
    """
    if start_date or end_date:
        sd = start_date or "2000-01-01"
        ed = end_date or datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT pb.duration_s, pb.power, pb.date, pb.ride_id
               FROM power_bests pb
               JOIN (SELECT duration_s, MAX(power) as max_power
                     FROM power_bests WHERE date >= %s AND date <= %s
                     GROUP BY duration_s) m
                 ON pb.duration_s = m.duration_s AND pb.power = m.max_power
               WHERE pb.date >= %s AND pb.date <= %s
               ORDER BY pb.duration_s""",
            (sd, ed, sd, ed),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT pb.duration_s, pb.power, pb.date, pb.ride_id
               FROM power_bests pb
               JOIN (SELECT duration_s, MAX(power) as max_power FROM power_bests GROUP BY duration_s) m
                 ON pb.duration_s = m.duration_s AND pb.power = m.max_power
               ORDER BY pb.duration_s"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_ftp_history_rows(conn) -> list[dict]:
    """Get FTP progression by month, including current athlete setting.

    Returns list of dicts with: month, ftp, weight, w_per_kg, and optionally source.
    """
    rows = conn.execute(
        """SELECT m.month, m.max_ftp as ftp,
                  (SELECT r.weight FROM rides r WHERE SUBSTR(r.date, 1, 7) = m.month AND r.ftp = m.max_ftp LIMIT 1) as weight
           FROM (SELECT SUBSTR(date, 1, 7) as month, MAX(ftp) as max_ftp FROM rides WHERE ftp > 0 GROUP BY SUBSTR(date, 1, 7)) m
           ORDER BY m.month"""
    ).fetchall()

    result = [
        {
            "month": r["month"],
            "ftp": r["ftp"],
            "weight": r["weight"],
            "w_per_kg": round(r["ftp"] / r["weight"], 2) if r["weight"] and r["weight"] > 0 else None,
        }
        for r in rows
    ]

    # Append current athlete_settings FTP if it differs from the latest ride-based entry
    try:
        current_ftp = int(get_athlete_setting("ftp") or 0)
    except (ValueError, TypeError):
        current_ftp = 0
    if current_ftp > 0:
        current_month = datetime.now().strftime("%Y-%m")
        last_ftp = result[-1]["ftp"] if result else 0
        last_month = result[-1]["month"] if result else ""
        if current_ftp != last_ftp or current_month != last_month:
            try:
                weight = float(get_athlete_setting("weight_kg") or 0)
            except (ValueError, TypeError):
                weight = 0
            entry = {
                "month": current_month,
                "ftp": current_ftp,
                "weight": weight if weight > 0 else None,
                "w_per_kg": round(current_ftp / weight, 2) if weight > 0 else None,
                "source": "athlete_setting",
            }
            if result and last_month == current_month:
                result[-1] = entry
            else:
                result.append(entry)

    return result


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
