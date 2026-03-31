"""ADK tools for the coaching agent to manage the training plan."""

from datetime import datetime, timedelta
from server.database import get_db, get_setting, set_setting, get_all_settings, get_athlete_setting, set_athlete_setting
from server.queries import get_current_ftp, get_periodization_phases, get_week_planned_and_actual
from server.services.workout_generator import generate_zwo, generate_custom_zwo, get_template, list_templates as _list_templates, calculate_planned_tss
from server.services.intervals_icu import push_workout, delete_event, compute_sync_hash, is_configured as icu_is_configured


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
        ftp = get_current_ftp(conn)

        for day_offset, template in enumerate(week_template):
            if template is None:
                continue

            workout_type, base_duration = template
            duration = max(30, round(base_duration * scale))
            date_str = (dt + timedelta(days=day_offset)).strftime("%Y-%m-%d")

            # Remove any existing workout on this date (collect stale event ID)
            old_row = conn.execute(
                "SELECT icu_event_id FROM planned_workouts WHERE date = ? AND icu_event_id IS NOT NULL",
                (date_str,),
            ).fetchone()
            if old_row:
                try:
                    delete_event(old_row["icu_event_id"])
                except Exception:
                    pass
            conn.execute("DELETE FROM planned_workouts WHERE date = ?", (date_str,))

            # Generate ZWO
            xml_str, name = generate_zwo(workout_type, duration, ftp)
            tss = calculate_planned_tss(xml_str)

            conn.execute(
                "INSERT INTO planned_workouts (date, name, sport, total_duration_s, planned_tss, workout_xml) VALUES (?, ?, ?, ?, ?, ?)",
                (date_str, name, "bike", duration * 60, tss, xml_str),
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
        phases = get_periodization_phases(conn)

        if not phases:
            return {"status": "error", "message": "No periodization phases defined."}

        if not end_date:
            end_date = phases[-1]["end_date"]

        ftp = get_current_ftp(conn)

        def get_phase_for_date(d_str):
            for p in phases:
                if p["start_date"] <= d_str <= p["end_date"]:
                    return p
            return None

        # Collect stale event IDs before deleting workouts
        stale_events = conn.execute(
            "SELECT icu_event_id FROM planned_workouts WHERE date >= ? AND date <= ? AND icu_event_id IS NOT NULL",
            (start_date, end_date),
        ).fetchall()
        stale_event_ids = [r["icu_event_id"] for r in stale_events]

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
                tss = calculate_planned_tss(xml_str)
                conn.execute(
                    "INSERT INTO planned_workouts (date, name, sport, total_duration_s, planned_tss, workout_xml) VALUES (?, ?, ?, ?, ?, ?)",
                    (date_str, name, "bike", duration * 60, tss, xml_str),
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

    # Clean up stale events on intervals.icu (best-effort, after DB commit)
    for eid in stale_event_ids:
        try:
            delete_event(eid)
        except Exception:
            pass

    return {
        "status": "success",
        "start_date": start_date,
        "end_date": end_date,
        "ftp": ftp,
        "weeks_generated": len(weeks_generated),
        "summary": weeks_generated,
    }


def replace_workout(date: str, workout_type: str = "", duration_minutes: int = 0,
                     name: str = "", description: str = "", steps: list[dict] = []) -> dict:
    """Replace or create a single day's planned workout without affecting other days.

    Use this when the athlete wants to change, customize, or add a workout for one day.

    There are three modes:
    1. **Template mode**: Set workout_type to a template key from the database.
       Use list_workout_templates to see available templates. Optionally set duration_minutes.
    2. **Custom mode**: Set name, description, and steps to design a fully custom workout.
       Each step is a dict with 'type' and type-specific fields:
       - Warmup: {type: "Warmup", duration_seconds: 600, power_low: 0.40, power_high: 0.75}
       - Cooldown: {type: "Cooldown", duration_seconds: 300, power_low: 0.65, power_high: 0.40}
       - SteadyState: {type: "SteadyState", duration_seconds: 900, power: 0.90}
       - Intervals: {type: "Intervals", repeat: 4, on_duration_seconds: 240,
         off_duration_seconds: 240, on_power: 1.18, off_power: 0.50}
       Power values are FTP fractions (e.g., 0.75 = 75% FTP, 1.0 = FTP, 1.18 = 118% FTP).
    3. **Rest mode**: Set workout_type to "rest" to remove the workout.

    Prefer custom mode when the athlete needs a specific workout structure. Use template mode
    for quick standard workouts. Include coaching notes in description (RPE cues, cadence
    targets, terrain notes, what to focus on).

    Args:
        date: The date to replace (YYYY-MM-DD).
        workout_type: Template name or "rest". Leave empty for custom mode.
        duration_minutes: Duration for template mode. Ignored in custom mode.
        name: Workout name for custom mode (e.g., "3x8 Climbing Threshold").
        description: Coaching notes for custom mode (instructions, RPE cues, cadence targets, etc.).
        steps: List of step dicts for custom mode. See above for format.

    Returns:
        Details of the new workout, or confirmation of rest day.
    """
    # Rest mode: clear the day
    if workout_type == "rest":
        with get_db() as conn:
            deleted = conn.execute(
                "SELECT name, icu_event_id FROM planned_workouts WHERE date = ?", (date,)
            ).fetchone()
            old_event_id = deleted["icu_event_id"] if deleted else None
            conn.execute("DELETE FROM planned_workouts WHERE date = ?", (date,))
        # Clean up stale event on intervals.icu
        if old_event_id:
            try:
                delete_event(old_event_id)
            except Exception:
                pass
        return {
            "status": "success",
            "date": date,
            "action": "removed",
            "previous_workout": deleted["name"] if deleted else None,
            "message": f"Cleared workout on {date} — now a rest day.",
        }

    with get_db() as conn:
        ftp = get_current_ftp(conn)

        previous = conn.execute(
            "SELECT name, icu_event_id FROM planned_workouts WHERE date = ?", (date,)
        ).fetchone()
        old_event_id = previous["icu_event_id"] if previous else None

        # Custom mode: agent-designed workout with specific steps
        if steps and name:
            xml_str, workout_name = generate_custom_zwo(name, description or "", steps, ftp)
            total_s = 0
            for s in steps:
                if s["type"] == "Intervals":
                    total_s += s["repeat"] * (s["on_duration_seconds"] + s["off_duration_seconds"])
                else:
                    total_s += s.get("duration_seconds", 0)
            duration_minutes = max(1, round(total_s / 60))

        # Template mode: use a database template
        elif workout_type:
            tmpl = get_template(workout_type)
            if not tmpl:
                available = [t["key"] for t in _list_templates()]
                return {
                    "status": "error",
                    "message": f"Unknown workout type '{workout_type}'. "
                               f"Available: {', '.join(sorted(available))}, rest",
                }
            if duration_minutes <= 0:
                total_s = 0
                for s in tmpl["steps"]:
                    if s["type"] in ("Intervals", "IntervalsT"):
                        total_s += s.get("repeat", 1) * (s.get("on_duration_seconds", s.get("on_duration", 0)) + s.get("off_duration_seconds", s.get("off_duration", 0)))
                    else:
                        total_s += s.get("duration_seconds", s.get("duration", 0)) or 0
                duration_minutes = max(30, round(total_s / 60))
            xml_str, workout_name = generate_zwo(workout_type, duration_minutes, ftp)
        else:
            return {
                "status": "error",
                "message": "Provide either workout_type (template mode) or name + steps (custom mode).",
            }

        conn.execute("DELETE FROM planned_workouts WHERE date = ?", (date,))
        tss = calculate_planned_tss(xml_str)
        conn.execute(
            "INSERT INTO planned_workouts (date, name, sport, total_duration_s, planned_tss, workout_xml) VALUES (?, ?, ?, ?, ?, ?)",
            (date, workout_name, "bike", duration_minutes * 60, tss, xml_str),
        )

    # Clean up stale event on intervals.icu
    if old_event_id:
        try:
            delete_event(old_event_id)
        except Exception:
            pass

    return {
        "status": "success",
        "date": date,
        "action": "replaced" if previous else "created",
        "previous_workout": previous["name"] if previous else None,
        "new_workout": workout_name,
        "duration_min": duration_minutes,
        "ftp": ftp,
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
        planned, actual = get_week_planned_and_actual(conn, start_str, end_str)

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

    now_iso = datetime.now().isoformat(timespec="seconds")

    with get_db() as conn:
        ftp = get_current_ftp(conn)

        if date:
            # Sync workout(s) for a specific date
            if workout_name:
                rows = conn.execute(
                    "SELECT id, date, name, workout_xml, total_duration_s, icu_event_id, sync_hash FROM planned_workouts WHERE date = ? AND name LIKE ?",
                    (date, f"%{workout_name}%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, date, name, workout_xml, total_duration_s, icu_event_id, sync_hash FROM planned_workouts WHERE date = ?",
                    (date,),
                ).fetchall()
        else:
            # Sync all upcoming workouts for the current week
            today = datetime.now().strftime("%Y-%m-%d")
            dt = datetime.now()
            end = dt + timedelta(days=(6 - dt.weekday()))
            end_str = end.strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT id, date, name, workout_xml, total_duration_s, icu_event_id, sync_hash FROM planned_workouts WHERE date >= ? AND date <= ? AND workout_xml IS NOT NULL",
                (today, end_str),
            ).fetchall()

        if not rows:
            return {"status": "no_workouts", "message": "No planned workouts with structured data found for the specified criteria."}

        synced = []
        skipped = []
        errors = []
        for row in rows:
            row = dict(row)
            if not row["workout_xml"]:
                errors.append({"name": row["name"], "date": row["date"], "error": "No structured workout data (ZWO) available"})
                continue

            w_name = row["name"] or "Workout"
            moving_time = int(row["total_duration_s"] or 0)
            current_hash = compute_sync_hash(w_name, row["date"], row["workout_xml"], moving_time)

            # Skip if unchanged
            if row.get("sync_hash") == current_hash and row.get("icu_event_id"):
                skipped.append({"name": w_name, "date": row["date"]})
                continue

            result = push_workout(
                date=row["date"],
                name=w_name,
                zwo_xml=row["workout_xml"],
                moving_time_secs=moving_time,
                icu_event_id=row.get("icu_event_id"),
            )

            if result.get("status") == "success":
                conn.execute(
                    "UPDATE planned_workouts SET icu_event_id = ?, sync_hash = ?, synced_at = ? WHERE id = ?",
                    (result.get("event_id"), current_hash, now_iso, row["id"]),
                )
                synced.append({"name": w_name, "date": row["date"]})
            else:
                errors.append({"name": w_name, "date": row["date"], "error": result.get("message", "Unknown error")})

    msg = f"Synced {len(synced)} workout(s) to Garmin via intervals.icu"
    if skipped:
        msg += f", {len(skipped)} unchanged (skipped)"
    if errors:
        msg += f", {len(errors)} failed"

    return {
        "status": "success" if synced or skipped else "error",
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "message": msg,
    }


def list_workout_templates(category: str = "") -> dict:
    """List available workout templates from the database.

    Use this to see what templates are available before using replace_workout in template mode,
    or to show the athlete their template library.

    Args:
        category: Optional filter by category (base, build, peak, recovery, general).
            Leave empty to list all templates.

    Returns:
        List of templates with key, name, description, category, and step count.
    """
    templates = _list_templates()
    if category:
        templates = [t for t in templates if t["category"] == category]

    return {
        "status": "success",
        "count": len(templates),
        "templates": [
            {
                "key": t["key"],
                "name": t["name"],
                "description": t["description"],
                "category": t["category"],
                "source": t["source"],
                "step_count": len(t["steps"]),
            }
            for t in templates
        ],
    }


def save_workout_template(key: str, name: str, description: str, category: str,
                           steps: list[dict] = [], from_workout_id: int = 0) -> dict:
    """Save a new workout template to the database for future reuse.

    Use this when:
    - The athlete likes a workout and wants to save it as a template
    - You want to create a new template based on a workout you designed
    - The athlete asks you to create a template from a planned workout

    If from_workout_id is provided, the steps are extracted from that planned workout's
    ZWO data (ignoring the steps parameter).

    Args:
        key: Unique identifier slug (e.g., "tempo_over_unders", "mtb_climbing_repeats").
            Use lowercase with underscores. Must be unique.
        name: Human-readable name (e.g., "Tempo Over-Unders", "MTB Climbing Repeats").
        description: Coaching notes — what the workout targets, how it should feel,
            RPE cues, cadence guidance, terrain suggestions.
        category: One of: base, build, peak, recovery, general.
        steps: List of step dicts (same format as replace_workout custom mode):
            - Warmup: {type: "Warmup", duration_seconds: 600, power_low: 0.40, power_high: 0.75}
            - Cooldown: {type: "Cooldown", duration_seconds: 300, power_low: 0.65, power_high: 0.40}
            - SteadyState: {type: "SteadyState", duration_seconds: 900, power: 0.90}
            - Intervals: {type: "Intervals", repeat: 4, on_duration_seconds: 240,
              off_duration_seconds: 240, on_power: 1.18, off_power: 0.50}
        from_workout_id: Optional. If set, extract steps from this planned workout instead
            of using the steps parameter.

    Returns:
        The saved template details.
    """
    import json

    # Extract steps from an existing planned workout if requested
    if from_workout_id:
        with get_db() as conn:
            row = conn.execute(
                "SELECT name, workout_xml FROM planned_workouts WHERE id = ?",
                (from_workout_id,),
            ).fetchone()
        if not row:
            return {"status": "error", "message": f"Planned workout {from_workout_id} not found."}
        if not row["workout_xml"]:
            return {"status": "error", "message": f"Planned workout {from_workout_id} has no structured data."}

        # Parse ZWO XML back into step format
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(row["workout_xml"])
        except ET.ParseError:
            return {"status": "error", "message": "Could not parse workout XML."}

        workout_el = root.find("workout")
        if workout_el is None:
            return {"status": "error", "message": "No workout element found in XML."}

        steps = []
        for el in workout_el:
            tag = el.tag
            if tag == "IntervalsT":
                steps.append({
                    "type": "Intervals",
                    "repeat": int(el.get("Repeat", "1")),
                    "on_duration_seconds": int(float(el.get("OnDuration", "0"))),
                    "off_duration_seconds": int(float(el.get("OffDuration", "0"))),
                    "on_power": float(el.get("OnPower", "1.0")),
                    "off_power": float(el.get("OffPower", "0.5")),
                })
            elif tag in ("Warmup", "Cooldown"):
                steps.append({
                    "type": tag,
                    "duration_seconds": int(float(el.get("Duration", "0"))),
                    "power_low": float(el.get("PowerLow", "0.4")),
                    "power_high": float(el.get("PowerHigh", "0.65")),
                })
            elif tag == "SteadyState":
                steps.append({
                    "type": "SteadyState",
                    "duration_seconds": int(float(el.get("Duration", "0"))),
                    "power": float(el.get("Power", "0.65")),
                })

        if not name:
            name = row["name"] or key

    if not steps:
        return {"status": "error", "message": "No steps provided and no workout to extract from."}

    valid_categories = {"base", "build", "peak", "recovery", "general"}
    if category not in valid_categories:
        return {"status": "error", "message": f"Invalid category. Must be one of: {', '.join(sorted(valid_categories))}"}

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM workout_templates WHERE key = ?", (key,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE workout_templates SET name = ?, description = ?, category = ?, steps = ?, source = ? WHERE key = ?",
                (name, description, category, json.dumps(steps), "coach", key),
            )
            action = "updated"
        else:
            conn.execute(
                "INSERT INTO workout_templates (key, name, description, category, steps, source) VALUES (?, ?, ?, ?, ?, ?)",
                (key, name, description, category, json.dumps(steps), "coach"),
            )
            action = "created"

    return {
        "status": "success",
        "action": action,
        "key": key,
        "name": name,
        "category": category,
        "step_count": len(steps),
        "message": f"Template '{name}' {action}. It can now be used with replace_workout(workout_type='{key}') "
                   f"or in weekly plan generation.",
    }


def set_workout_coach_notes(date: str, notes: str) -> dict:
    """Set coach's pre-ride notes on a planned workout.

    Use this to give the athlete instructions, focus areas, RPE targets,
    or other guidance before they do a workout.

    Args:
        date: The workout date (YYYY-MM-DD).
        notes: Coach's notes/instructions for the athlete.

    Returns:
        Status of the update.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name FROM planned_workouts WHERE date = ? LIMIT 1", (date,)
        ).fetchone()
        if not row:
            return {"status": "error", "message": f"No planned workout found on {date}"}
        conn.execute(
            "UPDATE planned_workouts SET coach_notes = ? WHERE id = ?",
            (notes, row["id"]),
        )
    return {
        "status": "success",
        "message": f"Coach notes set for {date} ({row['name']})",
    }


def set_ride_coach_comments(date: str, comments: str) -> dict:
    """Set coach's post-ride analysis/comments on a completed ride.

    Use this to provide feedback on a completed ride — what went well,
    what to improve, how it fits the training plan, recovery advice.

    Args:
        date: The ride date (YYYY-MM-DD).
        comments: Coach's post-ride analysis and feedback.

    Returns:
        Status of the update.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, sub_sport FROM rides WHERE date = ? ORDER BY duration_s DESC LIMIT 1",
            (date,),
        ).fetchone()
        if not row:
            return {"status": "error", "message": f"No ride found on {date}"}
        conn.execute(
            "UPDATE rides SET coach_comments = ? WHERE id = ?",
            (comments, row["id"]),
        )
    return {
        "status": "success",
        "message": f"Coach comments set for {date} ride",
    }


def update_coach_settings(section: str, new_value: str) -> dict:
    """Update qualitative coaching configuration settings like goals, principles, or coach behavior.

    Use this when the athlete tells you about changes to their qualitative profile (new goals, 
    target events, strengths, limiters) or when they want to adjust coaching style or principles.

    For structured numeric values like FTP, Weight, or Heart Rate, use update_athlete_setting instead.

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
        "message": f"Updated {section.replace('_', ' ')}. Qualitative profile changes saved.",
    }


def update_athlete_setting(key: str, value: str, date_set: str = "") -> dict:
    """Update a structured athlete benchmark like FTP, weight, heart rate thresholds, etc.

    Use this when the athlete reports changes to measurable values. These settings are critical
    for metric calculations (TSS, IF, NP), workout power targets, zone calculations, 
    and the Performance Management Chart (PMC). Each update creates a historical record.

    Args:
        key: Setting to update. One of: 'ftp', 'weight_kg', 'lthr', 'max_hr', 'resting_hr', 'age', 'gender'.
        value: The new value (e.g., '275' for FTP, '74' for weight).
        date_set: Optional date (YYYY-MM-DD) when this benchmark became effective. Defaults to today.

    Returns:
        Status of the update.
    """
    from server.database import ATHLETE_SETTINGS_DEFAULTS
    valid_keys = set(ATHLETE_SETTINGS_DEFAULTS.keys())
    if key not in valid_keys:
        return {"status": "error", "message": f"Invalid key '{key}'. Must be one of: {', '.join(sorted(valid_keys))}"}

    set_athlete_setting(key, value, date_set)

    return {
        "status": "success",
        "key": key,
        "value": value,
        "date_set": date_set or datetime.now().strftime("%Y-%m-%d"),
        "message": f"Updated {key} to {value}. This structured benchmark will be used for future metric calculations and interval analysis.",
    }
