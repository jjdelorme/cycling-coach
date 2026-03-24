"""ADK tools for the coaching agent to manage the training plan."""

from datetime import datetime, timedelta
from server.database import get_db
from server.services.workout_generator import generate_zwo, WORKOUT_TEMPLATES


def replan_missed_day(missed_date: str, new_target_date: str) -> dict:
    """Move a planned workout from a missed day to a new date.

    Args:
        missed_date: The date that was missed (YYYY-MM-DD).
        new_target_date: The new date to schedule the workout (YYYY-MM-DD).

    Returns:
        Status of the replan operation.
    """
    with get_db() as conn:
        workouts = conn.execute(
            "SELECT * FROM planned_workouts WHERE date = ?", (missed_date,)
        ).fetchall()

        if not workouts:
            return {"status": "no_workout", "message": f"No planned workout found on {missed_date}"}

        # Check if target date already has a workout
        existing = conn.execute(
            "SELECT * FROM planned_workouts WHERE date = ?", (new_target_date,)
        ).fetchall()

        if existing:
            # Move existing workout to make room
            conn.execute(
                "UPDATE planned_workouts SET date = ? WHERE date = ?",
                (missed_date, new_target_date),
            )

        # Move the missed workout to the new date
        conn.execute(
            "UPDATE planned_workouts SET date = ? WHERE date = ?",
            (new_target_date, missed_date),
        )

    moved_names = [dict(w)["name"] for w in workouts]
    result = {
        "status": "success",
        "message": f"Moved {len(workouts)} workout(s) from {missed_date} to {new_target_date}",
        "workouts_moved": moved_names,
    }
    if existing:
        result["swapped_with"] = [dict(w)["name"] for w in existing]

    return result


def generate_weekly_plan(start_date: str, focus: str = "base", hours: float = 12.0) -> dict:
    """Generate a week of planned workouts and save them to the database.

    Args:
        start_date: Monday of the week to plan (YYYY-MM-DD).
        focus: Training focus - 'base', 'build', 'peak', or 'recovery'.
        hours: Target weekly hours.

    Returns:
        The generated weekly plan with workout details.
    """
    dt = datetime.fromisoformat(start_date)
    # Ensure it's a Monday
    if dt.weekday() != 0:
        dt = dt - timedelta(days=dt.weekday())

    # Define weekly templates based on focus
    templates = {
        "base": [
            ("recovery", 60),        # Mon: recovery or off
            ("z2_endurance", 90),     # Tue: Z2 endurance
            ("z2_endurance", 90),     # Wed: Z2 endurance
            ("sweetspot_3x15", 75),   # Thu: sweet spot
            None,                      # Fri: off
            ("z2_endurance", 180),    # Sat: long ride
            ("z2_endurance", 120),    # Sun: endurance
        ],
        "build": [
            ("recovery", 60),            # Mon: recovery
            ("threshold_2x20", 90),      # Tue: threshold
            ("z2_endurance", 90),         # Wed: easy
            ("vo2max_4x4", 75),           # Thu: VO2max
            ("recovery", 45),            # Fri: easy spin
            ("z2_endurance", 240),        # Sat: long MTB
            ("z2_endurance", 150),        # Sun: endurance
        ],
        "peak": [
            ("recovery", 60),             # Mon: recovery
            ("threshold_2x20", 90),       # Tue: threshold
            ("z2_endurance", 75),          # Wed: easy
            ("vo2max_4x4", 75),            # Thu: VO2max
            None,                           # Fri: off
            ("race_simulation", 180),      # Sat: race sim
            ("z2_endurance", 120),         # Sun: endurance
        ],
        "recovery": [
            None,                          # Mon: off
            ("recovery", 45),             # Tue: easy spin
            ("z2_endurance", 60),          # Wed: easy
            None,                          # Thu: off
            ("recovery", 45),             # Fri: easy spin
            ("z2_endurance", 90),          # Sat: easy ride
            None,                          # Sun: off
        ],
    }

    week_template = templates.get(focus, templates["base"])

    # Scale durations to match target hours
    total_planned_min = sum(d for t in week_template if t for _, d in [t])
    scale = (hours * 60) / total_planned_min if total_planned_min > 0 else 1.0

    workouts_created = []

    with get_db() as conn:
        # Get current FTP
        ftp_row = conn.execute(
            "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY date DESC LIMIT 1"
        ).fetchone()
        ftp = ftp_row["ftp"] if ftp_row else 261

        for day_offset, template in enumerate(week_template):
            if template is None:
                continue

            workout_type, base_duration = template
            duration = max(30, round(base_duration * scale))
            date_str = (dt + timedelta(days=day_offset)).strftime("%Y-%m-%d")

            # Remove any existing workout on this date
            conn.execute("DELETE FROM planned_workouts WHERE date = ?", (date_str,))

            # Generate ZWO
            xml_str, name = generate_zwo(workout_type, duration, ftp)

            conn.execute(
                "INSERT INTO planned_workouts (date, name, sport, total_duration_s, workout_xml) VALUES (?, ?, ?, ?, ?)",
                (date_str, name, "bike", duration * 60, xml_str),
            )

            workouts_created.append({
                "date": date_str,
                "day": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day_offset],
                "name": name,
                "duration_min": duration,
            })

    return {
        "status": "success",
        "week_start": dt.strftime("%Y-%m-%d"),
        "focus": focus,
        "target_hours": hours,
        "ftp": ftp,
        "workouts": workouts_created,
    }


