"""ADK tools for the coaching agent to manage the training plan."""

from datetime import datetime, timedelta
from server.database import get_db, get_setting, set_setting, get_all_settings, get_athlete_setting, set_athlete_setting
from server.utils.dates import get_request_tz, user_today
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
        "coach_notes_hint": "Consider calling set_workout_coach_notes to update the notes if they reference the original date or day-of-week context.",
    }
    if existing:
        result["swapped_with"] = [dict(w)["name"] for w in existing]

    return result


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
                "using generate_week_from_spec.",
    }


def generate_week_from_spec(workouts: list[dict]) -> dict:
    """Create multiple planned workouts from an agent-provided specification.

    The agent decides WHAT to prescribe based on athlete data (CTL/ATL/TSB,
    recent ride quality, phase goals). This function just persists those decisions
    efficiently in a single DB transaction.

    Use this when planning a full week or multi-day block. For a single day,
    use replace_workout instead.

    Each workout in the list can be one of three modes:
    1. **Template mode**: Provide 'workout_type' (template key) and optionally 'duration_minutes'.
    2. **Custom mode**: Provide 'name', 'steps', and optionally 'description'.
    3. **Rest day**: Provide only 'date' (or set workout_type='rest') to clear that day.

    Args:
        workouts: List of workout spec dicts. Each dict:
            - date (str, required): YYYY-MM-DD
            - workout_type (str, optional): Template key for template mode, or 'rest'
            - duration_minutes (int, optional): Duration override for template mode
            - name (str, optional): Workout name for custom mode
            - description (str, optional): Workout description for custom mode (also stored as coach_notes)
            - steps (list[dict], optional): Step dicts for custom mode
            - coach_notes (str, optional): Pre-ride coaching note for the athlete.
              IMPORTANT: Always provide this — notes should reference the athlete's
              current TSB, recent training load, and specific execution cues.

    Returns:
        Dict with created workouts, rest days, and any errors per date.
    """
    from server.services.intervals_icu import delete_event

    created = []
    rest_days = []
    errors = []

    with get_db() as conn:
        ftp = get_current_ftp(conn)

        for spec in workouts:
            date = spec.get("date")
            if not date:
                errors.append({"error": "Missing 'date' field", "spec": spec})
                continue

            workout_type = spec.get("workout_type", "")
            name = spec.get("name", "")
            description = spec.get("description", "")
            steps = spec.get("steps", [])
            coach_notes = spec.get("coach_notes") or description or None
            duration_minutes = spec.get("duration_minutes", 0)

            # Collect stale event ID before replacing
            old_row = conn.execute(
                "SELECT name, icu_event_id FROM planned_workouts WHERE date = ?", (date,)
            ).fetchone()
            old_event_id = old_row["icu_event_id"] if old_row else None

            # Rest day: clear the date
            if workout_type == "rest" or (not workout_type and not name and not steps):
                conn.execute("DELETE FROM planned_workouts WHERE date = ?", (date,))
                if old_event_id:
                    try:
                        delete_event(old_event_id)
                    except Exception:
                        pass
                rest_days.append(date)
                continue

            try:
                # Custom mode
                if steps and name:
                    xml_str, workout_name = generate_custom_zwo(name, description or "", steps, ftp)
                    total_s = 0
                    for s in steps:
                        if s.get("type") == "Intervals":
                            total_s += s.get("repeat", 1) * (s.get("on_duration_seconds", 0) + s.get("off_duration_seconds", 0))
                        else:
                            total_s += s.get("duration_seconds", 0)
                    duration_minutes = max(1, round(total_s / 60))

                # Template mode
                elif workout_type:
                    tmpl = get_template(workout_type)
                    if not tmpl:
                        available = [t["key"] for t in _list_templates()]
                        errors.append({
                            "date": date,
                            "error": f"Unknown workout_type '{workout_type}'. Available: {', '.join(sorted(available))}",
                        })
                        continue
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
                    errors.append({"date": date, "error": "Provide workout_type (template) or name+steps (custom)."})
                    continue

                conn.execute("DELETE FROM planned_workouts WHERE date = ?", (date,))
                tss = calculate_planned_tss(xml_str)
                conn.execute(
                    "INSERT INTO planned_workouts (date, name, sport, total_duration_s, planned_tss, workout_xml, coach_notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (date, workout_name, "bike", duration_minutes * 60, tss, xml_str, coach_notes),
                )
                created.append({"date": date, "name": workout_name, "duration_min": duration_minutes, "tss": round(tss or 0)})

                if old_event_id:
                    try:
                        delete_event(old_event_id)
                    except Exception:
                        pass

            except Exception as e:
                errors.append({"date": date, "error": str(e)})

    return {
        "status": "success" if not errors else "partial",
        "ftp_used": ftp,
        "created": created,
        "rest_days": rest_days,
        "errors": errors,
        "total_workouts": len(created),
        "message": f"Created {len(created)} workout(s), {len(rest_days)} rest day(s)" + (f", {len(errors)} error(s)" if errors else ""),
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
        # Custom mode: description becomes coach_notes. Template mode: notes are agent-provided.
        if steps and name:
            insert_notes = description or None
        else:
            insert_notes = None
        conn.execute(
            "INSERT INTO planned_workouts (date, name, sport, total_duration_s, planned_tss, workout_xml, coach_notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, workout_name, "bike", duration_minutes * 60, tss, xml_str, insert_notes),
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
        "coach_notes_set": bool(insert_notes),
        "coach_notes_hint": "Call set_workout_coach_notes with personalized notes referencing the athlete's current TSB and recent training.",
    }


def get_week_summary(date: str = "") -> dict:
    """Get a combined view of planned vs actual workouts for a week.

    Args:
        date: Any date in the target week (YYYY-MM-DD). Defaults to current week.

    Returns:
        Weekly overview with planned, actual rides, and compliance.
    """
    if not date:
        date = user_today()

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

    _now = datetime.now(get_request_tz())
    now_iso = _now.isoformat(timespec="seconds")

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
            today = _now.strftime("%Y-%m-%d")
            end = _now + timedelta(days=(6 - _now.weekday()))
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
    """Update qualitative coaching configuration settings like athlete goals or coaching principles.

    Use this when the athlete tells you about changes to their qualitative profile (new goals,
    target events, strengths, limiters) or when they want to adjust coaching focus.

    Note: coach_role and plan_management can only be edited by an administrator via the settings UI.

    Args:
        section: Which setting to update. One of: 'athlete_profile', 'coaching_principles'.
        new_value: The full new value for that section. Use bullet points starting with '- '.

    Returns:
        Status of the update.
    """
    valid_sections = {"athlete_profile", "coaching_principles"}
    if section not in valid_sections:
        return {"status": "error", "message": f"Invalid section '{section}'. Must be one of: {', '.join(sorted(valid_sections))}. (coach_role and plan_management can only be edited by an administrator.)"}

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
    and the Performance Management Chart (PMC). Each update creates a historical record and 
    synchronizes FTP and Weight changes with Intervals.icu automatically.

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

    # Sync with intervals.icu if applicable
    from server.services.intervals_icu import update_ftp, update_weight
    sync_status = "not_synced"
    if key == "ftp":
        try:
            update_ftp(int(value))
            sync_status = "synced"
        except (ValueError, Exception):
            sync_status = "sync_failed"
    elif key == "weight_kg":
        try:
            update_weight(float(value), date_set)
            sync_status = "synced"
        except (ValueError, Exception):
            sync_status = "sync_failed"

    return {
        "status": "success",
        "key": key,
        "value": value,
        "date_set": date_set or user_today(),
        "sync_status": sync_status,
        "message": f"Updated {key} to {value}. This structured benchmark will be used for future metric calculations and interval analysis. Changes were {'successfully' if sync_status == 'synced' else 'not'} pushed to Intervals.icu.",
    }
