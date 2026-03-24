"""ADK tools for the coaching agent to manage the training plan."""

from datetime import datetime, timedelta
from server.database import get_db, get_setting, set_setting, get_all_settings
from server.services.workout_generator import generate_zwo, WORKOUT_TEMPLATES
from server.services.intervals_icu import push_workout, is_configured as icu_is_configured


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
    """Adjust the end date of a periodization phase and keep subsequent phases contiguous.

    Subsequent phases retain their original durations but shift so each starts
    the day after the previous phase ends. This prevents gaps or overlaps.

    Args:
        phase_name: Name of the phase to adjust (e.g., 'Base Rebuild', 'Build 1').
        new_end_date: New end date for the phase (YYYY-MM-DD).
        reason: Reason for the adjustment.

    Returns:
        Status of the adjustment including updated schedule for all affected phases.
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

        # Cascade: keep subsequent phases contiguous, preserving each phase's duration
        subsequent = conn.execute(
            "SELECT * FROM periodization_phases WHERE start_date > ? ORDER BY start_date",
            (phase["start_date"],),
        ).fetchall()

        adjusted = []
        cursor = datetime.fromisoformat(new_end_date) + timedelta(days=1)

        for s in subsequent:
            original_duration = (datetime.fromisoformat(s["end_date"]) - datetime.fromisoformat(s["start_date"])).days
            new_start = cursor.strftime("%Y-%m-%d")
            new_end = (cursor + timedelta(days=original_duration)).strftime("%Y-%m-%d")
            conn.execute(
                "UPDATE periodization_phases SET start_date = ?, end_date = ? WHERE id = ?",
                (new_start, new_end, s["id"]),
            )
            adjusted.append({"name": s["name"], "start_date": new_start, "end_date": new_end})
            cursor = datetime.fromisoformat(new_end) + timedelta(days=1)

    return {
        "status": "success",
        "phase": phase_name,
        "old_end_date": old_end,
        "new_end_date": new_end_date,
        "reason": reason,
        "adjusted_phases": adjusted,
        "note": "Periodization dates updated. Existing planned workouts were NOT changed. "
                "Ask the athlete if they'd like you to regenerate workouts for the affected date range "
                "using regenerate_phase_workouts.",
    }


def regenerate_phase_workouts(start_date: str = "", end_date: str = "") -> dict:
    """Regenerate planned workouts for a date range based on the periodization phases.

    Looks up which phase each week falls in and generates appropriate workouts
    using 3-week build / 1-week recovery cycles within each phase. Replaces any
    existing planned workouts in the date range.

    Args:
        start_date: Start date (YYYY-MM-DD). Defaults to today.
        end_date: End date (YYYY-MM-DD). Defaults to end of last periodization phase.

    Returns:
        Summary of generated workouts by week and phase.
    """
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    # Weekly templates by focus (same as generate_weekly_plan)
    templates = {
        "base": [
            ("recovery", 60),
            ("z2_endurance", 90),
            ("z2_endurance", 90),
            ("sweetspot_3x15", 75),
            None,
            ("z2_endurance", 180),
            ("z2_endurance", 120),
        ],
        "build": [
            ("recovery", 60),
            ("threshold_2x20", 90),
            ("z2_endurance", 90),
            ("vo2max_4x4", 75),
            ("recovery", 45),
            ("z2_endurance", 240),
            ("z2_endurance", 150),
        ],
        "peak": [
            ("recovery", 60),
            ("threshold_2x20", 90),
            ("z2_endurance", 75),
            ("vo2max_4x4", 75),
            None,
            ("race_simulation", 180),
            ("z2_endurance", 120),
        ],
        "recovery": [
            None,
            ("recovery", 45),
            ("z2_endurance", 60),
            None,
            ("recovery", 45),
            ("z2_endurance", 90),
            None,
        ],
    }

    # Map phase names to focus types
    phase_focus_map = {
        "base rebuild": "base",
        "build 1": "build",
        "build 2": "build",
        "peak": "peak",
        "taper": "recovery",
    }

    with get_db() as conn:
        phases = conn.execute(
            "SELECT * FROM periodization_phases ORDER BY start_date"
        ).fetchall()

        if not phases:
            return {"status": "error", "message": "No periodization phases defined."}

        if not end_date:
            end_date = phases[-1]["end_date"]

        # Get current FTP
        ftp_row = conn.execute(
            "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY date DESC LIMIT 1"
        ).fetchone()
        ftp = ftp_row["ftp"] if ftp_row else 261

        def get_phase_for_date(d_str):
            for p in phases:
                if p["start_date"] <= d_str <= p["end_date"]:
                    return p
            return None

        # Delete existing planned workouts in the range
        conn.execute(
            "DELETE FROM planned_workouts WHERE date >= ? AND date <= ?",
            (start_date, end_date),
        )

        # Iterate week by week
        dt = datetime.fromisoformat(start_date)
        dt = dt - timedelta(days=dt.weekday())  # Align to Monday
        end_dt = datetime.fromisoformat(end_date)

        weeks_generated = []

        while dt <= end_dt:
            week_start = dt.strftime("%Y-%m-%d")
            mid_week = (dt + timedelta(days=3)).strftime("%Y-%m-%d")
            phase = get_phase_for_date(mid_week)

            if not phase:
                dt += timedelta(days=7)
                continue

            phase_name = phase["name"]
            focus = phase_focus_map.get(phase_name.lower(), "base")
            hours_low = phase["hours_per_week_low"] or 10
            hours_high = phase["hours_per_week_high"] or 14
            target_hours = (hours_low + hours_high) / 2

            # 3-week build / 1-week recovery cycle within each phase
            phase_start = datetime.fromisoformat(phase["start_date"])
            # Align phase start to its Monday for consistent week counting
            phase_monday = phase_start - timedelta(days=phase_start.weekday())
            weeks_into_phase = max(0, (dt - phase_monday).days // 7)
            cycle_week = weeks_into_phase % 4  # 0, 1, 2 = build; 3 = recovery

            if cycle_week == 3:
                week_focus = "recovery"
                week_hours = hours_low * 0.6
            elif cycle_week == 0:
                week_focus = focus
                week_hours = hours_low
            elif cycle_week == 1:
                week_focus = focus
                week_hours = target_hours
            else:
                week_focus = focus
                week_hours = hours_high

            # Generate workouts for this week inline
            week_template = templates.get(week_focus, templates["base"])
            total_planned_min = sum(d for t in week_template if t for _, d in [t])
            scale = (week_hours * 60) / total_planned_min if total_planned_min > 0 else 1.0

            workout_count = 0
            for day_offset, tmpl in enumerate(week_template):
                if tmpl is None:
                    continue

                workout_type, base_duration = tmpl
                duration = max(30, round(base_duration * scale))
                date_str = (dt + timedelta(days=day_offset)).strftime("%Y-%m-%d")

                # Only generate within the requested range
                if date_str < start_date or date_str > end_date:
                    continue

                conn.execute("DELETE FROM planned_workouts WHERE date = ?", (date_str,))
                xml_str, name = generate_zwo(workout_type, duration, ftp)
                conn.execute(
                    "INSERT INTO planned_workouts (date, name, sport, total_duration_s, workout_xml) VALUES (?, ?, ?, ?, ?)",
                    (date_str, name, "bike", duration * 60, xml_str),
                )
                workout_count += 1

            weeks_generated.append({
                "week_start": week_start,
                "phase": phase_name,
                "focus": week_focus,
                "hours": round(week_hours, 1),
                "cycle_week": cycle_week + 1,
                "is_recovery": cycle_week == 3,
                "workouts": workout_count,
            })

            dt += timedelta(days=7)

    return {
        "status": "success",
        "start_date": start_date,
        "end_date": end_date,
        "ftp": ftp,
        "weeks_generated": len(weeks_generated),
        "summary": weeks_generated,
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


def sync_workouts_to_garmin(date: str = "", workout_name: str = "") -> dict:
    """Sync planned workouts to Garmin via intervals.icu so they appear on the athlete's device.

    Can sync a single workout by date or name, or all workouts for a given week.
    The athlete can then see structured workouts on their Garmin device.

    Args:
        date: Date (YYYY-MM-DD) to sync workout(s) for. If empty, syncs all upcoming workouts for the current week.
        workout_name: Optional workout name to match. If provided with a date, syncs only that specific workout.

    Returns:
        Status of the sync operation with details of synced workouts.
    """
    if not icu_is_configured():
        return {"status": "error", "message": "intervals.icu is not configured. Cannot sync to Garmin."}

    with get_db() as conn:
        # Get FTP for the workout
        ftp_row = conn.execute(
            "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY date DESC LIMIT 1"
        ).fetchone()
        ftp = ftp_row["ftp"] if ftp_row else 261

        if date:
            # Sync workout(s) for a specific date
            if workout_name:
                rows = conn.execute(
                    "SELECT id, date, name, workout_xml, total_duration_s FROM planned_workouts WHERE date = ? AND name LIKE ?",
                    (date, f"%{workout_name}%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, date, name, workout_xml, total_duration_s FROM planned_workouts WHERE date = ?",
                    (date,),
                ).fetchall()
        else:
            # Sync all upcoming workouts for the current week
            today = datetime.now().strftime("%Y-%m-%d")
            dt = datetime.now()
            end = dt + timedelta(days=(6 - dt.weekday()))
            end_str = end.strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT id, date, name, workout_xml, total_duration_s FROM planned_workouts WHERE date >= ? AND date <= ? AND workout_xml IS NOT NULL",
                (today, end_str),
            ).fetchall()

    if not rows:
        return {"status": "no_workouts", "message": f"No planned workouts with structured data found for the specified criteria."}

    synced = []
    errors = []
    for row in rows:
        if not row["workout_xml"]:
            errors.append({"name": row["name"], "date": row["date"], "error": "No structured workout data (ZWO) available"})
            continue

        result = push_workout(
            date=row["date"],
            name=row["name"] or "Workout",
            zwo_xml=row["workout_xml"],
            moving_time_secs=int(row["total_duration_s"] or 0),
        )

        if result.get("status") == "success":
            synced.append({"name": row["name"], "date": row["date"]})
        else:
            errors.append({"name": row["name"], "date": row["date"], "error": result.get("message", "Unknown error")})

    return {
        "status": "success" if synced else "error",
        "synced": synced,
        "errors": errors,
        "message": f"Synced {len(synced)} workout(s) to Garmin via intervals.icu" + (f", {len(errors)} failed" if errors else ""),
    }


def update_coach_settings(section: str, new_value: str) -> dict:
    """Update coaching configuration settings like athlete profile, coaching principles, or coach behavior.

    Use this when the athlete tells you about changes to their profile (new FTP, weight, goals, target events),
    or when they want to adjust coaching style or principles.

    Args:
        section: Which setting to update. One of: 'athlete_profile', 'coaching_principles', 'coach_role', 'plan_management'.
        new_value: The full new value for that section. For athlete_profile and coaching_principles, use bullet points starting with '- '.

    Returns:
        Status of the update.
    """
    valid_sections = {"athlete_profile", "coaching_principles", "coach_role", "plan_management"}
    if section not in valid_sections:
        return {"status": "error", "message": f"Invalid section '{section}'. Must be one of: {', '.join(sorted(valid_sections))}"}

    set_setting(section, new_value)

    return {
        "status": "success",
        "section": section,
        "message": f"Updated {section.replace('_', ' ')}. Changes take effect immediately.",
    }