def adjust_phase(phase_name: str, new_end_date: str, reason: str) -> dict:
    """Adjust the end date of a periodization phase.

    Args:
        phase_name: Name of the phase to adjust (e.g., 'Base Rebuild', 'Build 1').
        new_end_date: New end date for the phase (YYYY-MM-DD).
        reason: Reason for the adjustment.

    Returns:
        Status of the adjustment.
    """
    with get_db() as conn:
        phase = conn.execute(
            "SELECT * FROM periodization_phases WHERE name = ?", (phase_name,)
        ).fetchone()

        if not phase:
            return {"status": "error", "message": f"Phase '{phase_name}' not found"}

        old_end = phase["end_date"]
        conn.execute(
            "UPDATE periodization_phases SET end_date = ? WHERE name = ?",
            (new_end_date, phase_name),
        )

        # If extending, push subsequent phases
        if new_end_date > old_end:
            diff_days = (datetime.fromisoformat(new_end_date) - datetime.fromisoformat(old_end)).days
            subsequent = conn.execute(
                "SELECT * FROM periodization_phases WHERE start_date > ? ORDER BY start_date",
                (old_end,),
            ).fetchall()

            for s in subsequent:
                new_start = (datetime.fromisoformat(s["start_date"]) + timedelta(days=diff_days)).strftime("%Y-%m-%d")
                new_s_end = (datetime.fromisoformat(s["end_date"]) + timedelta(days=diff_days)).strftime("%Y-%m-%d")
                conn.execute(
                    "UPDATE periodization_phases SET start_date = ?, end_date = ? WHERE id = ?",
                    (new_start, new_s_end, s["id"]),
                )

    return {
        "status": "success",
        "phase": phase_name,
        "old_end_date": old_end,
        "new_end_date": new_end_date,
        "reason": reason,
    }


def get_week_summary(date: str = "") -> dict:
    """Get a combined view of planned vs actual workouts for a week.

    Args:
        date: Any date in the target week (YYYY-MM-DD). Defaults to current week.

    Returns:
        Weekly overview with planned, actual rides, and compliance.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    dt = datetime.fromisoformat(date)
    start = dt - timedelta(days=dt.weekday())
    end = start + timedelta(days=6)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    with get_db() as conn:
        planned = conn.execute(
            "SELECT date, name, total_duration_s FROM planned_workouts WHERE date >= ? AND date <= ? ORDER BY date",
            (start_str, end_str),
        ).fetchall()

        actual = conn.execute(
            """SELECT date, sub_sport, duration_s, tss, avg_power, normalized_power, avg_hr
               FROM rides WHERE date >= ? AND date <= ? ORDER BY date""",
            (start_str, end_str),
        ).fetchall()

        # Weekly totals
        total_tss = sum(r["tss"] or 0 for r in actual)
        total_hours = sum((r["duration_s"] or 0) / 3600 for r in actual)

    return {
        "week": f"{start_str} to {end_str}",
        "planned_workouts": [
            {"date": p["date"], "name": p["name"], "duration_min": round((p["total_duration_s"] or 0) / 60)}
            for p in planned
        ],
        "actual_rides": [
            {
                "date": r["date"],
                "sport": r["sub_sport"],
                "duration_h": round((r["duration_s"] or 0) / 3600, 1),
                "tss": r["tss"],
                "avg_power": r["avg_power"],
                "np": r["normalized_power"],
                "avg_hr": r["avg_hr"],
            }
            for r in actual
        ],
        "total_hours": round(total_hours, 1),
        "total_tss": round(total_tss),
        "rides_count": len(actual),
        "planned_count": len(planned),
    }
