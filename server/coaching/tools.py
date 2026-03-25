"""ADK tools for the coaching agent to query training data."""

from datetime import datetime, timedelta
from server.database import get_db


def get_pmc_metrics(date: str = "") -> dict:
    """Get current fitness metrics (CTL, ATL, TSB) for a given date or today.

    Args:
        date: Date string (YYYY-MM-DD). Defaults to most recent available.

    Returns:
        Dictionary with ctl (fitness), atl (fatigue), tsb (form), weight.
    """
    with get_db() as conn:
        if date:
            row = conn.execute(
                "SELECT * FROM daily_metrics WHERE date <= ? ORDER BY date DESC LIMIT 1",
                (date,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM daily_metrics ORDER BY date DESC LIMIT 1"
            ).fetchone()

    if not row:
        return {"error": "No PMC data found"}

    return {
        "date": row["date"],
        "ctl": row["ctl"],
        "atl": row["atl"],
        "tsb": row["tsb"],
        "weight": row["weight"],
    }


def get_recent_rides(days_back: int = 7) -> list[dict]:
    """Get summary of recent completed rides.

    Args:
        days_back: Number of days to look back. Default 7.

    Returns:
        List of ride summaries with date, sport, duration, TSS, power, HR.
    """
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            """SELECT date, sub_sport, duration_s, distance_m, tss, avg_power,
                      normalized_power, avg_hr, total_ascent, best_20min_power,
                      post_ride_comments, coach_comments
               FROM rides WHERE date >= ? ORDER BY date DESC""",
            (cutoff,),
        ).fetchall()

    return [
        {
            "date": r["date"],
            "sport": r["sub_sport"],
            "duration_h": round((r["duration_s"] or 0) / 3600, 1),
            "distance_km": round((r["distance_m"] or 0) / 1000, 1),
            "tss": r["tss"],
            "avg_power": r["avg_power"],
            "normalized_power": r["normalized_power"],
            "avg_hr": r["avg_hr"],
            "ascent_m": r["total_ascent"],
            "best_20min": r["best_20min_power"],
            "athlete_post_ride_notes": r["post_ride_comments"],
            "coach_post_ride_notes": r["coach_comments"],
        }
        for r in rows
    ]


def get_upcoming_workouts(days_ahead: int = 7) -> list[dict]:
    """Get planned workouts for the coming days.

    Args:
        days_ahead: Number of days to look ahead. Default 7.

    Returns:
        List of planned workouts with date, name, duration.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, name, sport, total_duration_s, coach_notes, athlete_notes FROM planned_workouts WHERE date >= ? AND date <= ? ORDER BY date",
            (today, end),
        ).fetchall()

    return [
        {
            "date": r["date"],
            "name": r["name"],
            "sport": r["sport"],
            "duration_min": round((r["total_duration_s"] or 0) / 60),
            "coach_notes": r["coach_notes"],
            "athlete_notes": r["athlete_notes"],
        }
        for r in rows
    ]


def get_power_bests() -> dict:
    """Get all-time best power outputs at standard durations.

    Returns:
        Dictionary mapping duration labels to best power and date.
    """
    labels = {5: "5s", 30: "30s", 60: "1min", 300: "5min", 1200: "20min", 3600: "60min"}

    with get_db() as conn:
        rows = conn.execute(
            """SELECT pb.duration_s, pb.power, pb.date
               FROM power_bests pb
               JOIN (SELECT duration_s, MAX(power) as max_power FROM power_bests GROUP BY duration_s) m
                 ON pb.duration_s = m.duration_s AND pb.power = m.max_power
               ORDER BY pb.duration_s"""
        ).fetchall()

    return {
        labels.get(r["duration_s"], f"{r['duration_s']}s"): {"power": r["power"], "date": r["date"]}
        for r in rows
    }


def get_training_summary(period: str = "month") -> dict:
    """Get training volume summary for a period.

    Args:
        period: 'week', 'month', or 'season' for the summary period.

    Returns:
        Summary with ride count, hours, TSS, distance.
    """
    if period == "week":
        days = 7
    elif period == "month":
        days = 30
    else:
        days = 365

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    with get_db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as rides,
                      ROUND(CAST(SUM(duration_s) / 3600.0 AS NUMERIC), 1) as hours,
                      ROUND(CAST(SUM(COALESCE(tss, 0)) AS NUMERIC), 0) as tss,
                      ROUND(CAST(SUM(COALESCE(distance_m, 0)) / 1000.0 AS NUMERIC), 0) as distance_km,
                      ROUND(CAST(SUM(COALESCE(total_ascent, 0)) AS NUMERIC), 0) as ascent_m
               FROM rides WHERE date >= ?""",
            (cutoff,),
        ).fetchone()

    return {
        "period": period,
        "rides": row["rides"],
        "hours": row["hours"],
        "tss": row["tss"],
        "distance_km": row["distance_km"],
        "ascent_m": row["ascent_m"],
    }


def get_ftp_history() -> list[dict]:
    """Get FTP progression over time by month.

    Returns:
        List of monthly FTP values with W/kg.
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT m.month, m.max_ftp as ftp,
                      (SELECT r.weight FROM rides r WHERE SUBSTR(r.date, 1, 7) = m.month AND r.ftp = m.max_ftp LIMIT 1) as weight
               FROM (SELECT SUBSTR(date, 1, 7) as month, MAX(ftp) as max_ftp FROM rides WHERE ftp > 0 GROUP BY SUBSTR(date, 1, 7)) m
               ORDER BY m.month"""
        ).fetchall()

    return [
        {
            "month": r["month"],
            "ftp": r["ftp"],
            "weight_kg": r["weight"],
            "w_per_kg": round(r["ftp"] / r["weight"], 2) if r["weight"] and r["weight"] > 0 else None,
        }
        for r in rows
    ]


def get_periodization_status() -> dict:
    """Get the current training periodization phase and schedule.

    Returns:
        Current phase info and all phases with dates.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        phases = conn.execute(
            "SELECT * FROM periodization_phases ORDER BY start_date"
        ).fetchall()

    all_phases = []
    current = None
    for p in phases:
        phase = {
            "id": p["id"],
            "name": p["name"],
            "start_date": p["start_date"],
            "end_date": p["end_date"],
            "focus": p["focus"],
            "hours_per_week": f"{p['hours_per_week_low']}-{p['hours_per_week_high']}",
            "tss_target": f"{p['tss_target_low']}-{p['tss_target_high']}",
        }
        all_phases.append(phase)
        if p["start_date"] <= today <= p["end_date"]:
            current = phase

    return {
        "current_phase": current or {"name": "Off-season", "focus": "Recovery and base maintenance"},
        "all_phases": all_phases,
    }
